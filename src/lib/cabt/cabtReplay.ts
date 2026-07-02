import cardRows from './cardData.generated.json';
import attackRows from './attackData.generated.json';
import { japaneseAttackName, japaneseCardName } from './logFormat';
import { resolveCardImageUrl } from '../game/cardImages';
import { SlotType, targetFor, type CardView, type GameView, type LogView, type PlayerView, type PokemonSlotView } from '../game/types';
import type { ReplaySnapshot, ReplayStep } from '../game/replay';

type CardRow = {
  id: number;
  name: string;
  set: string;
  setNumber: string;
  kind: string;
  rule: string;
  evolvesFrom: string;
  hp: number | null;
  type: string;
  retreat: number | null;
  attackName: string;
  attackCost: string;
  attackDamage: string;
  attackText: string;
  retreatCost?: number;
  attacks?: number[];
};

type AttackRow = {
  attackId: number;
  name: string;
  text?: string;
  damage?: number;
  energies?: number[];
};

type CabtCardRef = {
  id: number;
  serial?: number;
  playerIndex?: number;
  name?: string;
};

type CabtPokemonRef = CabtCardRef & {
  hp?: number;
  maxHp?: number;
  energies?: number[];
  energyCards?: CabtCardRef[];
  tools?: CabtCardRef[];
  preEvolution?: CabtCardRef[];
};

type CabtPlayerFrame = {
  active?: CabtPokemonRef[];
  bench?: CabtPokemonRef[];
  benchMax?: number;
  deckCount?: number;
  discard?: CabtCardRef[];
  hand?: CabtCardRef[];
  handCount?: number;
  prize?: Array<CabtCardRef | null>;
  poisoned?: boolean;
  burned?: boolean;
  asleep?: boolean;
  paralyzed?: boolean;
  confused?: boolean;
};

type CabtVisualizeFrame = {
  logs?: Array<Record<string, unknown>>;
  select?: Record<string, unknown> | null;
  selected?: unknown;
  action?: unknown;
  obs?: unknown;
  current: {
    turn: number;
    yourIndex: number;
    result: number;
    stadium?: CabtCardRef[];
    players: CabtPlayerFrame[];
  };
};

type KaggleContext = {
  environment?: {
    id?: string;
    title?: string;
    rewards?: number[];
    statuses?: string[];
    steps?: Array<Array<{ action?: unknown; observation?: Record<string, unknown>; status?: string; reward?: number }>>;
    info?: {
      TeamNames?: string[];
      EpisodeId?: string | number;
    };
  };
};

type CabtRunnerJson = {
  visualize?: CabtVisualizeFrame[];
  steps?: Array<{ index?: number; action?: unknown; observation?: unknown }>;
};

const cardDatabase = new Map<number, CardRow>((cardRows as CardRow[]).map((card) => [card.id, card]));
const attackDatabase = new Map<number, AttackRow>((attackRows as AttackRow[]).map((attack) => [attack.attackId, attack]));

export function cabtReplayToSnapshot(input: unknown): ReplaySnapshot {
  const visualFrames = extractVisualizeFrames(input);
  if (!visualFrames.length) {
    throw new Error('CABT replay did not include visualize frames.');
  }

  const environment = (input as KaggleContext)?.environment;
  const players = playerNames(input);
  const views: GameView[] = [];
  const steps: ReplayStep[] = [];
  const logs: LogView[] = [];
  let logId = 1;

  visualFrames.forEach((frame, index) => {
    for (const entry of frame.logs ?? []) {
      logs.push({ id: logId++, message: formatLog(entry), params: entry });
    }
    const view = frameToGameView(frame, players, logs);
    views.push(view);
    steps.push({
      index,
      label: stepLabel(frame, index),
      stateIndex: index,
      actionIndex: index === 0 ? null : index - 1,
      sequence: index,
      turn: view.turn,
      phase: view.phase,
      activePlayerIndex: view.activePlayerIndex,
      type: String(frame.select?.type ?? 'frame'),
      payload: {
        select: frame.select,
        selected: frame.selected,
        action: frame.action,
      },
    });
  });

  const finalView = views.at(-1);
  const winner = typeof finalView?.winner === 'number' ? finalView.winner : -1;
  return {
    id: String(environment?.id ?? 'cabt-local-replay'),
    name: environment?.title ? `${environment.title} replay` : 'CABT replay',
    created: Date.now(),
    players: players.map((name, index) => ({ userId: index, name })),
    winner,
    stateCount: views.length,
    actionCount: Math.max(0, steps.length - 1),
    turnCount: Math.max(...views.map((view) => view.turn), 0),
    cardNames: [...new Set([...cardDatabase.values()].map((card) => card.name))],
    views,
    steps,
  };
}

