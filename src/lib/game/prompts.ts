import { SlotType, type CardTarget, type CardView, type GameView, type PromptView } from './types';

export type PromptClassName =
  | 'AlertPrompt'
  | 'ShowCardsPrompt'
  | 'ConfirmCardsPrompt'
  | 'ShowMulliganPrompt'
  | 'ShuffleDeckPrompt'
  | 'WaitPrompt'
  | 'ConfirmPrompt'
  | 'CoinFlipPrompt'
  | 'SelectPrompt'
  | 'SelectOptionPrompt'
  | 'ChooseAttackPrompt'
  | 'ChooseCardsPrompt'
  | 'ChoosePrizePrompt'
  | 'ChooseEnergyPrompt'
  | 'DiscardEnergyPrompt'
  | 'MoveEnergyPrompt'
  | 'AttachEnergyPrompt'
  | 'PutDamagePrompt'
  | 'MoveDamagePrompt'
  | 'RemoveDamagePrompt';

export type KnownPrompt =
  | (PromptView & { className: 'AlertPrompt' | 'ShowCardsPrompt' | 'ConfirmCardsPrompt' | 'ShowMulliganPrompt' })
  | (PromptView & { className: 'ShuffleDeckPrompt' })
  | (PromptView & { className: 'WaitPrompt'; fields: { duration?: number } & Record<string, unknown> })
  | (PromptView & { className: 'ConfirmPrompt' })
  | (PromptView & { className: 'CoinFlipPrompt' })
  | (PromptView & { className: 'SelectPrompt' | 'SelectOptionPrompt'; fields: { values?: unknown[] } & Record<string, unknown> })
  | (PromptView & { className: 'ChooseAttackPrompt' })
  | (PromptView & { className: 'ChooseCardsPrompt' })
  | (PromptView & { className: 'ChoosePrizePrompt' })
  | (PromptView & { className: 'ChooseEnergyPrompt' })
  | (PromptView & { className: 'DiscardEnergyPrompt' | 'MoveEnergyPrompt' })
  | (PromptView & { className: 'AttachEnergyPrompt' })
  | (PromptView & { className: 'PutDamagePrompt' | 'MoveDamagePrompt' | 'RemoveDamagePrompt' });

export type UnknownPrompt = PromptView;

export type Prompt = KnownPrompt | UnknownPrompt;

export type IndexedCardView = CardView & {
  index?: number;
};

export function isKnownPrompt(prompt: PromptView): prompt is KnownPrompt {
  return (
    prompt.className === 'AlertPrompt'
    || prompt.className === 'ShowCardsPrompt'
    || prompt.className === 'ConfirmCardsPrompt'
    || prompt.className === 'ShowMulliganPrompt'
    || prompt.className === 'ShuffleDeckPrompt'
    || prompt.className === 'WaitPrompt'
    || prompt.className === 'ConfirmPrompt'
    || prompt.className === 'CoinFlipPrompt'
    || prompt.className === 'SelectPrompt'
    || prompt.className === 'SelectOptionPrompt'
    || prompt.className === 'ChooseAttackPrompt'
    || prompt.className === 'ChooseCardsPrompt'
    || prompt.className === 'ChoosePrizePrompt'
    || prompt.className === 'ChooseEnergyPrompt'
    || prompt.className === 'DiscardEnergyPrompt'
    || prompt.className === 'MoveEnergyPrompt'
    || prompt.className === 'AttachEnergyPrompt'
    || prompt.className === 'PutDamagePrompt'
    || prompt.className === 'MoveDamagePrompt'
    || prompt.className === 'RemoveDamagePrompt'
  );
}

export function autoResolvablePromptResult(prompt: PromptView | undefined, game: GameView | null | undefined): unknown | undefined {
  if (!prompt) {
    return undefined;
  }
  if (
    prompt.className === 'AlertPrompt'
    || prompt.className === 'ShowCardsPrompt'
    || prompt.className === 'ConfirmCardsPrompt'
    || prompt.className === 'ShowMulliganPrompt'
  ) {
    return true;
  }
  if (prompt.className === 'ShuffleDeckPrompt') {
    const deckCount = game?.players[prompt.playerIndex]?.deckCount;
    if (typeof deckCount !== 'number' || !Number.isInteger(deckCount) || deckCount < 0) {
      return undefined;
    }
    return Array.from({ length: deckCount }, (_item, index) => index);
  }
  if (prompt.className === 'ConfirmPrompt' && prompt.message === 'GO_FIRST') {
    return true;
  }
  return undefined;
}

