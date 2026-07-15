import { describe, expect, it } from 'vitest';
import { LocalEngineController } from './localEngine';
import { SlotType, targetFor } from '../lib/game/types';
import { CabtAreaType, CabtLogType, CabtOptionType, CabtSelectContext } from '../lib/cabt/types';

describe('LocalEngineController', () => {
  process.env.CABT_ENGINE_MODE = 'demo';

  it('starts a CABT-shaped demo game and exposes a playable view', async () => {
    const engine = new LocalEngineController();
    const res = await engine.handle({
      type: 'startGame',
      payload: {
        player1: { deck: [] },
        player2: { deck: [] },
      },
    });

    expect(res.ok).toBe(true);
    if (!res.ok) return;
    expect(res.view.players).toHaveLength(2);
    expect(res.view.phaseLabel).toBe('プレイヤーの番');
    expect(res.view.players[0]?.active.pokemon?.name).toBe('Charmander');
    expect(res.view.players[0]?.availableActions?.active?.attacks[0]?.name).toBe('Ember');
  });

  it('accepts existing UI commands through the CABT adapter scaffold', async () => {
    const engine = new LocalEngineController();
    let res = await engine.handle({ type: 'startGame' });
    expect(res.ok).toBe(true);
    if (!res.ok) return;

    res = await engine.handle({
      type: 'playCard',
      payload: {
        playerIndex: 0,
        handIndex: 0,
        target: targetFor(0, 0, SlotType.ACTIVE),
      },
    });
    expect(res.ok).toBe(true);
    if (!res.ok) return;
    expect(res.view.players[0]?.active.energy).toHaveLength(2);

    res = await engine.handle({ type: 'attack', payload: { playerIndex: 0, attack: 'Ember' } });
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.view.activePlayerIndex).toBe(1);
      expect(res.view.logs.at(-2)?.message).toContain('Ember');
    }
  });

  it('starts self-vs-self without sending agent paths to the bridge', async () => {
    const engine = new LocalEngineController() as any;
    let bridgePayload: Record<string, unknown> | undefined;
    engine.bridge = {
      stop: () => {},
      request: async (payload: Record<string, unknown>) => {
        bridgePayload = payload;
        return { ok: true, observation: null, cards: [], attacks: [] };
      },
    };

    const res = await engine.start({
      player1: { deck: Array(60).fill(1), control: 'self' },
      player2: { deck: Array(60).fill(2), control: 'self', agentId: 'mega-lucario-ex' },
    });

    expect(res.ok).toBe(true);
    expect(bridgePayload?.agentControlled).toEqual([false, false]);
    expect(bridgePayload?.agentPaths).toEqual([undefined, undefined]);
  });

  it('wires agent-controlled players to their selected agent paths', async () => {
    const engine = new LocalEngineController() as any;
    let bridgePayload: Record<string, unknown> | undefined;
    engine.bridge = {
      stop: () => {},
      request: async (payload: Record<string, unknown>) => {
        bridgePayload = payload;
        return { ok: true, observation: null, cards: [], attacks: [] };
      },
    };

    const res = await engine.start({
      player1: { deck: Array(60).fill(1), control: 'agent', agentId: 'first-legal' },
      player2: { deck: Array(60).fill(2), control: 'agent', agentId: 'mega-lucario-ex' },
    });

    expect(res.ok).toBe(true);
    expect(bridgePayload?.agentControlled).toEqual([true, true]);
    expect(bridgePayload?.agentPaths).toEqual([undefined, 'public/agents/mega-lucario-ex/main.py']);
  });

  it('matches real CABT main-phase hand options with omitted source fields', () => {
    const engine = new LocalEngineController() as any;
    const payload = {
      playerIndex: 0,
      handIndex: 3,
      target: targetFor(0, 0, SlotType.ACTIVE),
    };

    expect(engine.matchesPlayCardOption({ type: CabtOptionType.PLAY, index: 3 }, payload)).toBe(true);
    expect(engine.matchesPlayCardOption({
      type: CabtOptionType.ATTACH,
      area: CabtAreaType.HAND,
      index: 3,
      inPlayArea: CabtAreaType.ACTIVE,
      inPlayIndex: 0,
    }, payload)).toBe(true);
    expect(engine.matchesPlayCardOption({
      type: CabtOptionType.ATTACH,
      area: CabtAreaType.HAND,
      index: 3,
      inPlayArea: CabtAreaType.BENCH,
      inPlayIndex: 0,
    }, payload)).toBe(false);
  });

  it('matches CABT ability options to the clicked board slot and ability name', () => {
    const engine = new LocalEngineController() as any;
    engine.observation = {
      current: {
        players: [
          {
            active: [null],
            bench: [{ id: 96 }],
            hand: [],
          },
        ],
      },
    };
    engine.dataMaps = {
      cardData: {
        96: { cardId: 96, name: 'Teal Mask Ogerpon ex', cardType: 0, skills: [{ name: 'Teal Dance' }] },
      },
      attacks: {},
    };

    expect(engine.matchesAbilityOption({
      type: CabtOptionType.ABILITY,
      area: CabtAreaType.BENCH,
      index: 0,
    }, {
      playerIndex: 0,
      ability: 'Teal Dance',
      target: targetFor(0, 0, SlotType.BENCH, 0),
    })).toBe(true);
    expect(engine.matchesAbilityOption({
      type: CabtOptionType.ABILITY,
      area: CabtAreaType.BENCH,
      index: 0,
    }, {
      playerIndex: 0,
      ability: 'Wrong Ability',
      target: targetFor(0, 0, SlotType.BENCH, 0),
    })).toBe(false);
  });

  it('keeps a selected retreat target across intermediate CABT prompts', () => {
    const engine = new LocalEngineController() as any;
    engine.pendingRetreatTarget = { playerIndex: 0, benchIndex: 1 };
    engine.observation = {
      select: {
        option: [
          { area: CabtAreaType.BENCH, index: 0 },
          { area: CabtAreaType.BENCH, index: 1 },
        ],
      },
    };

    expect(engine.findPendingRetreatTargetOption()).toBe(1);
  });

  it('appends bridge auto-step logs to the action timeline sequence', () => {
    const engine = new LocalEngineController() as any;
    const current = currentState();

    engine.applyBridgeResponse({
      ok: true,
      id: 1,
      observation: {
        select: null,
        logs: [{ type: CabtLogType.TURN_END, playerIndex: 1 }],
        current,
      },
      autoSteps: [
        {
          select: null,
          logs: [{ type: CabtLogType.TURN_START, playerIndex: 1 }],
          current,
        },
        {
          select: null,
          logs: [{ type: CabtLogType.TURN_END, playerIndex: 1 }],
          current,
        },
      ],
    });

    const response = engine.viewResponse();

    expect(response.ok).toBe(true);
    if (!response.ok) return;
    expect(response.view.actionTimeline).toEqual([
      expect.objectContaining({ id: 1, message: 'プレイヤー2の番が始まった。' }),
      expect.objectContaining({ id: 2, message: 'プレイヤー2は番を終えた。' }),
    ]);
    expect(response.sequence).toEqual([
      expect.objectContaining({
        actionTimeline: [expect.objectContaining({ message: 'プレイヤー2の番が始まった。' })],
      }),
      expect.objectContaining({
        actionTimeline: [
          expect.objectContaining({ message: 'プレイヤー2の番が始まった。' }),
          expect.objectContaining({ message: 'プレイヤー2は番を終えた。' }),
        ],
      }),
    ]);
  });

  it('inserts a playback reveal prompt for known deck-to-discard batches', () => {
    const engine = new LocalEngineController() as any;
    engine.dataMaps = {
      cardData: {
        3: { cardId: 3, name: 'Basic {W} Energy', cardType: 5, energyType: 3, set: 'SVE', setNumber: '3' },
        723: { cardId: 723, name: 'Mega Abomasnow ex', cardType: 0, set: 'MEG', setNumber: '36' },
      },
      attacks: {},
    };

    engine.applyBridgeResponse({
      ok: true,
      id: 1,
      observation: {
        select: null,
        logs: [
          { type: CabtLogType.MOVE_CARD, playerIndex: 0, cardId: 3, serial: 10, fromArea: CabtAreaType.DECK, toArea: CabtAreaType.DISCARD },
          { type: CabtLogType.MOVE_CARD, playerIndex: 0, cardId: 723, serial: 11, fromArea: CabtAreaType.DECK, toArea: CabtAreaType.DISCARD },
        ],
        current: currentState(),
      },
      autoSteps: [],
    });

    const response = engine.viewResponse();
    expect(response.ok).toBe(true);
    if (!response.ok) return;
    const revealView = response.sequence?.[0];

    expect(revealView?.prompts[0]).toEqual(expect.objectContaining({
      className: 'ConfirmCardsPrompt',
      type: 'playback-reveal',
      message: '公開して捨てたカード',
    }));
    expect(revealView?.prompts[0]?.fields.cards).toEqual([
      expect.objectContaining({ name: 'Basic {W} Energy' }),
      expect.objectContaining({ name: 'Mega Abomasnow ex' }),
    ]);
    expect(response.sequence?.[1]?.prompts).toEqual([]);
  });

  it('skips agent decision frames according to manual player controls', () => {
    const engine = new LocalEngineController() as any;
    engine.playerControls = ['self', 'agent'];

    engine.applyBridgeResponse({
      ok: true,
      id: 1,
      observation: {
        select: null,
        logs: [],
        current: currentState(),
      },
      autoSteps: [
        {
          select: {
            type: 1,
            context: CabtSelectContext.TO_ACTIVE,
            minCount: 1,
            maxCount: 1,
            remainDamageCounter: 0,
            remainEnergyCost: 0,
            option: [{ type: CabtOptionType.CARD, area: CabtAreaType.BENCH, index: 0, playerIndex: 1 }],
            deck: null,
            contextCard: null,
            effect: null,
          },
          logs: [],
          current: currentState({ yourIndex: 1 }),
        },
        {
          select: null,
          logs: [],
          current: currentState({ yourIndex: 0 }),
        },
      ],
    });

    const response = engine.viewResponse();
    expect(response.ok).toBe(true);
    if (!response.ok) return;
    expect(response.sequence).toHaveLength(1);
    expect(response.sequence?.[0]?.prompts).toEqual([]);
  });

  it('batches repeated single-energy retreat payment prompts', async () => {
    const engine = new LocalEngineController() as any;
    const selections: number[][] = [];
    const activeWithFourEnergy = {
      id: 723,
      hp: 350,
      maxHp: 350,
      appearThisTurn: false,
      energies: [3, 3, 3, 3],
      energyCards: [10, 11, 12, 13].map((serial) => ({ id: 3, serial, playerIndex: 0 })),
      tools: [],
      preEvolution: [],
    };
    const current = {
      turn: 1,
      turnActionCount: 0,
      yourIndex: 0,
      firstPlayer: 0,
      supporterPlayed: false,
      stadiumPlayed: false,
      energyAttached: true,
      retreated: false,
      result: -1,
      stadium: [],
      looking: null,
      players: [
        {
          active: [activeWithFourEnergy],
          bench: [{ id: 722, hp: 90, maxHp: 90, appearThisTurn: false, energies: [], energyCards: [], tools: [], preEvolution: [] }],
          benchMax: 5,
          deckCount: 47,
          discard: [],
          prize: [],
          handCount: 0,
          hand: [],
          poisoned: false,
          burned: false,
          asleep: false,
          paralyzed: false,
          confused: false,
        },
        {
          active: [null],
          bench: [],
          benchMax: 5,
          deckCount: 47,
          discard: [],
          prize: [],
          handCount: 0,
          hand: [],
          poisoned: false,
          burned: false,
          asleep: false,
          paralyzed: false,
          confused: false,
        },
      ],
    };
    const energySelect = (energyCards: typeof activeWithFourEnergy.energyCards) => ({
      type: 1,
      context: CabtSelectContext.DISCARD_ENERGY_CARD,
      minCount: 1,
      maxCount: 1,
      remainDamageCounter: 0,
      remainEnergyCost: energyCards.length,
      option: energyCards.map((_card, energyIndex) => ({
        type: CabtOptionType.ENERGY_CARD,
        area: CabtAreaType.ACTIVE,
        index: 0,
        energyIndex,
        playerIndex: 0,
      })),
      deck: null,
      contextCard: null,
      effect: null,
    });

    engine.sessionId = 'test-session';
    engine.pendingRetreatTarget = { playerIndex: 0, benchIndex: 0 };
    engine.dataMaps = { cardData: {}, attacks: {} };
    engine.observation = {
      select: energySelect(activeWithFourEnergy.energyCards),
      logs: [],
      current,
    };
    engine.bridge = {
      request: async ({ selection }: { selection: number[] }) => {
        selections.push(selection);
        activeWithFourEnergy.energyCards.shift();
        activeWithFourEnergy.energies.shift();
        if (activeWithFourEnergy.energyCards.length) {
          return {
            ok: true,
            observation: { select: energySelect(activeWithFourEnergy.energyCards), logs: [], current },
          };
        }
        return {
          ok: true,
          observation: {
            select: {
              type: 1,
              context: CabtSelectContext.TO_ACTIVE,
              minCount: 1,
              maxCount: 1,
              remainDamageCounter: 0,
              remainEnergyCost: 0,
              option: [{ type: CabtOptionType.CARD, area: CabtAreaType.BENCH, index: 0, playerIndex: 0 }],
              deck: null,
              contextCard: null,
              effect: null,
            },
            logs: [],
            current,
          },
        };
      },
    };

    const response = await engine.applySelection([0, 1, 2, 3]);

    expect(selections).toEqual([[0], [0], [0], [0], [0]]);
    expect(response.ok).toBe(true);
    if (!response.ok) return;
    expect(response.sequence).toHaveLength(5);
  });

  it('marks a direct human frame instant and later automatic frames animate', async () => {
    const engine = new LocalEngineController() as any;
    const select = {
      type: 1,
      context: CabtSelectContext.MAIN,
      minCount: 1,
      maxCount: 1,
      remainDamageCounter: 0,
      remainEnergyCost: 0,
      option: [{ type: CabtOptionType.END }],
      deck: null,
      contextCard: null,
      effect: null,
    };
    engine.sessionId = 'session';
    engine.playerControls = ['self', 'agent'];
    engine.observation = { select, logs: [], current: currentState({ yourIndex: 0 }) };
    engine.bridge = {
      request: async () => ({
        ok: true,
        observation: { select: null, logs: [], current: currentState({ yourIndex: 0 }) },
        autoSteps: [
          { select: null, logs: [], current: currentState({ yourIndex: 0 }) },
          { select: null, logs: [], current: currentState({ yourIndex: 1 }) },
        ],
      }),
    };

    const response = await engine.applySelection([0]);

    expect(response.ok).toBe(true);
    if (!response.ok) return;
    expect(response.sequencePlayback).toEqual(['instant', 'animate']);
  });

  it('exposes opaque Codex tokens and rejects a stale decision', async () => {
    const engine = new LocalEngineController() as any;
    engine.observationVersion = 7;
    engine.observation = {
      select: {
        type: 0,
        context: CabtSelectContext.MAIN,
        minCount: 1,
        maxCount: 1,
        remainDamageCounter: 0,
        remainEnergyCost: 0,
        option: [{ type: CabtOptionType.END }],
        deck: null,
        contextCard: null,
        effect: null,
      },
      logs: [],
      current: currentState({ yourIndex: 1 }),
    };

    const decision = engine.currentCodexDecision(1);

    expect(decision).toMatchObject({ playerIndex: 1, minCount: 1, maxCount: 1 });
    expect(decision.options[0]).toMatchObject({ token: 'd7-o0', kind: 'end', label: 'ターンエンド' });
    expect(decision.options[0]).not.toHaveProperty('index');
    await expect(engine.applyCodexDecision(1, 'd6', ['d6-o0']))
      .resolves.toMatchObject({ ok: false, error: '局面が更新されています。最新の合法手を取得してください。' });
  });

  it('does not expose a decision to the non-acting seat', () => {
    const engine = new LocalEngineController() as any;
    engine.observationVersion = 1;
    engine.observation = {
      select: {
        type: 0,
        context: CabtSelectContext.MAIN,
        minCount: 1,
        maxCount: 1,
        remainDamageCounter: 0,
        remainEnergyCost: 0,
        option: [{ type: CabtOptionType.END }],
        deck: null,
        contextCard: null,
        effect: null,
      },
      logs: [],
      current: currentState({ yourIndex: 1 }),
    };

    expect(engine.currentCodexDecision(0)).toBeNull();
  });

  it('validates duplicate, malformed and out-of-range Codex tokens', async () => {
    const engine = new LocalEngineController() as any;
    engine.observationVersion = 2;
    engine.observation = {
      select: {
        type: 1,
        context: CabtSelectContext.TO_HAND,
        minCount: 1,
        maxCount: 2,
        remainDamageCounter: 0,
        remainEnergyCost: 0,
        option: [
          { type: CabtOptionType.CARD, cardId: 1 },
          { type: CabtOptionType.CARD, cardId: 2 },
        ],
        deck: null,
        contextCard: null,
        effect: null,
      },
      logs: [],
      current: currentState({ yourIndex: 1 }),
    };

    await expect(engine.applyCodexDecision(1, 'd2', ['d2-o0', 'd2-o0']))
      .resolves.toMatchObject({ ok: false });
    await expect(engine.applyCodexDecision(1, 'd2', ['wrong']))
      .resolves.toMatchObject({ ok: false, error: '合法手トークンが正しくありません。' });
    await expect(engine.applyCodexDecision(1, 'd2', ['d2-o2']))
      .resolves.toMatchObject({ ok: false, error: '合法手トークンが正しくありません。' });
  });

  it('summarizes the Codex deck and exposes only legitimately searched deck cards', () => {
    const engine = new LocalEngineController() as any;
    engine.observationVersion = 3;
    engine.observation = {
      select: {
        type: 1,
        context: CabtSelectContext.TO_HAND,
        minCount: 1,
        maxCount: 1,
        remainDamageCounter: 0,
        remainEnergyCost: 0,
        option: [
          { type: CabtOptionType.CARD, area: CabtAreaType.DECK, index: 0 },
          { type: CabtOptionType.CARD, area: CabtAreaType.DECK, index: 1 },
        ],
        deck: [{ id: 1 }, { id: 2 }],
        contextCard: null,
        effect: null,
      },
      logs: [],
      current: currentState({ yourIndex: 1 }),
    };

    expect(engine.describeCodexDeck(Array(60).fill(1))).toEqual([
      expect.objectContaining({ id: 1, count: 60 }),
    ]);
    expect(engine.currentCodexSearch(1)).toMatchObject({
      decisionId: 'd3',
      cards: [expect.objectContaining({ id: 1 }), expect.objectContaining({ id: 2 })],
    });
  });
});