function extractVisualizeFrames(input: unknown): CabtVisualizeFrame[] {
  const runnerFrames = (input as CabtRunnerJson)?.visualize;
  if (Array.isArray(runnerFrames)) {
    return runnerFrames as CabtVisualizeFrame[];
  }

  const steps = (input as KaggleContext)?.environment?.steps;
  const frames = steps?.[0]?.[0]?.observation?.visualize;
  if (Array.isArray(frames)) {
    return frames as CabtVisualizeFrame[];
  }

  const firstStepFrames = (steps?.[0]?.[0] as { visualize?: unknown } | undefined)?.visualize;
  if (Array.isArray(firstStepFrames)) {
    return firstStepFrames as CabtVisualizeFrame[];
  }

  const nestedEnvironment = (input as { environment?: { steps?: unknown } })?.environment?.steps;
  if (Array.isArray(nestedEnvironment)) {
    const maybeFrames = (nestedEnvironment[0] as Array<Record<string, unknown>> | undefined)?.[0]?.visualize;
    if (Array.isArray(maybeFrames)) {
      return maybeFrames as CabtVisualizeFrame[];
    }
  }

  return [];
}

function frameToGameView(frame: CabtVisualizeFrame, playerNamesForReplay: string[], logs: LogView[]): GameView {
  const current = frame.current;
  const activePlayerIndex = clampPlayerIndex(current.yourIndex);
  const players = current.players.map((player, index) =>
    buildPlayerView(player, index, activePlayerIndex, playerNamesForReplay[index] ?? `プレイヤー${index + 1}`, current.stadium ?? []),
  );
  return {
    ready: true,
    phase: current.result >= 0 ? 7 : 2,
    phaseLabel: current.result >= 0 ? '対戦終了' : 'リプレイ',
    turn: current.turn,
    activePlayerIndex,
    activePlayerId: players[activePlayerIndex]?.id,
    winner: current.result >= 0 && current.result <= 1 ? current.result : current.result === 2 ? 3 : undefined,
    players,
    prompts: [],
    logs: [...logs],
    events: [frame],
  };
}

function buildPlayerView(
  player: CabtPlayerFrame,
  index: number,
  activePlayerIndex: number,
  name: string,
  stadium: CabtCardRef[],
): PlayerView {
  const hand = player.hand ?? [];
  return {
    index,
    id: index,
    name,
    hand: hand.length ? hand.map(cardToView) : Array.from({ length: player.handCount ?? 0 }, () => faceDownCard()),
    deckCount: player.deckCount ?? 0,
    discard: (player.discard ?? []).map(cardToView),
    lostZone: [],
    stadium: stadium.map(cardToView),
    playZone: [],
    prizesLeft: player.prize?.length ?? 0,
    active: pokemonToSlot(player.active?.[0] ?? null, index, 'active', 0, activePlayerIndex, player),
    bench: Array.from({ length: Math.max(player.benchMax ?? 5, player.bench?.length ?? 0) }, (_item, benchIndex) =>
      pokemonToSlot(player.bench?.[benchIndex] ?? null, index, 'bench', benchIndex, activePlayerIndex, player),
    ),
    playableCardIds: hand.map((card) => card.id),
    availableActions: {
      active: {
        attacks: [],
        abilities: [],
        retreat: { legal: false, targets: [] },
      },
      bench: (player.bench ?? []).map((_bench, benchIndex) => ({ index: benchIndex, abilities: [] })),
    },
  };
}

function pokemonToSlot(
  pokemonCard: CabtPokemonRef | null,
  ownerIndex: number,
  slot: 'active' | 'bench',
  index: number,
  activePlayerIndex: number,
  player: CabtPlayerFrame,
): PokemonSlotView {
  const slotType = slot === 'active' ? SlotType.ACTIVE : SlotType.BENCH;
  const pokemonView = pokemonCard ? cardToView(pokemonCard) : undefined;
  const maxHp = pokemonCard?.maxHp ?? pokemonView?.hp ?? 0;
  const currentHp = pokemonCard?.hp ?? maxHp;
  return {
    ownerIndex,
    slot,
    index,
    target: targetFor(activePlayerIndex, ownerIndex, slotType, index),
    empty: !pokemonCard,
    pokemon: pokemonView,
    cards: pokemonView ? [pokemonView, ...(pokemonCard?.preEvolution ?? []).map(cardToView)] : [],
    damage: Math.max(0, maxHp - currentHp),
    hp: maxHp,
    retreat: Array.from({ length: retreatCostFor(cardDatabase.get(pokemonCard?.id ?? -1)) }, () => 'Colorless'),
    energy: (pokemonCard?.energyCards ?? []).map(cardToView),
    tools: (pokemonCard?.tools ?? []).map(cardToView),
    specialConditions: [
      player.poisoned ? 'Poisoned' : null,
      player.burned ? 'Burned' : null,
      player.asleep ? 'Asleep' : null,
      player.paralyzed ? 'Paralyzed' : null,
      player.confused ? 'Confused' : null,
    ].filter((condition): condition is string => !!condition),
  };
}