export function shouldAutoResolvePrompt(
  prompt: PromptView | undefined,
  autoConfirmPrompts: boolean,
  result: unknown,
  allowForcedAutoResolve = true,
): boolean {
  if (!prompt || result === undefined) {
    return false;
  }
  if (prompt.fields.playbackOnly === true) {
    return false;
  }
  if (prompt.className === 'ShuffleDeckPrompt') {
    return true;
  }
  if (isForcedAutoResolvePrompt(prompt)) {
    return allowForcedAutoResolve;
  }
  return autoConfirmPrompts;
}

export function isForcedAutoResolvePrompt(prompt: PromptView | undefined): boolean {
  return prompt?.className === 'ShuffleDeckPrompt'
    || (prompt?.className === 'ConfirmPrompt' && prompt.message === 'GO_FIRST');
}

/**
 * True when PromptHost renders a usable, player-operable UI for this prompt.
 * The safety-advance button ("選べない時はここから進める") is only shown when this is
 * false, so a player is never offered a silent auto-pick next to a working picker —
 * deck-search choices (ポケパッド・トウコ等) must always be made by the player.
 */
export function promptHasInteractiveUi(prompt: PromptView | null | undefined): boolean {
  if (!prompt) {
    return false;
  }
  switch (prompt.className) {
    case 'AlertPrompt':
    case 'ShowCardsPrompt':
    case 'ConfirmCardsPrompt':
    case 'ShowMulliganPrompt':
    case 'WaitPrompt':
    case 'ConfirmPrompt':
    case 'CoinFlipPrompt':
    case 'ChooseAttackPrompt':
    case 'SelectPrompt':
    case 'SelectOptionPrompt':
      return true;
    case 'ChooseCardsPrompt':
    case 'ChooseEnergyPrompt':
    case 'DiscardEnergyPrompt':
    case 'MoveEnergyPrompt':
    case 'AttachEnergyPrompt':
      return extractPromptCards(prompt.fields).length > 0;
    case 'ChoosePrizePrompt': {
      const prizes = prompt.fields.prizes;
      return Array.isArray(prizes) && prizes.length > 0;
    }
    default:
      // Board-interaction prompts (PutDamage / MoveDamage / ChoosePokemon など) は盤面クリックが
      // 塞がる局面が過去にあったため、脱出用ボタンを残す。未知のクラスも同様。
      return false;
  }
}

export type PromptPlacement = 'center' | 'board' | 'zone';

const BOARD_PROMPT_CLASS_NAMES: ReadonlySet<string> = new Set<string>([
  'AttachEnergyPrompt',
  'PutDamagePrompt',
  'MoveDamagePrompt',
  'RemoveDamagePrompt',
  'ChoosePokemonPrompt',
]);

export function getPromptPlacement(className: string | undefined | null): PromptPlacement {
  if (className && BOARD_PROMPT_CLASS_NAMES.has(className)) {
    return 'board';
  }
  return 'center';
}

export function promptInstanceKey(
  prompt: Pick<PromptView, 'id' | 'className' | 'message'> | null | undefined,
) {
  return prompt ? `${prompt.id}:${prompt.className}:${prompt.message ?? ''}` : '';
}

export function promptOptions(prompt: Pick<PromptView, 'fields'> | null | undefined): Record<string, unknown> {
  return fieldOptions(prompt?.fields);
}

export function fieldOptions(fields: Record<string, unknown> | null | undefined): Record<string, unknown> {
  const options = fields?.options;
  return options && typeof options === 'object' ? (options as Record<string, unknown>) : {};
}

export function promptSlots(
  prompt: Pick<PromptView, 'fields'> | null | undefined,
  fallback: number[] = [SlotType.ACTIVE, SlotType.BENCH],
): number[] {
  const slots = prompt?.fields.slots;
  return Array.isArray(slots) ? (slots as number[]) : fallback;
}

export function promptBlockedIndexes(prompt: Pick<PromptView, 'fields'> | null | undefined): number[] {
  const blocked = promptOptions(prompt).blocked;
  return Array.isArray(blocked) ? blocked.filter((item): item is number => typeof item === 'number') : [];
}

export function promptBlockedTargets(
  prompt: Pick<PromptView, 'fields'> | null | undefined,
  key: 'blocked' | 'blockedTo' = 'blocked',
): CardTarget[] {
  const blocked = promptOptions(prompt)[key];
  return Array.isArray(blocked) ? (blocked as CardTarget[]) : [];
}

