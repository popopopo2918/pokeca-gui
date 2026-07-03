import { describe, expect, it } from 'vitest';
import {
  autoResolvablePromptResult,
  cabtSelectFromPrompt,
  extractPromptCards,
  fieldOptions,
  firstLegalCabtSelection,
  isForcedAutoResolvePrompt,
  isKnownPrompt,
  legalizeCabtSelection,
  promptBlockedIndexes,
  promptBlockedTargets,
  promptHasInteractiveUi,
  promptInstanceKey,
  promptOptions,
  prunePromptIndexes,
  promptSlots,
  samePromptIndexes,
  shouldAutoResolvePrompt,
} from './prompts';
import { SlotType, targetFor, type GameView, type PromptView } from './types';

describe('prompt helpers', () => {
  it('identifies migrated prompt classes as known prompts', () => {
    expect(isKnownPrompt(prompt('ConfirmPrompt'))).toBe(true);
    expect(isKnownPrompt(prompt('ChooseCardsPrompt'))).toBe(true);
    expect(isKnownPrompt(prompt('ShuffleDeckPrompt'))).toBe(true);
    expect(isKnownPrompt(prompt('ChoosePokemonPrompt'))).toBe(false);
  });

  it('keys prompt component instances by prompt identity', () => {
    expect(promptInstanceKey(prompt('ChooseEnergyPrompt', {}, 9))).toBe('9:ChooseEnergyPrompt:');
    expect(promptInstanceKey({ ...prompt('ChooseCardsPrompt', {}, 9), message: 'CHOOSE_STARTING_POKEMONS' }))
      .toBe('9:ChooseCardsPrompt:CHOOSE_STARTING_POKEMONS');
    expect(promptInstanceKey(undefined)).toBe('');
  });

  it('normalizes prompt options and slots', () => {
    const item = prompt('ChoosePokemonPrompt', {
      slots: [SlotType.ACTIVE],
      options: { min: 1, blocked: [3] },
    });

    expect(promptOptions(item)).toEqual({ min: 1, blocked: [3] });
    expect(fieldOptions(item.fields)).toEqual({ min: 1, blocked: [3] });
    expect(promptSlots(item)).toEqual([SlotType.ACTIVE]);
    expect(promptSlots(prompt('ChoosePokemonPrompt'))).toEqual([SlotType.ACTIVE, SlotType.BENCH]);
  });

  it('extracts blocked indexes and target arrays', () => {
    const target = targetFor(0, 1, SlotType.BENCH, 2);
    const item = prompt('ChoosePokemonPrompt', {
      options: {
        blocked: [1, 'bad', 2],
        blockedTo: [target],
      },
    });

    expect(promptBlockedIndexes(item)).toEqual([1, 2]);
    expect(promptBlockedTargets(item, 'blockedTo')).toEqual([target]);
  });

  it('extracts prompt cards from card lists or energy maps', () => {
    expect(extractPromptCards({ cards: [{ index: 4, name: 'Ralts', fullName: 'Ralts SIT' }] })).toEqual([
      { index: 4, name: 'Ralts', fullName: 'Ralts SIT' },
    ]);
    expect(extractPromptCards({ energy: [{ index: 2, card: { name: 'Psychic Energy', fullName: 'Psychic Energy SVE' } }] })).toEqual([
      { index: 2, name: 'Psychic Energy', fullName: 'Psychic Energy SVE' },
    ]);
  });

  it('prunes selected prompt indexes without hiding value equality', () => {
    expect(prunePromptIndexes([1, 2, 3], (index) => index !== 2, 2)).toEqual([1, 3]);
    expect(samePromptIndexes([1, 3], [1, 3])).toBe(true);
    expect(samePromptIndexes([1, 3], [3, 1])).toBe(false);
  });

  it('auto-resolves shuffle prompts with the current deck order', () => {
    const item = prompt('ShuffleDeckPrompt');
    const game = {
      players: [
        { deckCount: 4 },
      ],
    } as GameView;

    const result = autoResolvablePromptResult(item, game);

    expect(result).toEqual([0, 1, 2, 3]);
    expect(shouldAutoResolvePrompt(item, false, result)).toBe(true);
  });

  it('keeps alert-style auto prompts behind the auto-confirm setting', () => {
    const item = prompt('ShowCardsPrompt');
    const result = autoResolvablePromptResult(item, null);

    expect(result).toBe(true);
    expect(shouldAutoResolvePrompt(item, false, result)).toBe(false);
    expect(shouldAutoResolvePrompt(item, true, result)).toBe(true);
  });

  it('keeps playback reveal prompts manual even when auto-confirm is enabled', () => {
    const item = prompt('ConfirmCardsPrompt', {
      playbackOnly: true,
      cards: [{ name: 'Basic Water Energy', fullName: 'Basic Water Energy' }],
    });
    const result = autoResolvablePromptResult(item, null);

    expect(result).toBe(true);
    expect(shouldAutoResolvePrompt(item, false, result)).toBe(false);
    expect(shouldAutoResolvePrompt(item, true, result)).toBe(false);
  });

  it('does not auto-resolve optional card search prompts', () => {
    const item = prompt('ChooseCardsPrompt', { options: { min: 0, max: 1 }, cardList: [{ name: 'Poké Pad hit', fullName: 'Poké Pad hit' }] });
    const result = autoResolvablePromptResult(item, null);

    expect(result).toBeUndefined();
    expect(shouldAutoResolvePrompt(item, true, result)).toBe(false);
  });

  it('auto-resolves only the setup go-first confirm prompt', () => {
    const goFirst = { ...prompt('ConfirmPrompt'), message: 'GO_FIRST' };
    const ordinaryConfirm = { ...prompt('ConfirmPrompt'), message: 'WANT_TO_DISCARD_ENERGY' };

    const goFirstResult = autoResolvablePromptResult(goFirst, null);
    const ordinaryResult = autoResolvablePromptResult(ordinaryConfirm, null);

    expect(goFirstResult).toBe(true);
    expect(isForcedAutoResolvePrompt(goFirst)).toBe(true);
    expect(shouldAutoResolvePrompt(goFirst, false, goFirstResult)).toBe(true);
    expect(ordinaryResult).toBeUndefined();
    expect(isForcedAutoResolvePrompt(ordinaryConfirm)).toBe(false);
    expect(shouldAutoResolvePrompt(ordinaryConfirm, true, ordinaryResult)).toBe(false);
  });

  it('lets manual flows disable forced prompt auto-resolution', () => {
    const goFirst = { ...prompt('ConfirmPrompt'), message: 'GO_FIRST' };
    const result = autoResolvablePromptResult(goFirst, null);

    expect(shouldAutoResolvePrompt(goFirst, false, result, false)).toBe(false);
    expect(shouldAutoResolvePrompt(goFirst, true, result, false)).toBe(false);
  });

  it('keeps deck shuffles auto-resolved in manual flows', () => {
    const shuffle = prompt('ShuffleDeckPrompt');
    const game = {
      players: [
        { deckCount: 3 },
      ],
    } as GameView;
    const result = autoResolvablePromptResult(shuffle, game);

    expect(result).toEqual([0, 1, 2]);
    expect(shouldAutoResolvePrompt(shuffle, false, result, false)).toBe(true);
  });
});

