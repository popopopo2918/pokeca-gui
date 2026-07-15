import { randomBytes } from 'node:crypto';
import type { EngineResponse, GameView } from '../lib/game/types';
import type {
  CodexDeckEntry,
  CodexEngineDecision,
  CodexRationale,
  CodexSearchSnapshot,
  SelfPlayDecisionRecord,
} from './codexProtocol';
import { sanitizeCodexRationale } from './codexProtocol';
import { LocalEngineController } from './localEngine';
import { calculateSelfPlayMetrics } from './selfPlayMetrics';
import { maskViewForCodex } from './viewMask';

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

type CreateBody = {
  decks: [unknown[], unknown[]];
  names?: [string, string];
  alakazamSeat: 0 | 1;
};

type DecisionBody = {
  decisionId: string;
  tokens: string[];
  rationale: CodexRationale;
};

type SelfPlayMatch = {
  id: string;
  coordinatorCode: string;
  seatCodes: [string, string];
  controller: Controller;
  ownDecks: [CodexDeckEntry[], CodexDeckEntry[]];
  alakazamSeat: 0 | 1;
  sessionId: string;
  revision: number;
  queue: Promise<unknown>;
  decisions: SelfPlayDecisionRecord[];
  searchedCards: [CodexSearchSnapshot[], CodexSearchSnapshot[]];
  playerTurns: [number, number];
  observedActiveSeat?: 0 | 1;
  connected: [boolean, boolean];
  lastUsed: number;
  saved: boolean;
  replayFile?: string;
  replayId?: string;
};

const MATCH_IDLE_MS = 60 * 60 * 1000;
const MAX_MATCHES = 8;

function newCode(): string {
  return randomBytes(12).toString('base64url');
}

function newMatchId(): string {
  return randomBytes(8).toString('hex');
}

export class CodexSelfPlayManager {
  private readonly matches = new Map<string, SelfPlayMatch>();
  private readonly bySeatCode = new Map<string, { matchId: string; seat: 0 | 1 }>();
  private readonly byCoordinatorCode = new Map<string, string>();

  constructor(private readonly controllerFactory: () => Controller = () => new LocalEngineController()) {}

  async create(body: CreateBody): Promise<Record<string, any>> {
    this.prune();
    if (this.matches.size >= MAX_MATCHES) {
      return { ok: false, error: 'Codex自己対戦数が上限に達しています。' };
    }
    if ((body?.alakazamSeat !== 0 && body?.alakazamSeat !== 1)
      || !Array.isArray(body?.decks)
      || body.decks.length !== 2
      || body.decks.some((deck) => !Array.isArray(deck) || deck.length !== 60)) {
      return { ok: false, error: '両席の60枚デッキとフーディン席を指定してください。' };
    }
    const controller = this.controllerFactory();
    let ownDecks: [CodexDeckEntry[], CodexDeckEntry[]];
    try {
      ownDecks = [controller.describeCodexDeck(body.decks[0]), controller.describeCodexDeck(body.decks[1])];
    } catch (error) {
      controller.close();
      return { ok: false, error: error instanceof Error ? error.message : 'デッキを読み込めませんでした。' };
    }
    const names = body.names ?? ['Codex 1', 'Codex 2'];
    const response = await controller.handle({
      type: 'startGame',
      payload: {
        player1: { name: names[0], deck: body.decks[0], control: 'self' },
        player2: { name: names[1], deck: body.decks[1], control: 'self', manualOpponent: true },
      },
    });
    if (!response.ok) {
      controller.close();
      return response;
    }
    const match: SelfPlayMatch = {
      id: newMatchId(),
      coordinatorCode: newCode(),
      seatCodes: [newCode(), newCode()],
      controller,
      ownDecks,
      alakazamSeat: body.alakazamSeat,
      sessionId: response.sessionId ?? '',
      revision: response.sequence?.length || 1,
      queue: Promise.resolve(),
      decisions: [],
      searchedCards: [[], []],
      playerTurns: [0, 0],
      connected: [false, false],
      lastUsed: Date.now(),
      saved: false,
    };
    this.matches.set(match.id, match);
    this.byCoordinatorCode.set(match.coordinatorCode, match.id);
    this.bySeatCode.set(match.seatCodes[0], { matchId: match.id, seat: 0 });
    this.bySeatCode.set(match.seatCodes[1], { matchId: match.id, seat: 1 });
    return {
      ok: true,
      matchId: match.id,
      coordinatorCode: match.coordinatorCode,
      seatCodes: match.seatCodes,
      revision: match.revision,
      alakazamSeat: match.alakazamSeat,
    };
  }

