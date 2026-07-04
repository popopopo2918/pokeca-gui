import cardRows from './cardData.generated.json';
import attackRows from './attackData.generated.json';
import jaCardRows from '../cards/cardsJa.generated.json';
import { CabtAreaType, CabtLogType } from './types';
import type { ActionTimelineEvent } from '../game/types';

type CardRow = {
  id: number;
  name: string;
  attacks?: number[];
  cardType?: number;
};

type AttackRow = {
  attackId: number;
  name: string;
};

type JaMove = { name?: string; cost?: string; damage?: string; effect?: string };
type JaCard = { name?: string; moves?: JaMove[] };

const cardDatabase = new Map<number, CardRow>((cardRows as CardRow[]).map((card) => [card.id, card]));
const attackDatabase = new Map<number, AttackRow>((attackRows as AttackRow[]).map((attack) => [attack.attackId, attack]));
const jaCards = jaCardRows as Record<string, JaCard>;

// Japanese card names (fall back to English when a JP name is missing).
const jaCardName = new Map<number, string>();
for (const [id, card] of Object.entries(jaCards)) {
  if (card?.name) {
    jaCardName.set(Number(id), card.name);
  }
}

// Japanese attack names keyed by attackId. In the JP data each card's `moves`
// list shows abilities first and attacks last, so the attacks line up with the
// LAST entries of `moves` against cardData's `attacks` (the attackId list).
const jaAttackName = new Map<number, string>();
for (const card of cardRows as CardRow[]) {
  const attackIds = card.attacks ?? [];
  const moves = jaCards[String(card.id)]?.moves ?? [];
  if (attackIds.length === 0 || moves.length < attackIds.length) {
    continue;
  }
  const offset = moves.length - attackIds.length;
  attackIds.forEach((attackId, index) => {
    const name = moves[offset + index]?.name;
    if (name) {
      jaAttackName.set(attackId, name);
    }
  });
}

const logTypeNames: Record<number, string> = {
  [CabtLogType.SHUFFLE]: 'Shuffle',
  [CabtLogType.HAS_BASIC_POKEMON]: 'HasBasicPokemon',
  [CabtLogType.TURN_START]: 'TurnStart',
  [CabtLogType.TURN_END]: 'TurnEnd',
  [CabtLogType.DRAW]: 'Draw',
  [CabtLogType.DRAW_REVERSE]: 'DrawReverse',
  [CabtLogType.MOVE_CARD]: 'MoveCard',
  [CabtLogType.MOVE_CARD_REVERSE]: 'MoveCardReverse',
  [CabtLogType.SWITCH]: 'Switch',
  [CabtLogType.CHANGE]: 'Change',
  [CabtLogType.PLAY]: 'Play',
  [CabtLogType.ATTACH]: 'Attach',
  [CabtLogType.EVOLVE]: 'Evolve',
  [CabtLogType.DEVOLVE]: 'Devolve',
  [CabtLogType.MOVE_ATTACHED]: 'MoveAttached',
  [CabtLogType.ATTACK]: 'Attack',
  [CabtLogType.HP_CHANGE]: 'HPChange',
  [CabtLogType.POISONED]: 'Poisoned',
  [CabtLogType.BURNED]: 'Burned',
  [CabtLogType.ASLEEP]: 'Asleep',
  [CabtLogType.PARALYZED]: 'Paralyzed',
  [CabtLogType.CONFUSED]: 'Confused',
  [CabtLogType.COIN]: 'Coin',
  [CabtLogType.RESULT]: 'Result',
};

