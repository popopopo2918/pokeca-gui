import { randomBytes } from 'node:crypto';
import type { EngineResponse, GameView, SequencePlayback } from '../lib/game/types';
import type {
  CodexDecisionRecord,
  CodexDeckEntry,
  CodexEngineDecision,
  CodexRationale,
  CodexSearchSnapshot,
} from './codexProtocol';
import { LocalEngineController } from './localEngine';
import { maskViewForCodex, maskViewForSeat } from './viewMask';

type Controller = Pick<
  LocalEngineController,
  | 'handle'
  | 'currentGameView'
  | 'currentCodexDecision'
  | 'applyCodexDecision'
  | 'describeCodexDeck'
  | 'currentCodexSearch'
  | 'saveReplay'
  | 'close'
>;

type CodexMatch = {
  id: string;
  connectionCode: string;
  humanClientId: string;
  humanSeat: 0 | 1;
  codexSeat: 0 | 1;
  decks: [unknown[], unknown[]];
  ownDeck: CodexDeckEntry[];
  controller: Controller;
  sessionId: string;
  revision: number;
  frames: Array<{ rev: number; view: GameView }>;
  queue: Promise<unknown>;
  decisions: CodexDecisionRecord[];
  searchedCards: CodexSearchSnapshot[];
  connectedAt?: number;
  lastUsed: number;
  saved: boolean;
};

type CreateBody = {
  decks: [unknown[], unknown[]];
  codexSeat: 0 | 1;
};

type AgentDecisionBody = {
  decisionId: string;
  tokens: string[];
  rationale: CodexRationale;
};

const MATCH_IDLE_MS = 60 * 60 * 1000;
const MAX_MATCHES = 8;
const MAX_FRAMES = 300;

function newConnectionCode(): string {
  return randomBytes(12).toString('base64url');
}

function newMatchId(): string {
  return randomBytes(8).toString('hex');
}

function remotePlayback(count: number): SequencePlayback[] {
  return Array.from({ length: count }, () => 'animate');
}

export class CodexMatchManager {
  private readonly matches = new Map<string, CodexMatch>();
  private readonly byConnectionCode = new Map<string, string>();

  constructor(private readonly controllerFactory: () => Controller = () => new LocalEngineController()) {}

  async create(clientId: string, body: CreateBody): Promise<Record<string, any>> {
    this.prune();
    if (this.matches.size >= MAX_MATCHES) {
      return { ok: false, error: 'Codex対戦数が上限に達しています。しばらくしてからお試しください。' };
    }
    if ((body?.codexSeat !== 0 && body?.codexSeat !== 1)
      || !Array.isArray(body?.decks)
      || body.decks.length !== 2
      || body.decks.some((deck) => !Array.isArray(deck) || deck.length !== 60)) {
      return { ok: false, error: '両プレイヤーの60枚デッキとCodex席を指定してください。' };
    }

    const controller = this.controllerFactory();
    try {
      controller.describeCodexDeck(body.decks[0]);
      controller.describeCodexDeck(body.decks[1]);
    } catch (error) {
      controller.close();
      return { ok: false, error: error instanceof Error ? error.message : 'デッキを読み込めませんでした。' };
    }

    const humanSeat = (1 - body.codexSeat) as 0 | 1;
    const response = await controller.handle({
      type: 'startGame',
      payload: {
        player1: { name: body.codexSeat === 0 ? 'Codex' : 'プレイヤー', deck: body.decks[0], control: 'self' },
        player2: { name: body.codexSeat === 1 ? 'Codex' : 'プレイヤー', deck: body.decks[1], control: 'self', manualOpponent: true },
      },
    });
    if (!response.ok) {
      controller.close();
      return response;
    }

    const match: CodexMatch = {
      id: newMatchId(),
      connectionCode: newConnectionCode(),
      humanClientId: clientId,
      humanSeat,
      codexSeat: body.codexSeat,
      decks: body.decks,
      ownDeck: controller.describeCodexDeck(body.decks[body.codexSeat]),
      controller,
      sessionId: response.sessionId ?? '',
      revision: 0,
      frames: [],
      queue: Promise.resolve(),
      decisions: [],
      searchedCards: [],
      lastUsed: Date.now(),
      saved: false,
    };
    this.appendFrames(match, response);
    this.matches.set(match.id, match);
    this.byConnectionCode.set(match.connectionCode, match.id);
    return {
      ok: true,
      matchId: match.id,
      connectionCode: match.connectionCode,
      humanSeat,
      codexSeat: match.codexSeat,
      revision: match.revision,
      view: maskViewForSeat(response.view, humanSeat),
      sequence: response.sequence?.map((frame) => maskViewForSeat(frame, humanSeat)),
      sequencePlayback: response.sequencePlayback,
      codexConnected: false,
    };
  }