  seatState(code: string): Record<string, any> {
    const authorized = this.matchForSeatCode(code);
    if (!authorized) return { ok: false, error: '自己対戦の席コードが無効か、期限切れです。' };
    const { match, seat } = authorized;
    match.lastUsed = Date.now();
    match.connected[seat] = true;
    const rawView = match.controller.currentGameView();
    this.observeActiveSeat(match, rawView);
    const search = match.controller.currentCodexSearch(seat);
    if (search && !match.searchedCards[seat].some((item) => item.decisionId === search.decisionId)) {
      match.searchedCards[seat].push(search);
    }
    const decision = match.controller.currentCodexDecision(seat);
    return {
      ok: true,
      status: rawView.phase === 7 ? 'finished' : decision ? 'decision' : 'waiting-opponent',
      matchId: match.id,
      seat,
      alakazamSeat: match.alakazamSeat,
      playerTurn: match.playerTurns[seat],
      revision: match.revision,
      view: maskViewForCodex(rawView, seat),
      decision,
      ownDeck: match.ownDecks[seat],
      knowledge: { searches: match.searchedCards[seat] },
    };
  }

  async seatDecision(code: string, body: DecisionBody): Promise<Record<string, any>> {
    const authorized = this.matchForSeatCode(code);
    if (!authorized) return { ok: false, error: '自己対戦の席コードが無効か、期限切れです。' };
    const { match, seat } = authorized;
    return this.enqueue(match, async () => {
      match.lastUsed = Date.now();
      const before = match.controller.currentGameView();
      this.observeActiveSeat(match, before);
      const current = match.controller.currentCodexDecision(seat);
      if (!current) return { ok: false, error: 'この席の手番ではありません。', revision: match.revision };
      if (current.decisionId !== body?.decisionId) {
        return { ok: false, error: '局面が更新されています。最新の合法手を取得してください。', revision: match.revision };
      }
      const rationale = sanitizeCodexRationale(body?.rationale);
      if (!rationale) return { ok: false, error: '判断理由は4項目すべて入力してください。', revision: match.revision };
      if (!Array.isArray(body?.tokens)) return { ok: false, error: '合法手トークンを指定してください。', revision: match.revision };
      const selected = selectedOptions(current, body.tokens);
      if (!selected) return { ok: false, error: '現在の合法手トークンだけを指定してください。', revision: match.revision };
      const response = await match.controller.applyCodexDecision(seat, body.decisionId, body.tokens);
      if (!response.ok) return { ...response, revision: match.revision };
      this.appendRevision(match, response);
      match.decisions.push({
        seat,
        playerTurn: match.playerTurns[seat],
        revision: match.revision,
        turn: response.view.turn,
        decisionId: body.decisionId,
        tokens: [...body.tokens],
        prompt: current.prompt,
        selected,
        ownPrizesLeftBefore: before.players[seat]?.prizesLeft ?? 0,
        ownPrizesLeftAfter: response.view.players[seat]?.prizesLeft ?? 0,
        rationale,
        createdAt: new Date().toISOString(),
      });
      this.observeActiveSeat(match, response.view);
      this.maybeSaveFinished(match, response.view);
      return {
        ok: true,
        revision: match.revision,
        view: maskViewForCodex(response.view, seat),
        sequence: response.sequence?.map((frame) => maskViewForCodex(frame, seat)),
        sequencePlayback: response.sequencePlayback,
      };
    });
  }

  progress(code: string): Record<string, any> {
    const match = this.matchForCoordinatorCode(code);
    if (!match) return { ok: false, error: '自己対戦の管理コードが無効か、期限切れです。' };
    const view = match.controller.currentGameView();
    return {
      ok: true,
      matchId: match.id,
      revision: match.revision,
      activeSeat: view.prompts[0]?.playerIndex ?? view.activePlayerIndex,
      finished: view.phase === 7,
      connected: match.connected,
      decisionCount: match.decisions.length,
    };
  }

