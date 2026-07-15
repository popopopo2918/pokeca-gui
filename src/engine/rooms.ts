import { LocalEngineController } from './localEngine';
import type { EngineResponse, GameView, SequencePlayback } from '../lib/game/types';
import { maskViewForSeat } from './viewMask';

// 遠隔対戦ルーム: 2つのブラウザが同じ対戦（1つのエンジン）を座席0/1で共有する。
// - 座席はクライアントID（x-cabt-client）に紐づく。再読み込みしても同じ席に戻れる。
// - 手番でない側のコマンドはサーバーが拒否する。
// - ビューは座席ごとにマスクして返す（相手の手札・相手のドロー内容などを隠す）。
// - 進行はポーリング同期: コマンド成功ごとに revision が進み、差分フレームを配る。

type RoomFrame = { rev: number; view: GameView };

type Room = {
  code: string;
  controller: LocalEngineController;
  seats: [string | null, string | null];
  decks: [unknown[] | null, unknown[] | null];
  sessionId: string;
  started: boolean;
  revision: number;
  frames: RoomFrame[];
  lastUsed: number;
  queue: Promise<unknown>;
  /** 決着時の対戦ログ自動保存を1回に抑えるフラグ */
  saved: boolean;
};

const rooms = new Map<string, Room>();
const ROOM_IDLE_MS = 60 * 60 * 1000;
const MAX_ROOMS = 8;
const MAX_FRAMES = 300;

setInterval(pruneRooms, 5 * 60 * 1000).unref();

function pruneRooms(): void {
  const now = Date.now();
  for (const [code, room] of rooms) {
    if (now - room.lastUsed > ROOM_IDLE_MS) {
      room.controller.close();
      rooms.delete(code);
    }
  }
}

// 紛らわしい文字（0/O, 1/I など）を除いたルームコード。
const CODE_CHARS = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';

function createRoomCode(): string {
  let code = '';
  for (let i = 0; i < 6; i += 1) {
    code += CODE_CHARS[Math.floor(Math.random() * CODE_CHARS.length)];
  }
  return rooms.has(code) ? createRoomCode() : code;
}

export function createRoom(clientId: string, deck: unknown): { ok: boolean; code?: string; seat?: number; error?: string } {
  if (!Array.isArray(deck) || deck.length !== 60) {
    return { ok: false, error: 'デッキはちょうど60枚にしてください。' };
  }
  pruneRooms();
  if (rooms.size >= MAX_ROOMS) {
    return { ok: false, error: 'ルーム数が上限に達しています。しばらくしてからお試しください。' };
  }
  const room: Room = {
    code: createRoomCode(),
    controller: new LocalEngineController(),
    seats: [clientId, null],
    decks: [deck, null],
    sessionId: '',
    started: false,
    revision: 0,
    frames: [],
    lastUsed: Date.now(),
    queue: Promise.resolve(),
    saved: false,
  };
  rooms.set(room.code, room);
  return { ok: true, code: room.code, seat: 0 };
}

export async function joinRoom(clientId: string, code: string, deck: unknown): Promise<Record<string, unknown>> {
  const room = rooms.get(normalizeCode(code));
  if (!room) {
    return { ok: false, error: 'ルームが見つかりません。コードを確認してください。' };
  }
  room.lastUsed = Date.now();
  const existingSeat = room.seats.indexOf(clientId);
  if (existingSeat >= 0) {
    return { ok: true, seat: existingSeat, started: room.started };
  }
  if (room.seats[1]) {
    return { ok: false, error: 'このルームは満員です。' };
  }
  if (!Array.isArray(deck) || deck.length !== 60) {
    return { ok: false, error: 'デッキはちょうど60枚にしてください。' };
  }
  room.seats[1] = clientId;
  room.decks[1] = deck;

  const response = await enqueue(room, () => room.controller.handle({
    type: 'startGame',
    payload: {
      player1: { name: 'プレイヤー1', deck: room.decks[0], control: 'self' },
      player2: { name: 'プレイヤー2', deck: room.decks[1], control: 'self', manualOpponent: true },
    },
  }));
  if (!response.ok) {
    room.seats[1] = null;
    room.decks[1] = null;
    return { ok: false, error: response.error };
  }
  room.sessionId = response.sessionId ?? '';
  room.started = true;
  appendFrames(room, response);
  return { ok: true, seat: 1, started: true };
}

export function leaveRoom(clientId: string, code: string): { ok: boolean } {
  const room = rooms.get(normalizeCode(code));
  if (room && room.seats.includes(clientId)) {
    room.controller.close();
    rooms.delete(room.code);
  }
  return { ok: true };
}

