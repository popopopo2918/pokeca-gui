import { describe, expect, it } from 'vitest';
import type { CodexEngineDecision, CodexSearchSnapshot } from './codexProtocol';
import type { EngineResponse, GameView } from '../lib/game/types';
import { CodexMatchManager } from './codexMatches';

function view(actingSeat: number, finished = false): GameView {
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
    turn: 1,
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
      id: 1,
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

function createFakeController(initialActingSeat = 1) {
  let current = view(initialActingSeat);
  let decisionId = 'd1';
  return {
    startedWith: undefined as any,
    appliedDecisions: [] as string[][],
    searchSnapshot: null as CodexSearchSnapshot | null,
    closed: false,
    savedMetadata: undefined as Record<string, unknown> | undefined,
    async handle(command: any): Promise<EngineResponse> {
      if (command.type === 'startGame') {
        this.startedWith = command.payload;
        return { ok: true, view: current, sessionId: 'session', sequence: [current], sequencePlayback: ['instant'] };
      }
      if (command.type === 'concede') {
        current = view(initialActingSeat, true);
        return { ok: true, view: current };
      }
      return { ok: true, view: current };
    },
    currentGameView() {
      return current;
    },
    currentCodexDecision(playerIndex: number): CodexEngineDecision | null {
      if (current.phase === 7 || current.prompts[0]?.playerIndex !== playerIndex) return null;
      return {
        decisionId,
        playerIndex,
        prompt: '操作を選んでください。',
        minCount: 1,
        maxCount: 1,
        options: [{ token: `${decisionId}-o0`, kind: 'end', label: 'ターンエンド' }],
      };
    },
    async applyCodexDecision(_playerIndex: number, receivedDecisionId: string, tokens: string[]): Promise<EngineResponse> {
      if (receivedDecisionId !== decisionId) {
        return { ok: false, error: '局面が更新されています。最新の合法手を取得してください。' };
      }
      this.appliedDecisions.push(tokens);
      decisionId = 'd2';
      current = view(0);
      return { ok: true, view: current, sequence: [current], sequencePlayback: ['instant'] };
    },
    describeCodexDeck(cards: unknown[]) {
      const id = Number(cards[0]);
      return [{ id, name: `テストカード${id}`, count: cards.length }];
    },
    currentCodexSearch() {
      return this.searchSnapshot;
    },
    saveReplay(metadata?: Record<string, unknown>) {
      this.savedMetadata = metadata;
      return { ok: true, id: 'replay', file: 'replay.json' };
    },
    close() {
      this.closed = true;
    },
  };
}

async function startedMatch(options: { actingSeat: number; codexSeat: 0 | 1 }) {
  const fake = createFakeController(options.actingSeat);
  const manager = new CodexMatchManager(() => fake as never);
  const created = await manager.create('human-client', {
    decks: [Array(60).fill(1), Array(60).fill(2)],
    codexSeat: options.codexSeat,
  });
  return { manager, created, fake };
}

describe('CodexMatchManager', () => {
  it('starts both CABT seats manual and returns a fair Codex view', async () => {
    const { manager, created, fake } = await startedMatch({ actingSeat: 1, codexSeat: 1 });

    expect(created.ok).toBe(true);
    expect(fake.startedWith.player1.control).toBe('self');
    expect(fake.startedWith.player2.control).toBe('self');
    const agent = manager.agentState(created.connectionCode!);
    expect(agent.status).toBe('decision');
    expect(agent.view.players[0].hand[0].name).toBe('未公開');
    expect(agent.view.players[1].hand[0].name).not.toBe('未公開');
    expect(agent.view.players[0].prizeContents).toBeUndefined();
    expect(agent.view.players[1].prizeContents).toBeUndefined();
    expect(agent.ownDeck).toEqual([{ id: 2, name: 'テストカード2', count: 60 }]);
    expect(manager.browserState('human-client', created.matchId!, 0).codexConnected).toBe(true);
  });

  it('rejects human commands during the Codex turn', async () => {
    const { manager, created } = await startedMatch({ actingSeat: 1, codexSeat: 1 });

    await expect(manager.browserCommand('human-client', created.matchId!, { type: 'passTurn' }))
      .resolves.toMatchObject({ ok: false, error: 'Codexの操作待ちです。' });
  });

  it('serializes duplicate Codex decisions and applies only one', async () => {
    const { manager, created, fake } = await startedMatch({ actingSeat: 1, codexSeat: 1 });
    const body = { decisionId: 'd1', tokens: ['d1-o0'], rationale: rationale() };

    const [first, second] = await Promise.all([
      manager.agentDecision(created.connectionCode!, body),
      manager.agentDecision(created.connectionCode!, body),
    ]);

    expect([first.ok, second.ok].filter(Boolean)).toHaveLength(1);
    expect(fake.appliedDecisions).toHaveLength(1);
  });

  it('remembers only deck cards exposed by a legitimate Codex search prompt', async () => {
    const { manager, created, fake } = await startedMatch({ actingSeat: 1, codexSeat: 1 });
    fake.searchSnapshot = {
      decisionId: 'd1',
      prompt: '山札からポケモンを選んでください。',
      cards: [{ id: 101, name: 'ケーシィ' }, { id: 102, name: 'ユンゲラー' }],
    };

    const agent = manager.agentState(created.connectionCode!);

    expect(agent.knowledge.searches).toEqual([fake.searchSnapshot]);
    expect(agent).not.toHaveProperty('prizeContents');
  });

  it('stores sanitized rationale and includes it in the finished replay metadata', async () => {
    const { manager, created, fake } = await startedMatch({ actingSeat: 1, codexSeat: 1 });
    const longEvidence = `  ${'公開情報'.repeat(200)}  `;
    await manager.agentDecision(created.connectionCode!, {
      decisionId: 'd1',
      tokens: ['d1-o0'],
      rationale: {
        action: '  ターンエンド  ',
        goal: '次の番へ進める',
        evidence: longEvidence,
        alternative: '不要なカード使用を見送る',
      },
    });

    await manager.browserCommand('human-client', created.matchId!, {
      type: 'concede',
      payload: { playerIndex: 0 },
    });

    const metadata = fake.savedMetadata as any;
    expect(metadata.codexDecisions[0].rationale.action).toBe('ターンエンド');
    expect(metadata.codexDecisions[0].rationale.evidence.length).toBe(500);
    expect(JSON.stringify(metadata)).not.toContain(created.connectionCode);
    expect(manager.summary(created.connectionCode!)).toMatchObject({
      ok: true,
      result: 0,
      replayFile: 'replay.json',
      decisions: [expect.objectContaining({ decisionId: 'd1' })],
    });
  });

  it('rejects a decision without all four rationale fields', async () => {
    const { manager, created, fake } = await startedMatch({ actingSeat: 1, codexSeat: 1 });

    const response = await manager.agentDecision(created.connectionCode!, {
      decisionId: 'd1',
      tokens: ['d1-o0'],
      rationale: { ...rationale(), evidence: '   ' },
    });

    expect(response).toMatchObject({ ok: false, error: '判断理由は4項目すべて入力してください。' });
    expect(fake.appliedDecisions).toHaveLength(0);
  });
});