  browserState(clientId: string, matchId: string, since: number): Record<string, any> {
    const match = this.authorizedBrowserMatch(clientId, matchId);
    if (!match) {
      return { ok: false, error: 'Codex対戦が見つからないか、参加者ではありません。' };
    }
    match.lastUsed = Date.now();
    const sequence = match.frames
      .filter((frame) => frame.rev > Math.max(0, Number.isFinite(since) ? since : 0))
      .map((frame) => maskViewForSeat(frame.view, match.humanSeat));
    return {
      ok: true,
      matchId: match.id,
      humanSeat: match.humanSeat,
      codexSeat: match.codexSeat,
      codexConnected: Boolean(match.connectedAt),
      revision: match.revision,
      view: maskViewForSeat(match.controller.currentGameView(), match.humanSeat),
      sequence: sequence.length ? sequence : undefined,
      sequencePlayback: sequence.length ? remotePlayback(sequence.length) : undefined,
    };
  }

  async browserCommand(clientId: string, matchId: string, command: { type: string; payload?: any }): Promise<Record<string, any>> {
    const match = this.authorizedBrowserMatch(clientId, matchId);
    if (!match) {
      return { ok: false, error: 'Codex対戦が見つからないか、参加者ではありません。' };
    }
    return this.enqueue(match, async () => {
      match.lastUsed = Date.now();
      if (command.type === 'startGame' || command.type === 'undo') {
        return { ok: false, error: 'Codex対戦ではこの操作は使えません。' };
      }
      const acting = this.actingSeat(match);
      if (command.type !== 'concede' && acting === match.codexSeat) {
        return { ok: false, error: 'Codexの操作待ちです。' };
      }
      if (command.type !== 'concede' && acting !== match.humanSeat) {
        return { ok: false, error: '現在は操作できません。' };
      }
      const response = await match.controller.handle({
        type: command.type,
        payload: { ...(command.payload ?? {}), sessionId: match.sessionId },
      });
      if (response.ok) {
        this.appendFrames(match, response);
      }
      return this.maskResponse(response, match, match.humanSeat, response.ok ? response.sequencePlayback : undefined);
    });
  }

  agentState(connectionCode: string): Record<string, any> {
    const match = this.matchForCode(connectionCode);
    if (!match) {
      return { ok: false, error: 'Codex接続コードが無効か、期限切れです。' };
    }
    match.lastUsed = Date.now();
    match.connectedAt ??= Date.now();
    const search = match.controller.currentCodexSearch(match.codexSeat);
    if (search && !match.searchedCards.some((item) => item.decisionId === search.decisionId)) {
      match.searchedCards.push(search);
    }
    const rawView = match.controller.currentGameView();
    const decision = match.controller.currentCodexDecision(match.codexSeat);
    return {
      ok: true,
      status: rawView.phase === 7 ? 'finished' : decision ? 'decision' : 'waiting-human',
      matchId: match.id,
      codexSeat: match.codexSeat,
      revision: match.revision,
      view: maskViewForCodex(rawView, match.codexSeat),
      decision,
      ownDeck: match.ownDeck,
      knowledge: { searches: match.searchedCards },
    };
  }