function cardToView(cardRef: CabtCardRef): CardView {
  const data = cardDatabase.get(cardRef.id);
  const rawName = cardRef.name || data?.name || `Card ${cardRef.id}`;
  const name = displayName(rawName);
  const kind = data?.kind ?? '';
  const isPokemon = kind.includes('Pokémon') || !!data?.hp;
  const isEnergy = kind.includes('Energy') || /Energy\b/.test(rawName);
  const isTrainer = !isPokemon && !isEnergy;
  const view: CardView = {
    id: cardRef.id,
    name,
    fullName: name,
    set: data?.set || undefined,
    setNumber: data?.setNumber || undefined,
    superType: isPokemon ? 'Pokemon' : isEnergy ? 'Energy' : 'Trainer',
    cardType: isPokemon ? energySymbolToType(data?.type) : undefined,
    trainerType: isTrainer ? kind : undefined,
    energyType: isEnergy ? energySymbolToType(data?.type || rawName) : undefined,
    stage: stageLabel(kind),
    evolvesFrom: data?.evolvesFrom || undefined,
    hp: data?.hp ?? undefined,
    retreat: Array.from({ length: retreatCostFor(data) }, () => 'Colorless'),
    attacks: attacksForCard(data),
  };
  return {
    ...view,
    imageUrl: resolveCardImageUrl(view),
  };
}

function faceDownCard(): CardView {
  return {
    name: 'カード',
    fullName: 'カード',
  };
}

function playerNames(input: unknown): string[] {
  const names = (input as KaggleContext)?.environment?.info?.TeamNames;
  return names?.length ? names : ['プレイヤー1', 'プレイヤー2'];
}

function stepLabel(frame: CabtVisualizeFrame, index: number): string {
  const prizeSummary = prizeMoveSummary(frame.logs ?? []);
  if (prizeSummary) {
    return prizeSummary;
  }

  const attackSummary = attackLogSummary(frame.logs ?? []);
  if (attackSummary) {
    return attackSummary;
  }

  const latestLog = frame.logs?.at(-1);
  if (latestLog) {
    return formatLog(latestLog);
  }
  const selectType = frame.select?.type;
  const context = frame.select?.context;
  if (selectType || context) {
    return [selectType, context].filter(Boolean).join(' · ');
  }
  return index === 0 ? '初期状態' : `フレーム${index}`;
}

function formatLog(log: Record<string, unknown>): string {
  const playerIndex = typeof log.playerIndex === 'number' ? log.playerIndex : undefined;
  const actor = playerIndex === undefined ? 'ゲーム' : `プレイヤー${playerIndex + 1}`;
  const card = cardName(Number(log.cardId));
  switch (log.type) {
    case 'TurnStart':
      return `${actor}の番が始まった。`;
    case 'TurnEnd':
      return `${actor}は番を終えた。`;
    case 'Draw':
      return `${actor}は「${card}」を引いた。`;
    case 'Play':
      return `${actor}は「${card}」を使った。`;
    case 'Attach':
      return `${actor}は「${card}」をつけた。`;
    case 'Attack':
      return `${actor}は「${card}」で「${attackNameForLog(log)}」を使った。`;
    case 'MoveCard':
      if (Number(log.fromArea) === 6 && Number(log.toArea) === 2) {
        return `${actor}はサイドから「${card}」を取った。`;
      }
      return `${actor}は「${card}」を${areaName(log.fromArea)}から${areaName(log.toArea)}へ移動した。`;
    case 'HpChange':
    case 'HPChange':
      return `${actor}の「${card}」のHPが変化した。`;
    case 'Result':
      return '対戦が終了した。';
    default:
      return `${actor}：${String(log.type ?? 'イベント')}${Number.isFinite(Number(log.cardId)) ? `「${card}」` : ''}。`;
  }
}

