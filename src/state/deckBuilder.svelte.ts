import {
  getCatalog,
  getCatalogMap,
  validateDeck,
  buildCabtIdCsv,
  buildSetupDeckText,
  type CatalogCard,
  type CardCategory,
  type DeckValidation,
} from '../lib/cards/cardCatalog';
import {
  loadLibrary,
  saveLibrary,
  loadCurrentCounts,
  saveCurrentCounts,
  createDeckId,
  sanitizeCounts,
  type SavedDeck,
  type DeckCounts,
} from '../lib/cards/deckStorage';

export type DeckGroup = { card: CatalogCard; count: number };
export type DeckGroups = Record<CardCategory, DeckGroup[]>;

const CATEGORY_ORDER: CardCategory[] = ['pokemon', 'trainer', 'energy'];

class DeckBuilderStore {
  counts = $state<DeckCounts>({});
  library = $state<SavedDeck[]>([]);
  activeDeckId = $state<string | null>(null);
  activeDeckName = $state<string>('新しいデッキ');

  private readonly map = getCatalogMap();

  init() {
    this.counts = loadCurrentCounts();
    this.library = loadLibrary();
  }

  private persist() {
    saveCurrentCounts(this.counts);
  }

  get total(): number {
    return Object.values(this.counts).reduce((sum, n) => sum + n, 0);
  }

  get validation(): DeckValidation {
    return validateDeck(this.counts, this.map);
  }

  countOf(id: number): number {
    return this.counts[id] ?? 0;
  }

  get groups(): DeckGroups {
    const groups: DeckGroups = { pokemon: [], trainer: [], energy: [] };
    for (const [rawId, count] of Object.entries(this.counts)) {
      if (!count) continue;
      const card = this.map.get(Number(rawId));
      if (!card) continue;
      groups[card.category].push({ card, count });
    }
    for (const category of CATEGORY_ORDER) {
      groups[category].sort((a, b) => a.card.name.localeCompare(b.card.name));
    }
    return groups;
  }

  setCount(id: number, next: number) {
    const card = this.map.get(id);
    const limit = card ? card.copyLimit : 4;
    const clamped = Math.max(0, Math.min(next, limit));
    if (clamped <= 0) {
      const { [id]: _drop, ...rest } = this.counts;
      this.counts = rest;
    } else {
      this.counts = { ...this.counts, [id]: clamped };
    }
    this.persist();
  }

  add(id: number, delta = 1) {
    this.setCount(id, this.countOf(id) + delta);
  }

  remove(id: number, delta = 1) {
    this.setCount(id, this.countOf(id) - delta);
  }

  clear() {
    this.counts = {};
    this.activeDeckId = null;
    this.activeDeckName = '新しいデッキ';
    this.persist();
  }

  loadCounts(counts: DeckCounts) {
    this.counts = sanitizeCounts(counts);
    this.persist();
  }

  // --- export helpers ---
  toCabtCsv(): string {
    return buildCabtIdCsv(this.counts);
  }

  toSetupDeckText(): string {
    return buildSetupDeckText(this.counts, getCatalog());
  }

  // --- library ---
  refreshLibrary() {
    this.library = loadLibrary();
  }

  saveAs(name: string): SavedDeck {
    const deck: SavedDeck = {
      id: createDeckId(),
      name: name.trim() || '無題のデッキ',
      counts: { ...this.counts },
      updatedAt: Date.now(),
    };
    this.library = [deck, ...this.library];
    saveLibrary(this.library);
    this.activeDeckId = deck.id;
    this.activeDeckName = deck.name;
    return deck;
  }

  saveActive(): void {
    if (!this.activeDeckId) {
      this.saveAs(this.activeDeckName);
      return;
    }
    this.library = this.library.map((deck) =>
      deck.id === this.activeDeckId
        ? { ...deck, counts: { ...this.counts }, name: this.activeDeckName.trim() || deck.name, updatedAt: Date.now() }
        : deck,
    );
    saveLibrary(this.library);
  }

  loadDeck(id: string): void {
    const deck = this.library.find((d) => d.id === id);
    if (!deck) return;
    this.counts = { ...deck.counts };
    this.activeDeckId = deck.id;
    this.activeDeckName = deck.name;
    this.persist();
  }

  duplicateDeck(id: string): void {
    const deck = this.library.find((d) => d.id === id);
    if (!deck) return;
    const copy: SavedDeck = {
      id: createDeckId(),
      name: `${deck.name} のコピー`,
      counts: { ...deck.counts },
      updatedAt: Date.now(),
    };
    this.library = [copy, ...this.library];
    saveLibrary(this.library);
  }

  deleteDeck(id: string): void {
    this.library = this.library.filter((d) => d.id !== id);
    saveLibrary(this.library);
    if (this.activeDeckId === id) {
      this.activeDeckId = null;
    }
  }

  renameDeck(id: string, name: string): void {
    this.library = this.library.map((deck) => (deck.id === id ? { ...deck, name: name.trim() || deck.name } : deck));
    saveLibrary(this.library);
    if (this.activeDeckId === id) {
      this.activeDeckName = name.trim() || this.activeDeckName;
    }
  }
}

export const deckBuilderStore = new DeckBuilderStore();