export function roomState(clientId: string, code: string, since: number): Record<string, unknown> {
  const room = rooms.get(normalizeCode(code));
  if (!room) {
    return { ok: false, error: 'ルームが見つかりません（相手が退出したか、期限切れです）。' };
  }
  const seat = room.seats.indexOf(clientId);
  if (seat < 0) {
    return { ok: false, error: 'このルームの参加者ではありません。' };
  }
  room.lastUsed = Date.now();
  if (!room.started) {
    return { ok: true, started: false, revision: room.revision, code: room.code, seat };
  }
  const stateView = currentView(room);
  const sequence = room.frames
    .filter((frame) => frame.rev > since)
    .map((frame) => maskViewForSeat(frame.view, seat));
  return {
    ok: true,
    started: true,
    revision: room.revision,
    code: room.code,
    seat,
    view: maskViewForSeat(stateView, seat),
    sequence: sequence.length ? sequence : undefined,
    sequencePlayback: sequence.length ? remotePlayback(sequence.length) : undefined,
  };
}

export async function roomCommand(clientId: string, code: string, command: { type: string; payload?: any }): Promise<Record<string, unknown>> {
  const room = rooms.get(normalizeCode(code));
  if (!room) {
    return { ok: false, error: 'ルームが見つかりません（相手が退出したか、期限切れです）。' };
  }
  const seat = room.seats.indexOf(clientId);
  if (seat < 0) {
    return { ok: false, error: 'このルームの参加者ではありません。' };
  }
  if (!room.started) {
    return { ok: false, error: 'まだ対戦が始まっていません。' };
  }
  room.lastUsed = Date.now();
  if (command.type === 'startGame' || command.type === 'undo') {
    return { ok: false, error: 'オンライン対戦ではこの操作は使えません。' };
  }
  const acting = actingSeat(room);
  // 投了は自分の手番でなくてもできる（手番制限すると相手ターン中に降参できない）
  if (command.type !== 'state' && command.type !== 'concede' && acting !== seat) {
    return { ok: false, error: '相手の手番です。' };
  }

  const response = await enqueue(room, () => room.controller.handle({
    type: command.type,
    payload: { ...(command.payload ?? {}), sessionId: room.sessionId },
  }));
  if (response.ok) {
    appendFrames(room, response);
    maybeSaveFinishedReplay(room, response);
  }
  const masked: Record<string, unknown> = {
    ...response,
    view: response.view ? maskViewForSeat(response.view, seat) : response.view,
    sequence: response.ok && response.sequence ? response.sequence.map((view) => maskViewForSeat(view, seat)) : undefined,
    sequencePlayback: response.ok && response.sequence
      ? senderPlayback(response.sequencePlayback, response.sequence.length)
      : undefined,
    revision: room.revision,
    undoCount: 0,
  };
  delete masked.sessionId;
  return masked;
}

// 決着したら、ルームを動かしているサーバー側の対戦ログへ自動保存する（1回だけ）。
// ローカル対戦の自動保存と同じ形式なので、対戦ログタブからそのまま再生できる。
function maybeSaveFinishedReplay(room: Room, response: EngineResponse): void {
  if (room.saved || !response.ok || response.view?.phase !== 7) {
    return;
  }
  room.saved = true;
  try {
    room.controller.saveReplay();
  } catch {
    // 保存失敗時は次の機会（手動のログ出力）に任せる
    room.saved = false;
  }
}

/** 対戦中でも押せる手動の「ログ出力」用。保存したファイル名を返す。 */
export function roomSaveReplay(clientId: string, code: string): Record<string, unknown> {
  const room = rooms.get(normalizeCode(code));
  if (!room) {
    return { ok: false, error: 'ルームが見つかりません（相手が退出したか、期限切れです）。' };
  }
  if (room.seats.indexOf(clientId) < 0) {
    return { ok: false, error: 'このルームの参加者ではありません。' };
  }
  room.lastUsed = Date.now();
  const result = room.controller.saveReplay();
  // 対戦中の手動保存は途中までの記録。決着時の自動保存（完全版）は別途走らせたいので、
  // saved を立てるのは決着後に保存した場合だけにする。
  if (result.ok && currentView(room).phase === 7) {
    room.saved = true;
  }
  return result as unknown as Record<string, unknown>;
}

function enqueue(room: Room, task: () => Promise<EngineResponse>): Promise<EngineResponse> {
  const next = room.queue.then(task, task);
  room.queue = next.catch(() => undefined);
  return next;
}

function currentView(room: Room): GameView {
  const last = room.frames.at(-1);
  return last ? last.view : room.controller.currentGameView();
}

function actingSeat(room: Room): number {
  const view = currentView(room);
  return view.prompts[0]?.playerIndex ?? view.activePlayerIndex;
}

function appendFrames(room: Room, response: EngineResponse): void {
  if (!response.ok) {
    return;
  }
  const views = response.sequence?.length ? response.sequence : [response.view];
  for (const view of views) {
    room.revision += 1;
    room.frames.push({ rev: room.revision, view });
  }
  if (room.frames.length > MAX_FRAMES) {
    room.frames = room.frames.slice(-MAX_FRAMES);
  }
}

function normalizeCode(code: string): string {
  return code.trim().toUpperCase();
}

function remotePlayback(count: number): SequencePlayback[] {
  return Array.from({ length: count }, () => 'animate');
}

function senderPlayback(playback: SequencePlayback[] | undefined, count: number): SequencePlayback[] {
  return Array.from({ length: count }, (_unused, index) => playback?.[index] ?? 'animate');
}

export const __test = { remotePlayback, senderPlayback };