  async agentDecision(connectionCode: string, body: AgentDecisionBody): Promise<Record<string, any>> {
    const match = this.matchForCode(connectionCode);
    if (!match) {
      return { ok: false, error: 'Codex接続コードが無効か、期限切れです。' };
    }
    match.connectedAt ??= Date.now();
    return this.enqueue(match, async () => {
      match.lastUsed = Date.now();
      const current = match.controller.currentCodexDecision(match.codexSeat);
      if (!current) {
        return { ok: false, error: 'Codexの手番ではありません。' };
      }
      if (current.decisionId !== body?.decisionId) {
        return { ok: false, error: '局面が更新されています。最新の合法手を取得してください。' };
      }
      const response = await match.controller.applyCodexDecision(match.codexSeat, body.decisionId, body.tokens ?? []);
      if (response.ok) {
        match.decisions.push({
          revision: match.revision,
          turn: response.view.turn,
          decisionId: body.decisionId,
          tokens: [...body.tokens],
          rationale: body.rationale,
          createdAt: new Date().toISOString(),
        });
        this.appendFrames(match, response);
      }
      return this.maskResponse(response, match, match.codexSeat, response.ok ? response.sequencePlayback : undefined, true);
    });
  }

  leave(clientId: string, matchId: string): { ok: boolean } {
    const match = this.authorizedBrowserMatch(clientId, matchId);
    if (match) {
      this.deleteMatch(match);
    }
    return { ok: true };
  }

  closeAll(): void {
    for (const match of this.matches.values()) {
      match.controller.close();
    }
    this.matches.clear();
    this.byConnectionCode.clear();
  }

  prune(now = Date.now()): void {
    for (const match of this.matches.values()) {
      if (now - match.lastUsed > MATCH_IDLE_MS) {
        this.deleteMatch(match);
      }
    }
  }

  private appendFrames(match: CodexMatch, response: Extract<EngineResponse, { ok: true }>): void {
    const views = response.sequence?.length ? response.sequence : [response.view];
    for (const frame of views) {
      match.revision += 1;
      match.frames.push({ rev: match.revision, view: frame });
    }
    if (match.frames.length > MAX_FRAMES) {
      match.frames = match.frames.slice(-MAX_FRAMES);
    }
  }

  private actingSeat(match: CodexMatch): number {
    const view = match.controller.currentGameView();
    return view.prompts[0]?.playerIndex ?? view.activePlayerIndex;
  }

  private maskResponse(
    response: EngineResponse,
    match: CodexMatch,
    seat: number,
    sequencePlayback?: SequencePlayback[],
    codex = false,
  ): Record<string, any> {
    const mask = codex ? maskViewForCodex : maskViewForSeat;
    if (!response.ok) {
      return { ...response, view: response.view ? mask(response.view, seat) : undefined, revision: match.revision };
    }
    return {
      ...response,
      sessionId: undefined,
      view: mask(response.view, seat),
      sequence: response.sequence?.map((frame) => mask(frame, seat)),
      sequencePlayback,
      revision: match.revision,
    };
  }

  private authorizedBrowserMatch(clientId: string, matchId: string): CodexMatch | undefined {
    const match = this.matches.get(matchId);
    return match?.humanClientId === clientId ? match : undefined;
  }

  private matchForCode(connectionCode: string): CodexMatch | undefined {
    const id = this.byConnectionCode.get(connectionCode.trim());
    return id ? this.matches.get(id) : undefined;
  }

  private enqueue<T>(match: CodexMatch, task: () => Promise<T>): Promise<T> {
    const next = match.queue.then(task, task);
    match.queue = next.catch(() => undefined);
    return next;
  }

  private deleteMatch(match: CodexMatch): void {
    match.controller.close();
    this.matches.delete(match.id);
    this.byConnectionCode.delete(match.connectionCode);
  }
}

export const codexMatchManager = new CodexMatchManager();
setInterval(() => codexMatchManager.prune(), 5 * 60 * 1000).unref();