export function formatCabtLog(log: Record<string, unknown>): string {
  const type = normalizedLogType(log.type);
  const playerIndex = typeof log.playerIndex === 'number' ? log.playerIndex : undefined;
  const actor = playerIndex === undefined ? 'ゲーム' : `プレイヤー${playerIndex + 1}`;
  const card = cardName(Number(log.cardId));
  const target = cardName(Number(log.cardIdTarget));

  switch (type) {
    case 'Shuffle':
      return `${actor}は山札をシャッフルした。`;
    case 'HasBasicPokemon':
      return `${actor}は、たねポケモンを${log.hasBasicPokemon ? '持っている' : '持っていない'}。`;
    case 'TurnStart':
      return `${actor}の番が始まった。`;
    case 'TurnEnd':
      return `${actor}は番を終えた。`;
    case 'Draw':
      return `${actor}は「${card}」を引いた。`;
    case 'DrawReverse':
      return `${actor}はカードを1枚引いた。`;
    case 'ability':
      return `${actor}の「${card}」が特性を使った。`;
    case 'Play':
      // Playing a Pokémon means putting it into play; trainers/items/supporters are "used".
      return cardDatabase.get(Number(log.cardId))?.cardType === 0
        ? `${actor}は「${card}」を出した。`
        : `${actor}は「${card}」を使った。`;
    case 'Attach':
      return `${actor}は「${card}」を${Number.isFinite(Number(log.cardIdTarget)) ? `「${target}」に` : ''}つけた。`;
    case 'Evolve':
      return `${actor}は「${card}」に進化させた。`;
    case 'Devolve':
      return `${actor}は「${card}」を退化させた。`;
    case 'Attack':
      return `${actor}は「${card}」で「${attackName(Number(log.attackId))}」を使った。`;
    case 'MoveCard':
      return moveCardMessage(actor, card, log);
    case 'MoveCardReverse':
      return `${actor}は裏向きのカードを${areaName(log.fromArea)}から${areaName(log.toArea)}へ移動した。`;
    case 'Switch':
      return `${actor}は「${cardName(Number(log.cardIdActive))}」と「${cardName(Number(log.cardIdBench))}」を入れ替えた。`;
    case 'Change':
      return `${actor}は「${cardName(Number(log.cardIdBefore))}」を「${cardName(Number(log.cardIdAfter))}」にした。`;
    case 'MoveAttached':
      return `${actor}は「${card}」を移動した。`;
    case 'HPChange':
      return hpChangeMessage(actor, card, log);
    case 'Poisoned':
      return `${actor}の「${card}」は${log.isRecover ? 'どくから回復した' : 'どく状態になった'}。`;
    case 'Burned':
      return `${actor}の「${card}」は${log.isRecover ? 'やけどから回復した' : 'やけど状態になった'}。`;
    case 'Asleep':
      return `${actor}の「${card}」は${log.isRecover ? '目を覚ました' : 'ねむり状態になった'}。`;
    case 'Paralyzed':
      return `${actor}の「${card}」は${log.isRecover ? 'まひから回復した' : 'まひ状態になった'}。`;
    case 'Confused':
      return `${actor}の「${card}」は${log.isRecover ? 'こんらんから回復した' : 'こんらん状態になった'}。`;
    case 'Coin':
      return `${actor}はコインを投げ、${log.head ? 'おもて' : 'うら'}が出た。`;
    case 'Result':
      return '対戦が終了した。';
    default:
      return `${actor}：${String(type ?? 'イベント')}${Number.isFinite(Number(log.cardId)) ? `「${card}」` : ''}。`;
  }
}

export function cabtLogsToTimeline(
  logs: Array<Record<string, unknown>>,
  options: { nextId?: number } = {},
): { events: ActionTimelineEvent[]; nextId: number } {
  let nextId = options.nextId ?? 1;
  const events = logs.map((log) => ({
    id: nextId++,
    message: formatCabtLog(log),
    playerIndex: typeof log.playerIndex === 'number' ? log.playerIndex : undefined,
    kind: normalizedLogType(log.type),
    params: log,
  }));
  return { events, nextId };
}

function normalizedLogType(type: unknown): string {
  if (typeof type === 'number') {
    return logTypeNames[type] ?? `Log ${type}`;
  }
  return String(type ?? 'Event');
}

function moveCardMessage(actor: string, card: string, log: Record<string, unknown>) {
  if (Number(log.fromArea) === CabtAreaType.PRIZE && Number(log.toArea) === CabtAreaType.HAND) {
    return `${actor}はサイドから「${card}」を取った。`;
  }
  if (Number(log.fromArea) === CabtAreaType.DECK && Number(log.toArea) === CabtAreaType.DISCARD) {
    return `${actor}は山札から「${card}」をトラッシュした。`;
  }
  return `${actor}は「${card}」を${areaName(log.fromArea)}から${areaName(log.toArea)}へ移動した。`;
}

