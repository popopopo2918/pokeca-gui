import { describe, expect, it } from 'vitest';
import { TOURNAMENT_DECKS } from './presetDecks';
import { deckCountsToText, getCatalogMap, resolveDeckTextEntries } from '../cards/cardCatalog';

describe('tournament preset decks', () => {
  const catalog = getCatalogMap();

  it.each(TOURNAMENT_DECKS.map((deck) => [deck.name, deck] as const))('%s は60枚で全カードがプールに存在する', (_name, deck) => {
    const total = Object.values(deck.counts).reduce((sum, count) => sum + count, 0);
    expect(total).toBe(60);
    for (const id of Object.keys(deck.counts).map(Number)) {
      expect(catalog.has(id), `card ${id} missing from catalog`).toBe(true);
    }
  });

  it.each(TOURNAMENT_DECKS.map((deck) => [deck.name, deck] as const))('%s はテキスト変換後も全行解決できる', (_name, deck) => {
    const text = deckCountsToText(deck.counts);
    const entries = resolveDeckTextEntries(text);
    const unresolved = entries.filter((entry) => !entry.card);
    expect(unresolved, JSON.stringify(unresolved.map((e) => e.label))).toEqual([]);
    const total = entries.reduce((sum, entry) => sum + entry.count, 0);
    expect(total).toBe(60);
  });
});