  summary(code: string): Record<string, any> {
    const match = this.matchForCoordinatorCode(code);
    if (!match) return { ok: false, error: '自己対戦の管理コードが無効か、期限切れです。' };
    const view = match.controller.currentGameView();
    if (view.phase !== 7) return { ok: false, status: 'in-progress', revision: match.revision };
    this.maybeSaveFinished(match, view);
    return {
      ok: true,
      status: 'finished',
      matchId: match.id,
      result: view.winner,
      alakazamSeat: match.alakazamSeat,
      replayFile: match.replayFile,
      replayId: match.replayId,
      decisions: match.decisions,
      publicTimeline: publicView(view).actionTimeline ?? [],
      metrics: calculateSelfPlayMetrics(match.decisions, match.alakazamSeat, view.winner),
    };
  }

  closeAll(): void {
    for (const match of this.matches.values()) match.controller.close();
    this.matches.clear();
    this.bySeatCode.clear();
    this.byCoordinatorCode.clear();
  }

  prune(now = Date.now()): void {
    for (const match of this.matches.values()) {
      if (now - match.lastUsed > MATCH_IDLE_MS) this.deleteMatch(match);
    }
  }

  private observeActiveSeat(match: SelfPlayMatch, view: GameView): void {
    if (view.phase === 7) return;
    const active = (view.prompts[0]?.playerIndex ?? view.activePlayerIndex) as 0 | 1;
    if (active !== 0 && active !== 1) return;
    if (match.observedActiveSeat !== active) {
      match.playerTurns[active] += 1;
      match.observedActiveSeat = active;
    }
  }

  private appendRevision(match: SelfPlayMatch, response: Extract<EngineResponse, { ok: true }>): void {
    match.revision += response.sequence?.length || 1;
  }

  private maybeSaveFinished(match: SelfPlayMatch, view: GameView): void {
    if (view.phase !== 7 || match.saved) return;
    const result = match.controller.saveReplay({
      selfPlay: true,
      alakazamSeat: match.alakazamSeat,
      selfPlayDecisions: match.decisions,
      publicTimeline: publicView(view).actionTimeline ?? [],
      result: view.winner,
    }) as Record<string, any>;
    if (result.ok) {
      match.replayFile = result.file;
      match.replayId = result.id;
      match.saved = true;
    }
  }

  private matchForSeatCode(code: string): { match: SelfPlayMatch; seat: 0 | 1 } | undefined {
    const authorized = this.bySeatCode.get(String(code ?? '').trim());
    const match = authorized ? this.matches.get(authorized.matchId) : undefined;
    return authorized && match ? { match, seat: authorized.seat } : undefined;
  }

  private matchForCoordinatorCode(code: string): SelfPlayMatch | undefined {
    const id = this.byCoordinatorCode.get(String(code ?? '').trim());
    return id ? this.matches.get(id) : undefined;
  }

  private enqueue<T>(match: SelfPlayMatch, task: () => Promise<T>): Promise<T> {
    const next = match.queue.then(task, task);
    match.queue = next.catch(() => undefined);
    return next;
  }

  private deleteMatch(match: SelfPlayMatch): void {
    match.controller.close();
    this.matches.delete(match.id);
    this.byCoordinatorCode.delete(match.coordinatorCode);
    this.bySeatCode.delete(match.seatCodes[0]);
    this.bySeatCode.delete(match.seatCodes[1]);
  }
}

function selectedOptions(decision: CodexEngineDecision, tokens: string[]) {
  const byToken = new Map(decision.options.map((option) => [option.token, option]));
  const options = tokens.map((token) => byToken.get(token));
  if (options.some((option) => !option)) return null;
  return options.map((option) => ({
    kind: option!.kind,
    label: option!.label,
    ...(option!.source ? { source: option!.source } : {}),
    ...(option!.target ? { target: option!.target } : {}),
  }));
}

function publicView(view: GameView): GameView {
  return maskViewForCodex(maskViewForCodex(view, 0), 1);
}

export const codexSelfPlayManager = new CodexSelfPlayManager();
setInterval(() => codexSelfPlayManager.prune(), 5 * 60 * 1000).unref();