function prizeMoveSummary(logs: Array<Record<string, unknown>>): string {
  const prizeMoves = logs.filter((log) => log.type === 'MoveCard' && Number(log.fromArea) === 6 && Number(log.toArea) === 2);
  if (!prizeMoves.length) {
    return '';
  }

  const playerIndex = typeof prizeMoves[0].playerIndex === 'number' ? prizeMoves[0].playerIndex : undefined;
  const samePlayer = prizeMoves.every((log) => log.playerIndex === playerIndex);
  if (!samePlayer || playerIndex === undefined) {
    return `両プレイヤーがサイドを合計${prizeMoves.length}枚取った。`;
  }

  const actor = `プレイヤー${playerIndex + 1}`;
  return `${actor}はサイドを${prizeMoves.length}枚取った。`;
}

function attackLogSummary(logs: Array<Record<string, unknown>>): string {
  const attack = logs.find((log) => log.type === 'Attack');
  return attack ? formatLog(attack) : '';
}

function areaName(area: unknown): string {
  const areaMap: Record<number, string> = {
    1: '山札',
    2: '手札',
    3: 'トラッシュ',
    4: 'バトル場',
    5: 'ベンチ',
    6: 'サイド',
    7: 'スタジアム',
    8: 'エネルギー',
    9: 'ポケモンのどうぐ',
    10: '進化元',
    11: 'プレイヤー',
    12: '選択中のカード',
  };
  return areaMap[Number(area)] ?? '領域';
}

function cardName(id: number): string {
  return japaneseCardName(id);
}

function attackNameForLog(log: Record<string, unknown>): string {
  return japaneseAttackName(Number(log.attackId));
}

function attacksForCard(data: CardRow | undefined): CardView['attacks'] {
  if (!data) {
    return undefined;
  }
  const engineAttacks = data.attacks
    ?.map((attackId) => attackDatabase.get(attackId))
    .filter((attack): attack is AttackRow => !!attack);
  if (engineAttacks?.length) {
    return engineAttacks.map((attack) => ({
      name: displayName(attack.name),
      cost: (attack.energies ?? []).map(energyName),
      damage: attack.damage ? String(attack.damage) : '',
      text: attack.text ?? '',
    }));
  }
  if (!data.attackName) {
    return undefined;
  }
  return [{
    name: data.attackName,
    cost: energyCostLabels(data.attackCost),
    damage: data.attackDamage,
    text: data.attackText,
  }];
}

function retreatCostFor(data: CardRow | undefined): number {
  return data?.retreat ?? data?.retreatCost ?? 0;
}

function displayName(name: string): string {
  return name
    .replaceAll('{G}', 'Grass')
    .replaceAll('{R}', 'Fire')
    .replaceAll('{W}', 'Water')
    .replaceAll('{L}', 'Lightning')
    .replaceAll('{P}', 'Psychic')
    .replaceAll('{F}', 'Fighting')
    .replaceAll('{D}', 'Darkness')
    .replaceAll('{M}', 'Metal')
    .replaceAll('{C}', 'Colorless');
}

function energySymbolToType(value: string | undefined): number | undefined {
  if (!value) {
    return undefined;
  }
  if (value.includes('{G}') || /grass/i.test(value)) return 1;
  if (value.includes('{R}') || /fire/i.test(value)) return 2;
  if (value.includes('{W}') || /water/i.test(value)) return 3;
  if (value.includes('{L}') || /lightning/i.test(value)) return 4;
  if (value.includes('{P}') || /psychic/i.test(value)) return 5;
  if (value.includes('{F}') || /fighting/i.test(value)) return 6;
  if (value.includes('{D}') || /dark/i.test(value)) return 7;
  if (value.includes('{M}') || /metal/i.test(value)) return 8;
  return 0;
}

function energyCostLabels(cost: string): string[] {
  return [...cost.matchAll(/\{([A-Z])\}/g)].map((match) => displayName(`{${match[1]}}`));
}

function energyName(energy: number): string {
  return [
    'Colorless',
    'Grass',
    'Fire',
    'Water',
    'Lightning',
    'Psychic',
    'Fighting',
    'Darkness',
    'Metal',
    'Dragon',
    'Rainbow',
    'Team Rocket',
  ][energy] ?? 'Colorless';
}

function stageLabel(kind: string): string | undefined {
  if (kind.includes('Basic Pokémon')) return 'Basic';
  if (kind.includes('Stage 1')) return 'Stage 1';
  if (kind.includes('Stage 2')) return 'Stage 2';
  return undefined;
}

function clampPlayerIndex(index: number): number {
  return index === 1 ? 1 : 0;
}