describe('CABT selection legalization', () => {
  function cabtPrompt(
    select: { minCount: number; maxCount: number; optionCount: number },
    options?: { min?: number; max?: number },
  ): PromptView {
    return prompt('ChooseCardsPrompt', {
      cabtSelect: {
        minCount: select.minCount,
        maxCount: select.maxCount,
        option: Array.from({ length: select.optionCount }, (_unused, index) => ({ index })),
      },
      options: options ?? { min: select.minCount, max: select.maxCount },
    });
  }

  it('leaves an already-legal selection untouched', () => {
    const item = cabtPrompt({ minCount: 1, maxCount: 2, optionCount: 5 });
    expect(legalizeCabtSelection([3], item)).toEqual([3]);
    expect(legalizeCabtSelection([0, 4], item)).toEqual([0, 4]);
  });

  it('pads an empty selection up to minCount (mirrors the reference agent)', () => {
    const item = cabtPrompt({ minCount: 1, maxCount: 1, optionCount: 5 });
    expect(legalizeCabtSelection([], item)).toEqual([0]);
    expect(legalizeCabtSelection(null, item)).toEqual([0]);
    expect(legalizeCabtSelection(true, item)).toEqual([0]);
  });

  it('keeps an empty selection when the prompt is optional (minCount 0)', () => {
    const item = cabtPrompt({ minCount: 0, maxCount: 1, optionCount: 3 });
    expect(legalizeCabtSelection([], item)).toEqual([]);
  });

  it('trims an over-long selection down to maxCount', () => {
    const item = cabtPrompt({ minCount: 1, maxCount: 2, optionCount: 6 });
    expect(legalizeCabtSelection([0, 1, 2, 3], item)).toEqual([0, 1]);
  });

  it('drops out-of-range and duplicate indexes', () => {
    const item = cabtPrompt({ minCount: 1, maxCount: 3, optionCount: 3 });
    expect(legalizeCabtSelection([5, 1, 1, -1, 2], item)).toEqual([1, 2]);
  });

  it('coerces a bare number into a single-index selection', () => {
    const item = cabtPrompt({ minCount: 1, maxCount: 1, optionCount: 4 });
    expect(legalizeCabtSelection(2, item)).toEqual([2]);
  });

  it('honors batched energy-discard limits carried on fields.options', () => {
    // Batched discard: engine maxCount is 1 but the UI submits several indexes at once.
    const item = cabtPrompt({ minCount: 1, maxCount: 1, optionCount: 5 }, { min: 1, max: 3 });
    expect(legalizeCabtSelection([0, 1, 2], item)).toEqual([0, 1, 2]);
  });

  it('passes through non-CABT prompts and non-selection values', () => {
    const nonCabt = prompt('ChoosePokemonPrompt', { options: { min: 1 } });
    expect(cabtSelectFromPrompt(nonCabt)).toBeNull();
    expect(legalizeCabtSelection([1], nonCabt)).toBeNull();

    const cabt = cabtPrompt({ minCount: 1, maxCount: 1, optionCount: 3 });
    expect(legalizeCabtSelection({ energyIndex: 1 }, cabt)).toBeNull();
  });

  it('produces the first maxCount indexes for the advance escape hatch', () => {
    expect(firstLegalCabtSelection(cabtPrompt({ minCount: 0, maxCount: 2, optionCount: 5 }))).toEqual([0, 1]);
    expect(firstLegalCabtSelection(cabtPrompt({ minCount: 1, maxCount: 1, optionCount: 5 }))).toEqual([0]);
    expect(firstLegalCabtSelection(prompt('ConfirmPrompt'))).toEqual([]);
  });

  it('hides the advance escape hatch when a dedicated picker UI is available', () => {
    // 山札サーチ（ポケパッド・トウコ等）の選択はプレイヤーが必ず自分で行う。
    const deckSearch = prompt('ChooseCardsPrompt', {
      cardList: [{ name: 'Dunsparce', fullName: 'Dunsparce', index: 0 }],
      options: { min: 0, max: 1 },
    });
    expect(promptHasInteractiveUi(deckSearch)).toBe(true);

    // 候補が空の ChooseCardsPrompt は操作不能なので脱出用ボタンを残す。
    expect(promptHasInteractiveUi(prompt('ChooseCardsPrompt', { cardList: [] }))).toBe(false);

    // ボタン式のプロンプトは常に操作可能。
    expect(promptHasInteractiveUi(prompt('ConfirmPrompt'))).toBe(true);
    expect(promptHasInteractiveUi(prompt('SelectPrompt', { values: [] }))).toBe(true);

    // 盤面クリック型・未知クラスは脱出用ボタンを残す。
    expect(promptHasInteractiveUi(prompt('ChoosePokemonPrompt'))).toBe(false);
    expect(promptHasInteractiveUi(prompt('PutDamagePrompt'))).toBe(false);
    expect(promptHasInteractiveUi(undefined)).toBe(false);
  });
});

function prompt(className: string, fields: Record<string, unknown> = {}, id = 1): PromptView {
  return {
    id,
    className,
    type: className,
    playerId: 1,
    playerIndex: 0,
    supported: true,
    resultSchema: 'unknown',
    fields,
  };
}