export function extractPromptCards(fields: Record<string, unknown> | null | undefined): IndexedCardView[] {
  const cardList = (fields?.cardList as IndexedCardView[] | undefined) ?? (fields?.cards as IndexedCardView[] | undefined);
  if (Array.isArray(cardList)) {
    return cardList;
  }
  const energy = fields?.energy as Array<{ index?: number; card?: CardView }> | undefined;
  if (Array.isArray(energy)) {
    return energy.map((item, index) => ({ index: item.index ?? index, ...(item.card ?? {}) }) as IndexedCardView);
  }
  return [];
}

export function samePromptIndexes(left: number[], right: number[]) {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

export function prunePromptIndexes(indexes: number[], isSelectable: (index: number) => boolean, maxSelections: number) {
  return indexes.filter((index) => isSelectable(index)).slice(0, maxSelections);
}

/**
 * The raw CABT selection descriptor carried on a prompt (min/max counts and the option list).
 * The native CABT engine raises when a submitted selection's length falls outside
 * [minCount, maxCount] or contains out-of-range / duplicate option indexes, which surfaces as an
 * HTTP 400 and a frozen board. These helpers keep every synthesized selection engine-legal.
 */
type CabtSelectLike = {
  minCount?: number;
  maxCount?: number;
  option?: unknown[];
};

export function cabtSelectFromPrompt(prompt: Pick<PromptView, 'fields'> | null | undefined): CabtSelectLike | null {
  const raw = prompt?.fields?.cabtSelect;
  return raw && typeof raw === 'object' ? (raw as CabtSelectLike) : null;
}

function firstFiniteInt(values: unknown[], fallback: number): number {
  for (const value of values) {
    const n = Number(value);
    if (Number.isFinite(n)) {
      return Math.trunc(n);
    }
  }
  return fallback;
}

function clampInt(value: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, value));
}

function normalizeSelectionValue(value: unknown): number[] | null {
  if (value === null || value === undefined || value === true) {
    return [];
  }
  if (typeof value === 'number' && Number.isInteger(value)) {
    return [value];
  }
  if (Array.isArray(value) && value.every((item) => typeof item === 'number' && Number.isInteger(item))) {
    return value as number[];
  }
  return null;
}

function selectionLimits(prompt: Pick<PromptView, 'fields'> | null | undefined, select: CabtSelectLike) {
  const optionCount = Array.isArray(select.option) ? select.option.length : 0;
  const options = promptOptions(prompt);
  const min = clampInt(firstFiniteInt([options.min, select.minCount], 0), 0, optionCount);
  const max = clampInt(firstFiniteInt([options.max, select.maxCount], optionCount), min, optionCount);
  return { optionCount, min, max };
}

/**
 * Coerce an arbitrary prompt result into a selection the CABT engine will accept: distinct,
 * in-range option indexes whose count sits within [min, max]. Over-long selections are trimmed
 * and under-long ones are padded with the lowest unused indexes (mirroring the reference agent).
 * Returns `null` when the prompt is not a CABT selection or the value is not selection-shaped, so
 * the caller can forward the original value untouched.
 */
export function legalizeCabtSelection(value: unknown, prompt: Pick<PromptView, 'fields'> | null | undefined): number[] | null {
  const select = cabtSelectFromPrompt(prompt);
  if (!select) {
    return null;
  }
  const normalized = normalizeSelectionValue(value);
  if (normalized === null) {
    return null;
  }
  const { optionCount, min, max } = selectionLimits(prompt, select);
  const seen = new Set<number>();
  const cleaned: number[] = [];
  for (const index of normalized) {
    if (index >= 0 && index < optionCount && !seen.has(index)) {
      seen.add(index);
      cleaned.push(index);
    }
  }
  const result = cleaned.slice(0, max);
  for (let index = 0; result.length < min && index < optionCount; index += 1) {
    if (!seen.has(index)) {
      seen.add(index);
      result.push(index);
    }
  }
  return result;
}

/**
 * The always-legal "advance" move: the first `maxCount` option indexes, matching the CABT
 * reference agent (`list(range(select.maxCount))`). Used by the "選べない時はここから進める" escape hatch.
 */
export function firstLegalCabtSelection(prompt: Pick<PromptView, 'fields'> | null | undefined): number[] {
  const select = cabtSelectFromPrompt(prompt);
  if (!select) {
    return [];
  }
  const { max } = selectionLimits(prompt, select);
  return Array.from({ length: max }, (_unused, index) => index);
}
