import { describe, expect, it } from 'vitest';
import type { CodexEngineDecision, CodexSearchSnapshot } from './codexProtocol';
import type { EngineResponse, GameView } from '../lib/game/types';
import { CodexSelfPlayManager } from './codexSelfPlay';

function view(actingSeat: 0 | 1, turn = 1, finished = false): GameView {
  const slot = (ownerIndex: number) => ({
    ownerIndex,
    slot: 'active' as const,
    index: 0,
    target: { player: 2, slot: 1, index: 0 },
    empty: true,
    cards: [],
    damage: 0,
    hp: 0,
    retreat: [],
    energy: [],
    tools: [],
    specialConditions: [],
  });
  return {
    ready: true,
    phase: finished ? 7 : 3,
    phaseLabel: finished ? '対戦終了' : 'プレイヤーの番',
    turn,
    activePlayerIndex: actingSeat,
    winner: finished ? 0 : undefined,
    players: [0, 1].map((index) => ({
      index,
      id: index,
      name: `P${index + 1}`,
      hand: [{ name: `hand-${index}`, fullName: `hand-${index}` }],
      deckCount: 46,
      discard: [],
      lostZone: [],
      stadium: [],
      playZone: [],
      prizesLeft: 6,
      prizeContents: [{ name: `prize-${index}`, fullName: `prize-${index}` }],
      active: slot(index),
      bench: [],
      playableCardIds: [],
    })),
    prompts: finished ? [] : [{
      id: turn,
      className: 'CabtPrompt',
      type: 'cabt-select',
      playerId: actingSeat,
      playerIndex: actingSeat,
      supported: true,
      resultSchema: 'cardIndexes',
      fields: {},
    }],
    logs: [],
    actionTimeline: [],
    events: [],
  };
}

function rationale() {
  return {
    action: 'ターンエンド',
    goal: '次の番へ進める',
    evidence: '追加の有効行動がない',
    alternative: '不要なカード使用を見送る',
  };
}

function createFakeController(
  finishAfter = Number.POSITIVE_INFINITY,
  turnSequence?: number[],
) {
  let current = view(0, turnSequence?.[0] ?? 1);
  let decisionNumber = 1;
  let applied = 0;
  return {
    startedWith: undefined as any,
    appliedDecisions: [] as Array<{ seat: number; tokens: string[] }>,
    searchSnapshots: [null, null] as Array<CodexSearchSnapshot | null>,
    savedMetadata: undefined as Record<string, unknown> | undefined,
    closed: false,
    async handle(command: any): Promise<EngineResponse> {
      if (command.type === 'startGame') {
        this.startedWith = command.payload;
        return { ok: true, view: current, sessionId: 'session', sequence: [current], sequencePlayback: ['instant'] };
      }
      if (command.type === 'concede') {
        current = view((1 - command.payload.playerIndex) as 0 | 1, decisionNumber, true);
        return { ok: true, view: current };
      }
      return { ok: true, view: current };
    },
    currentGameView() {
      return current;
    },
    currentCodexDecision(seat: number): CodexEngineDecision | null {
      if (current.phase === 7 || current.activePlayerIndex !== seat) return null;
      const decisionId = `d${decisionNumber}`;
      return {
        decisionId,
        playerIndex: seat,
        prompt: '操作を選んでください。',
        minCount: 1,
        maxCount: 1,
        options: [{ token: `${decisionId}-o0`, kind: 'end', label: 'ターンエンド' }],
      };
    },
    async applyCodexDecision(seat: number, decisionId: string, tokens: string[]): Promise<EngineResponse> {
      if (current.activePlayerIndex !== seat || decisionId !== `d${decisionNumber}`) {
        return { ok: false, error: '局面が更新されています。最新の合法手を取得してください。' };
      }
      this.appliedDecisions.push({ seat, tokens });
      applied += 1;
      decisionNumber += 1;
      const finished = applied >= finishAfter;
      current = view((1 - seat) as 0 | 1, turnSequence?.[applied] ?? decisionNumber, finished);
      return { ok: true, view: current, sequence: [current], sequencePlayback: ['instant'] };
    },
    describeCodexDeck(cards: unknown[]) {
      const id = Number(cards[0]);
      return [{ id, name: `テストカード${id}`, count: cards.length }];
    },
    currentCodexSearch(seat: number) {
      return this.searchSnapshots[seat];
    },
    saveReplay(metadata?: Record<string, unknown>) {
      this.savedMetadata = metadata;
      return { ok: true, id: 'self-play-replay', file: 'self-play-replay.json' };
    },
    close() {
      this.closed = true;
    },
  };
}

async function startedMatch(
  finishAfter = Number.POSITIVE_INFINITY,
  turnSequence?: number[],
) {
  const fake = createFakeController(finishAfter, turnSequence);
  const manager = new CodexSelfPlayManager(() => fake as never);
  const created = await manager.create({
    decks: [Array(60).fill(1), Array(60).fill(2)],
    names: ['フーディン', '対戦相手'],
    alakazamSeat: 0,
  });
  return { fake, manager, created };
}