function hpChangeMessage(actor: string, card: string, log: Record<string, unknown>) {
  const value = Number(log.value);
  if (!Number.isFinite(value) || value === 0) {
    return `${actor}の「${card}」のHPが変化した。`;
  }
  const amount = Math.abs(value);
  if (value < 0) {
    return `${actor}の「${card}」は${amount}ダメージを受けた。`;
  }
  return `${actor}の「${card}」はHPを${amount}回復した。`;
}

function areaName(area: unknown): string {
  const areaMap: Record<number, string> = {
    [CabtAreaType.DECK]: '山札',
    [CabtAreaType.HAND]: '手札',
    [CabtAreaType.DISCARD]: 'トラッシュ',
    [CabtAreaType.ACTIVE]: 'バトル場',
    [CabtAreaType.BENCH]: 'ベンチ',
    [CabtAreaType.PRIZE]: 'サイド',
    [CabtAreaType.STADIUM]: 'スタジアム',
    [CabtAreaType.ENERGY]: 'エネルギー',
    [CabtAreaType.TOOL]: 'ポケモンのどうぐ',
    [CabtAreaType.PRE_EVOLUTION]: '進化元',
    [CabtAreaType.PLAYER]: 'プレイヤー',
    [CabtAreaType.LOOKING]: '選択中のカード',
  };
  return areaMap[Number(area)] ?? '領域';
}

function cardName(id: number): string {
  const ja = jaCardName.get(id);
  if (ja) {
    return ja;
  }
  const en = cardDatabase.get(id)?.name;
  if (en) {
    return displayName(en);
  }
  return Number.isFinite(id) ? `カード${id}` : 'カード';
}

function attackName(id: number): string {
  const ja = jaAttackName.get(id);
  if (ja) {
    return ja;
  }
  const en = attackDatabase.get(id)?.name;
  if (en) {
    return displayName(en);
  }
  return Number.isFinite(id) ? `ワザ${id}` : 'ワザ';
}

// Shared Japanese name lookups (also used by the replay step labels).
export function japaneseCardName(id: number): string {
  return cardName(id);
}

export type JaMoveInfo = { name: string; text: string; damage: string };

// Japanese Ability/Attack display data for a card. In the JP data, `moves` lists Abilities first
// (name prefixed "[特性]") then Attacks, matching the English skills[]/attacks[] order.
// テラスタルポケモンは先頭に「テラスタル」のルール枠（ワザでも特性でもない）が入るため、
// attacks に混ぜると英語側 attacks[] と1つずれる。専用フィールドに分離する。
export function japaneseCardMoves(id: number): { abilities: JaMoveInfo[]; attacks: JaMoveInfo[]; terastal?: JaMoveInfo } {
  const abilities: JaMoveInfo[] = [];
  const attacks: JaMoveInfo[] = [];
  let terastal: JaMoveInfo | undefined;
  for (const move of jaCards[String(id)]?.moves ?? []) {
    const raw = (move?.name ?? '').trim();
    const info: JaMoveInfo = {
      name: raw.replace(/^\[特性\]\s*/, ''),
      text: move?.effect ?? '',
      damage: move?.damage ?? '',
    };
    if (raw.startsWith('[特性]')) {
      abilities.push(info);
    } else if (raw === 'テラスタル') {
      terastal = info;
    } else {
      attacks.push(info);
    }
  }
  return { abilities, attacks, terastal };
}

export function japaneseAttackName(id: number): string {
  return attackName(id);
}

function displayName(name: string): string {
  const energyNames: Record<string, string> = {
    '{C}': '無',
    '{G}': '草',
    '{R}': '炎',
    '{W}': '水',
    '{L}': '雷',
    '{P}': '超',
    '{F}': '闘',
    '{D}': '悪',
    '{M}': '鋼',
  };
  return energyNames[name] ?? name.replace(/\{([A-Z])\}/g, (_match, symbol) => energyNames[`{${symbol}}`] ?? symbol);
}
