import enCardsRaw from '../cabt/cardData.generated.json';
import jaCardsRaw from './cardsJa.generated.json';
import { resolveCardImageUrl } from '../game/cardImages';
import { pokemonTypeIconSrc, pokemonTypeLabelFor, energyIconSrc } from '../game/energyIcons';
import { formatCabtDeckList, type DeckCardMetadata } from '../game/deckImport';

export type CardCategory = 'pokemon' | 'trainer' | 'energy';

export type CatalogMove = {
  name: string;
  cost: string;
  damage: string;
  effect: string;
};

export type CatalogAbility = {
  name: string;
  text: string;
};

export type CatalogCard = {
  id: number;
  name: string;
  nameJa: string;
  set: string;
  setNumber: string;
  category: CardCategory;
  /** English subtype label, e.g. "Stage 2", "Supporter", "Special Energy". */
  subtype: string;
  subtypeJa: string;
  type?: string;
  typeLabel?: string;
  typeIcon?: string;
  energyIcon?: string;
  hp: number | null;
  retreat: number;
  evolvesFrom: string;
  rule: string;
  ruleJa: string;
  ex: boolean;
  megaEx: boolean;
  tera: boolean;
  aceSpec: boolean;
  basic: boolean;
  stage1: boolean;
  stage2: boolean;
  imageUrl?: string;
  abilities: CatalogAbility[];
  movesJa: CatalogMove[];
  /** Max copies allowed by deck rules (basic energy is effectively unlimited). */
  copyLimit: number;
  searchText: string;
};

type EnCard = {
  id: number;
  name: string;
  set: string;
  setNumber: string;
  kind: string;
  rule: string;
  evolvesFrom: string;
  hp: number | null;
  type: string;
  cardType: number;
  retreatCost: number;
  energyType: number;
  basic: boolean;
  stage1: boolean;
  stage2: boolean;
  ex: boolean;
  megaEx: boolean;
  tera: boolean;
  aceSpec: boolean;
  skills?: CatalogAbility[];
};

type JaCard = {
  name: string;
  kind: string;
  category: string;
  rule: string;
  hp: string;
  type: string;
  retreat: string;
  evolvesFrom: string;
  moves: CatalogMove[];
};

const TRAINER_SUBTYPE_JA: Record<string, string> = {
  Item: 'グッズ',
  Supporter: 'サポート',
  Stadium: 'スタジアム',
  'Pokémon Tool': 'ポケモンのどうぐ',
  'Pokemon Tool': 'ポケモンのどうぐ',
  Tool: 'ポケモンのどうぐ',
};

export const ENERGY_BASIC_COPY_LIMIT = 60;

function categoryOf(cardType: number): CardCategory {
  if (cardType === 0) return 'pokemon';
  if (cardType === 5 || cardType === 6) return 'energy';
  return 'trainer';
}

function pokemonStageJa(card: EnCard): string {
  if (card.megaEx) return 'メガシンカex';
  if (card.stage2) return '2進化';
  if (card.stage1) return '1進化';
  return 'たね';
}

function subtypeFor(card: EnCard, category: CardCategory): { en: string; ja: string } {
  if (category === 'energy') {
    return card.cardType === 5
      ? { en: 'Basic Energy', ja: '基本エネルギー' }
      : { en: 'Special Energy', ja: '特殊エネルギー' };
  }
  if (category === 'trainer') {
    return { en: card.kind || 'Trainer', ja: TRAINER_SUBTYPE_JA[card.kind] ?? 'トレーナーズ' };
  }
  const en = card.megaEx ? 'Mega ex' : card.stage2 ? 'Stage 2' : card.stage1 ? 'Stage 1' : 'Basic';
  return { en, ja: pokemonStageJa(card) };
}

function copyLimitFor(card: EnCard): number {
  if (card.cardType === 5) return ENERGY_BASIC_COPY_LIMIT;
  if (card.aceSpec) return 1;
  return 4;
}

