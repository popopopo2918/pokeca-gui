import { describe, expect, it } from 'vitest';
import { formatCabtDeckList, parseDeckList, SAMPLE_DECK } from './deckImport';

describe('deck import', () => {
  it('skips section count headers and expands the default deck to 60 cards', () => {
    const parsed = parseDeckList(SAMPLE_DECK);

    expect(parsed.errors).toEqual([]);
    expect(parsed.cards).toHaveLength(60);
    // Collector numbers are stripped, but the "<name> <SET>" pair the engine resolves is kept.
    expect(parsed.cards).toContain('キチキギスex SFA');
    expect(parsed.cards).toContain('テレパス【超】エネルギー POR');
    expect(parsed.cards.filter((card) => card === 'フーディン MEG')).toHaveLength(3);
    expect(parsed.cards).not.toContain('キチキギスex SFA 38');
    expect(parsed.cards).not.toContain('ポケモン: 22');
    expect(parsed.cards).not.toContain('トレーナーズ: 32');
    expect(parsed.cards).not.toContain('エネルギー: 6');
  });

  it('resolves a bare Japanese card name (no set code) to its card id', () => {
    const parsed = parseDeckList('1 リッチエネルギー');

    expect(parsed.errors).toEqual([]);
    expect(parsed.cards).toEqual(['13']);
  });

  it('reports ambiguous bare names and asks for a set code', () => {
    const parsed = parseDeckList('3 フーディン');

    expect(parsed.cards).toEqual([]);
    expect(parsed.errors[0]).toContain('複数のカード');
  });

  it('reports unknown bare names', () => {
    const parsed = parseDeckList('1 そんなカードはない');

    expect(parsed.cards).toEqual([]);
    expect(parsed.errors[0]).toContain('見つかりません');
  });

  it('normalizes accented names from deck exports', () => {
    const parsed = parseDeckList('1 Poké Pad POR 81');

    expect(parsed.errors).toEqual([]);
    expect(parsed.cards).toEqual(['Poke Pad POR']);
  });

  it('normalizes TCG Live basic energy shorthand', () => {
    const parsed = parseDeckList('7 Basic {W} Energy MEE 3');

    expect(parsed.errors).toEqual([]);
    expect(parsed.cards).toEqual([
      'Water Energy MEE',
      'Water Energy MEE',
      'Water Energy MEE',
      'Water Energy MEE',
      'Water Energy MEE',
      'Water Energy MEE',
      'Water Energy MEE',
    ]);
  });

  it('formats CABT deck IDs as grouped import text', () => {
    const deck = [
      ...Array.from({ length: 4 }, () => '723'),
      ...Array.from({ length: 2 }, () => '1145'),
      ...Array.from({ length: 54 }, () => '3'),
    ].join('\n');

    const formatted = formatCabtDeckList(deck, [
      { id: 3, name: 'Basic {W} Energy', set: 'SVE', setNumber: '3', cardType: 5 },
      { id: 723, name: 'Mega Abomasnow ex', set: 'MEG', setNumber: '36', cardType: 0 },
      { id: 1145, name: 'Mega Signal', set: 'MEG', setNumber: '121', cardType: 1 },
    ]);

    expect(formatted).toBe(`ポケモン: 4
4 メガユキノオーex MEG 36

トレーナーズ: 2
2 メガシグナル MEG 121

エネルギー: 54
54 基本【水】エネルギー SVE 3`);
    expect(parseDeckList(formatted).cards).toHaveLength(60);
  });
});