describe('CodexSelfPlayManager', () => {
  it('両席を手動で開始し異なるコードと公平な局面を返す', async () => {
    const { fake, manager, created } = await startedMatch();

    expect(created.ok).toBe(true);
    expect(created.seatCodes[0]).not.toBe(created.seatCodes[1]);
    expect(created.coordinatorCode).not.toBe(created.seatCodes[0]);
    expect(fake.startedWith.player1.control).toBe('self');
    expect(fake.startedWith.player2.control).toBe('self');
    for (const seat of [0, 1] as const) {
      const state = manager.seatState(created.seatCodes[seat]);
      expect(state.view.players[1 - seat].hand[0].name).toBe('未公開');
      expect(state.view.players[0].prizeContents).toBeUndefined();
      expect(state.view.players[1].prizeContents).toBeUndefined();
      expect(state.ownDeck).toEqual([{ id: seat + 1, name: `テストカード${seat + 1}`, count: 60 }]);
    }
  });

  it('両席が自分の手番だけ判断でき自席ターンを独立して数える', async () => {
    const { manager, created } = await startedMatch();

    const seat0 = manager.seatState(created.seatCodes[0]);
    const seat1 = manager.seatState(created.seatCodes[1]);
    expect(seat0.status).toBe('decision');
    expect(seat0.playerTurn).toBe(1);
    expect(seat1.status).toBe('waiting-opponent');
    await manager.seatDecision(created.seatCodes[0], {
      decisionId: seat0.decision.decisionId,
      tokens: [seat0.decision.options[0].token],
      rationale: rationale(),
    });
    expect(manager.seatState(created.seatCodes[1])).toMatchObject({ status: 'decision', playerTurn: 1 });
  });

  it('対戦準備中の席交代を自席ターンとして数えない', async () => {
    const { manager, created } = await startedMatch(Number.POSITIVE_INFINITY, [0, 0, 1]);

    const setupSeat0 = manager.seatState(created.seatCodes[0]);
    expect(setupSeat0).toMatchObject({ status: 'decision', playerTurn: 0 });
    await manager.seatDecision(created.seatCodes[0], {
      decisionId: setupSeat0.decision.decisionId,
      tokens: [setupSeat0.decision.options[0].token],
      rationale: rationale(),
    });

    const setupSeat1 = manager.seatState(created.seatCodes[1]);
    expect(setupSeat1).toMatchObject({ status: 'decision', playerTurn: 0 });
    await manager.seatDecision(created.seatCodes[1], {
      decisionId: setupSeat1.decision.decisionId,
      tokens: [setupSeat1.decision.options[0].token],
      rationale: rationale(),
    });

    expect(manager.seatState(created.seatCodes[0])).toMatchObject({ status: 'decision', playerTurn: 1 });
  });

  it('重複判断は一手だけ適用して同じrevisionを返す', async () => {
    const { fake, manager, created } = await startedMatch();
    const state = manager.seatState(created.seatCodes[0]);
    const body = {
      decisionId: state.decision.decisionId,
      tokens: [state.decision.options[0].token],
      rationale: rationale(),
    };

    const [first, second] = await Promise.all([
      manager.seatDecision(created.seatCodes[0], body),
      manager.seatDecision(created.seatCodes[0], body),
    ]);

    expect([first.ok, second.ok].filter(Boolean)).toHaveLength(1);
    expect(first.revision).toBe(second.revision);
    expect(fake.appliedDecisions).toHaveLength(1);
  });

  it('終了後だけ管理コードで全判断とリプレイを返す', async () => {
    const { fake, manager, created } = await startedMatch(1);
    expect(manager.summary(created.coordinatorCode)).toMatchObject({ ok: false, status: 'in-progress' });
    const state = manager.seatState(created.seatCodes[0]);
    await manager.seatDecision(created.seatCodes[0], {
      decisionId: state.decision.decisionId,
      tokens: [state.decision.options[0].token],
      rationale: rationale(),
    });

    const summary = manager.summary(created.coordinatorCode);
    expect(summary).toMatchObject({
      ok: true,
      status: 'finished',
      result: 0,
      replayFile: 'self-play-replay.json',
      decisions: [expect.objectContaining({ seat: 0, playerTurn: 1, prompt: '操作を選んでください。' })],
    });
    expect(JSON.stringify(fake.savedMetadata)).not.toContain(created.coordinatorCode);
    expect(JSON.stringify(fake.savedMetadata)).not.toContain(created.seatCodes[0]);
    expect(manager.summary('wrong-code')).toMatchObject({ ok: false });
  });

  it('席の投了を理由付きの一手として記録する', async () => {
    const { manager, created } = await startedMatch();

    const response = await manager.seatConcede(created.seatCodes[1], {
      action: '投了',
      goal: '勝ち筋がない試合を終了する',
      evidence: '次の相手の攻撃を防ぐ合法手がない',
      alternative: 'ターンを続けても敗北が確定している',
    });

    expect(response).toMatchObject({ ok: true });
    expect(manager.summary(created.coordinatorCode)).toMatchObject({
      ok: true,
      result: 0,
      decisions: [expect.objectContaining({
        seat: 1,
        selected: [{ kind: 'other', label: '投了' }],
      })],
    });
  });
});