function buildCard(en: EnCard, ja: JaCard | undefined): CatalogCard {
  const category = categoryOf(en.cardType);
  const subtype = subtypeFor(en, category);
  const imageUrl = resolveCardImageUrl({ id: en.id, set: en.set, setNumber: en.setNumber, name: en.name });
  const isEnergy = category === 'energy';
  const typeIcon = !isEnergy && category === 'pokemon' ? pokemonTypeIconSrc(en.energyType) : undefined;
  const energyIcon = isEnergy ? energyIconSrc({ name: en.name, energyType: en.energyType }) : undefined;
  const nameJa = ja?.name || en.name;
  return {
    id: en.id,
    name: en.name,
    nameJa,
    set: en.set,
    setNumber: en.setNumber,
    category,
    subtype: subtype.en,
    subtypeJa: subtype.ja,
    type: en.type || undefined,
    typeLabel: category === 'pokemon' ? pokemonTypeLabelFor(en.energyType) : undefined,
    typeIcon,
    energyIcon,
    hp: en.hp,
    retreat: en.retreatCost ?? 0,
    evolvesFrom: en.evolvesFrom || '',
    rule: en.rule && en.rule !== 'n/a' ? en.rule : '',
    ruleJa: ja?.rule || '',
    ex: en.ex,
    megaEx: en.megaEx,
    tera: en.tera,
    aceSpec: en.aceSpec,
    basic: en.basic,
    stage1: en.stage1,
    stage2: en.stage2,
    imageUrl,
    abilities: en.skills ?? [],
    movesJa: ja?.moves ?? [],
    copyLimit: copyLimitFor(en),
    searchText: `${en.name}\n${nameJa}\n${en.set} ${en.setNumber}`.toLowerCase(),
  };
}

let catalogCache: CatalogCard[] | null = null;

export function getCatalog(): CatalogCard[] {
  if (catalogCache) return catalogCache;
  const ja = jaCardsRaw as unknown as Record<string, JaCard>;
  catalogCache = (enCardsRaw as unknown as EnCard[]).map((en) => buildCard(en, ja[String(en.id)]));
  return catalogCache;
}

export function getCatalogMap(): Map<number, CatalogCard> {
  return new Map(getCatalog().map((card) => [card.id, card]));
}

export type DeckTextEntry = { count: number; card?: CatalogCard; label: string };

/** 貼り付け形式のデッキリスト（"3 ヒカリ PFL 87" など）をカタログのカードへ解決する。
 * セット＋コレクション番号が最優先、無ければ日本語/英語名で照合する。 */
export function resolveDeckTextEntries(text: string): DeckTextEntry[] {
  const catalog = getCatalog();
  const bySetNumber = new Map<string, CatalogCard>();
  for (const card of catalog) {
    bySetNumber.set(`${card.set} ${card.setNumber}`.toLowerCase(), card);
  }
  const entries: DeckTextEntry[] = [];
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.replace(/\s+#.*$/, '').trim();
    if (!line || /^[^\d:][^:]+:\s*\d+\s*$/.test(line)) {
      continue; // 空行またはセクション見出し（ポケモン: 22 など）
    }
    const match = line.match(/^(\d+)\s+(.+)$/);
    const count = match ? Number(match[1]) : 1;
    const label = (match ? match[2] : line).trim();
    const tokens = label.split(/\s+/);
    const hasNumber = /^\d+[a-z]?$/i.test(tokens.at(-1) ?? '');
    const setCode = hasNumber ? tokens.at(-2) : tokens.at(-1);
    let card: CatalogCard | undefined;
    if (hasNumber && setCode) {
      card = bySetNumber.get(`${setCode} ${tokens.at(-1)}`.toLowerCase());
    }
    if (!card) {
      const bareName = (hasNumber ? tokens.slice(0, -2) : tokens.slice(0, -1)).join(' ') || label;
      card = catalog.find((item) => item.nameJa === bareName || item.name === bareName)
        ?? catalog.find((item) => item.nameJa === label || item.name === label);
    }
    entries.push({ count: Number.isFinite(count) && count > 0 ? count : 1, card, label });
  }
  return entries;
}

/** デッキ編成で保存したデッキ（id→枚数）を、対戦画面に貼り付ける形式のリストへ変換する。 */
export function deckCountsToText(counts: Record<number, number>): string {
  const map = getCatalogMap();
  const sections: Record<CardCategory, string[]> = { pokemon: [], trainer: [], energy: [] };
  const totals: Record<CardCategory, number> = { pokemon: 0, trainer: 0, energy: 0 };
  for (const [rawId, count] of Object.entries(counts)) {
    const card = map.get(Number(rawId));
    if (!card || !count) {
      continue;
    }
    sections[card.category].push(`${count} ${card.nameJa} ${card.set} ${card.setNumber}`);
    totals[card.category] += count;
  }
  const parts: string[] = [];
  if (sections.pokemon.length) parts.push(`ポケモン: ${totals.pokemon}`, ...sections.pokemon, '');
  if (sections.trainer.length) parts.push(`トレーナーズ: ${totals.trainer}`, ...sections.trainer, '');
  if (sections.energy.length) parts.push(`エネルギー: ${totals.energy}`, ...sections.energy, '');
  return parts.join('\n').trim();
}

