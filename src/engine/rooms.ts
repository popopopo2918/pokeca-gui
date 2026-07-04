import { LocalEngineController } from './localEngine';
import { CabtAreaType } from '../lib/cabt/types';
import type { ActionTimelineEvent, EngineResponse, GameView, PromptView } from '../lib/game/types';

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
  }
  const masked: Record<string, unknown> = {
    ...response,
    view: response.view ? maskViewForSeat(response.view, seat) : response.view,
    sequence: response.ok && response.sequence ? response.sequence.map((view) => maskViewForSeat(view, seat)) : undefined,
    revision: room.revision,
    undoCount: 0,
  };
  delete masked.sessionId;
  return masked;
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

// ---- 座席ごとの情報マスク ----

const HIDDEN_CARD = { name: '未公開', fullName: '相手の手札（未公開）' };

function maskViewForSeat(view: GameView, seat: number): GameView {
  const opponent = 1 - seat;
  return {
    ...view,
    players: view.players.map((player, index) => (
      index === opponent
        ? { ...player, hand: player.hand.map(() => ({ ...HIDDEN_CARD })), prizeContents: undefined }
        : player
    )),
    prompts: view.prompts.map((prompt) => maskPrompt(prompt, seat)),
    actionTimeline: view.actionTimeline?.map((event) => maskTimelineEvent(event, opponent)),
  };
}

function maskPrompt(prompt: PromptView, seat: number): PromptView {
  if (prompt.playerIndex === seat || prompt.fields?.playbackOnly === true) {
    return prompt;
  }
  // 相手の選択肢（山札検索の中身など）は内容を渡さない。
  const { cardList: _cards, cards: _cards2, values: _values, prizes: _prizes, cabtSelect: _select, ...rest } = prompt.fields ?? {};
  return { ...prompt, fields: { ...rest, masked: true } };
}

function maskTimelineEvent(event: ActionTimelineEvent, opponent: number): ActionTimelineEvent {
  if (event.playerIndex !== opponent) {
    return event;
  }
  const params = (event.params ?? {}) as Record<string, unknown>;
  const toHand = Number(params.toArea) === CabtAreaType.HAND;
  const isDraw = event.kind === 'Draw';
  if (!isDraw && !toHand) {
    return event;
  }
  const actor = `プレイヤー${opponent + 1}`;
  const message = isDraw ? `${actor}はカードを引いた。` : `${actor}はカードを手札に加えた。`;
  const { cardId: _cardId, serial: _serial, ...maskedParams } = params;
  return { ...event, message, params: maskedParams };
}
