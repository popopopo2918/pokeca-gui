import { describe, it, expect } from 'vitest';
import {
  getCatalog,
  getCatalogMap,
  validateDeck,
  filterCatalog,
  EMPTY_FILTERS,
  buildCabtIdCsv,
  listSets,
  listTypes,
} from './cardCatalog';

describe('card catalog', () => {
  const cards = getCatalog();

  it('loads every card with merged JP name and a resolvable image URL', () => {
    expect(cards.length).toBe(1267);
    const lucario = cards.find((c) => c.id === 678);
    expect(lucario?.category).toBe('pokemon');
    expect(lucario?.nameJa).toContain('ルカリオ');
    expect(lucario?.megaEx).toBe(true);
    expect(lucario?.imageUrl).toBe('/card-images-jp/678.webp');
    expect(lucario?.movesJa.length).toBeGreaterThan(0);
  });

  it('classifies energy and trainers with sensible copy limits', () => {
    const basicEnergy = cards.find((c) => c.id === 1);
    expect(basicEnergy?.category).toBe('energy');
    expect(basicEnergy?.copyLimit).toBeGreaterThan(4);

    const pokemon = cards.find((c) => c.category === 'pokemon');
    expect(pokemon?.copyLimit).toBe(4);
  });

  it('filters by query, category and set', () => {
    const byJa = filterCatalog(cards, { ...EMPTY_FILTERS, query: 'ルカリオ' });
    expect(byJa.some((c) => c.id === 678)).toBe(true);

    const energyOnly = filterCatalog(cards, { ...EMPTY_FILTERS, category: 'energy' });
    expect(energyOnly.every((c) => c.category === 'energy')).toBe(true);

    expect(listSets(cards)).toContain('MEG');
    expect(listTypes(cards).length).toBeGreaterThan(0);
  });

  it('flags illegal decks and accepts a legal 60-card deck', () => {
    const map = getCatalogMap();
    expect(validateDeck({}, map).ok).toBe(false);

    // 60 copies of a basic energy: right size but missing a basic Pokemon.
    const allEnergy = validateDeck({ 3: 60 }, map);
    expect(allEnergy.total).toBe(60);
    expect(allEnergy.ok).toBe(false);

    // a basic Pokemon + filler basic energy reaching 60 should pass.
    const basicPokemon = getCatalog().find((c) => c.category === 'pokemon' && c.basic);
    expect(basicPokemon).toBeDefined();
    const legal = validateDeck({ [basicPokemon!.id]: 4, 3: 56 }, map);
    expect(legal.ok).toBe(true);
    expect(legal.byCategory.pokemon).toBe(4);
  });

  it('expands counts into a 60-line CABT id list', () => {
    const csv = buildCabtIdCsv({ 10: 2, 20: 3 });
    expect(csv.split('\n')).toHaveLength(5);
  });
});