function currentState(overrides: Record<string, unknown> = {}) {
  return {
    turn: 2,
    turnActionCount: 0,
    yourIndex: 0,
    firstPlayer: 0,
    supporterPlayed: false,
    stadiumPlayed: false,
    energyAttached: true,
    retreated: false,
    result: -1,
    stadium: [],
    looking: null,
    players: [
      playerState({ hand: [], handCount: 0 }),
      playerState({ hand: null, handCount: 0 }),
    ],
    ...overrides,
  };
}

function playerState(overrides: Record<string, unknown> = {}) {
  return {
    active: [null],
    bench: [],
    benchMax: 5,
    deckCount: 47,
    discard: [],
    prize: [],
    handCount: 0,
    hand: [],
    poisoned: false,
    burned: false,
    asleep: false,
    paralyzed: false,
    confused: false,
    ...overrides,
  };
}

describe('concede', () => {
  process.env.CABT_ENGINE_MODE = 'demo';

  it('ends the game with the opponent as winner (投了リグレッション)', async () => {
    const engine = new LocalEngineController();
    let res = await engine.handle({ type: 'startGame' });
    expect(res.ok).toBe(true);

    res = await engine.handle({ type: 'concede', payload: { playerIndex: 0 } });
    expect(res.ok).toBe(true);
    if (!res.ok) return;
    expect(res.view.winner).toBe(1);
    expect(res.view.phaseLabel).toBe('対戦終了');
  });
});
