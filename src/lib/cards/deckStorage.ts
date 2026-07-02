export type DeckCounts = Record<number, number>;

export type SavedDeck = {
  id: string;
  name: string;
  counts: DeckCounts;
  updatedAt: number;
};

const LIBRARY_KEY = 'cabt:deckLibrary:v1';
const CURRENT_KEY = 'cabt:deckBuilder:current:v1';

function storage(): Storage | null {
  try {
    return typeof localStorage !== 'undefined' ? localStorage : null;
  } catch {
    return null;
  }
}

export function createDeckId(): string {
  return `deck-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export function sanitizeCounts(raw: unknown): DeckCounts {
  const counts: DeckCounts = {};
  if (!raw || typeof raw !== 'object') return counts;
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    const id = Number(key);
    const count = Number(value);
    if (Number.isInteger(id) && id > 0 && Number.isFinite(count) && count > 0) {
      counts[id] = Math.floor(count);
    }
  }
  return counts;
}

export function loadLibrary(): SavedDeck[] {
  const store = storage();
  if (!store) return [];
  try {
    const parsed = JSON.parse(store.getItem(LIBRARY_KEY) ?? '[]');
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((d): d is SavedDeck => !!d && typeof d.id === 'string' && typeof d.name === 'string')
      .map((d) => ({ id: d.id, name: d.name, counts: sanitizeCounts(d.counts), updatedAt: Number(d.updatedAt) || Date.now() }));
  } catch {
    return [];
  }
}

export function saveLibrary(decks: SavedDeck[]): void {
  storage()?.setItem(LIBRARY_KEY, JSON.stringify(decks));
}

export function loadCurrentCounts(): DeckCounts {
  const store = storage();
  if (!store) return {};
  try {
    return sanitizeCounts(JSON.parse(store.getItem(CURRENT_KEY) ?? '{}'));
  } catch {
    return {};
  }
}

export function saveCurrentCounts(counts: DeckCounts): void {
  storage()?.setItem(CURRENT_KEY, JSON.stringify(counts));
}