export type CardFilters = {
  query: string;
  category: CardCategory | 'all';
  set: string | 'all';
  type: string | 'all';
  trait: 'all' | 'ex' | 'megaEx' | 'tera' | 'aceSpec' | 'basic' | 'stage1' | 'stage2';
};

export const EMPTY_FILTERS: CardFilters = {
  query: '',
  category: 'all',
  set: 'all',
  type: 'all',
  trait: 'all',
};

function matchesTrait(card: CatalogCard, trait: CardFilters['trait']): boolean {
  switch (trait) {
    case 'all':
      return true;
    case 'ex':
      return card.ex || card.megaEx;
    case 'megaEx':
      return card.megaEx;
    case 'tera':
      return card.tera;
    case 'aceSpec':
      return card.aceSpec;
    case 'basic':
      return card.category === 'pokemon' && card.basic;
    case 'stage1':
      return card.stage1;
    case 'stage2':
      return card.stage2;
    default:
      return true;
  }
}

export function filterCatalog(cards: CatalogCard[], filters: CardFilters): CatalogCard[] {
  const query = filters.query.trim().toLowerCase();
  return cards.filter((card) => {
    if (filters.category !== 'all' && card.category !== filters.category) return false;
    if (filters.set !== 'all' && card.set !== filters.set) return false;
    if (filters.type !== 'all' && card.typeLabel !== filters.type) return false;
    if (!matchesTrait(card, filters.trait)) return false;
    if (query && !card.searchText.includes(query)) return false;
    return true;
  });
}

export function listSets(cards: CatalogCard[]): string[] {
  return [...new Set(cards.map((c) => c.set).filter(Boolean))].sort();
}

export function listTypes(cards: CatalogCard[]): string[] {
  return [...new Set(cards.filter((c) => c.category === 'pokemon' && c.typeLabel).map((c) => c.typeLabel as string))].sort();
}

export const DECK_SIZE = 60;

export type DeckValidation = {
  total: number;
  byCategory: { pokemon: number; trainer: number; energy: number };
  errors: string[];
  ok: boolean;
};

/** Deck-legality check used as UX guidance; the CABT engine remains the source of truth. */
export function validateDeck(counts: Record<number, number>, map: Map<number, CatalogCard>): DeckValidation {
  const byCategory = { pokemon: 0, trainer: 0, energy: 0 };
  const errors: string[] = [];
  let total = 0;
  let basicPokemon = 0;
  let aceSpecTotal = 0;

  for (const [rawId, count] of Object.entries(counts)) {
    if (!count || count <= 0) continue;
    const id = Number(rawId);
    const card = map.get(id);
    total += count;
    if (!card) {
      errors.push(`不明なカードID ${id} が含まれています。`);
      continue;
    }
    byCategory[card.category] += count;
    if (card.category === 'pokemon' && card.basic) basicPokemon += count;
    if (card.aceSpec) aceSpecTotal += count;
    if (count > card.copyLimit) {
      const limitLabel = card.copyLimit >= ENERGY_BASIC_COPY_LIMIT ? '無制限' : `${card.copyLimit}枚`;
      errors.push(`${card.nameJa}：同名は${limitLabel}までです（現在${count}枚）。`);
    }
  }

  if (total !== DECK_SIZE) errors.push(`デッキは60枚ちょうどにしてください（現在${total}枚）。`);
  if (basicPokemon === 0) errors.push('「たね」ポケモンが最低1枚必要です。');
  if (aceSpecTotal > 1) errors.push(`ACE SPEC はデッキに1枚までです（現在${aceSpecTotal}枚）。`);

  return { total, byCategory, errors, ok: errors.length === 0 };
}

/** Expand a {cardId: count} map into the 60-line CABT id CSV the engine reads. */
export function buildCabtIdCsv(counts: Record<number, number>): string {
  const ids: number[] = [];
  for (const [id, count] of Object.entries(counts)) {
    for (let i = 0; i < count; i += 1) ids.push(Number(id));
  }
  return ids.join('\n');
}

/** Build the human-readable decklist text that the match setup import box expects. */
export function buildSetupDeckText(counts: Record<number, number>, cards: CatalogCard[]): string {
  const rows: DeckCardMetadata[] = cards.map((c) => ({
    id: c.id,
    name: c.name,
    set: c.set,
    setNumber: c.setNumber,
    cardType: c.category === 'pokemon' ? 0 : c.category === 'energy' ? (c.subtype === 'Basic Energy' ? 5 : 6) : 1,
  }));
  return formatCabtDeckList(buildCabtIdCsv(counts), rows);
}
