import { SAMPLE_DECK } from '../lib/game/deckImport';
import { parseLocalGameDeck, parseLocalGameDecks } from './deckImportModel';

const STORAGE_KEY = 'cabt.deckImport';

type StoredDecks = { deck1Text?: string; deck2Text?: string; pasted1?: string; pasted2?: string };

// Restore the last-used deck lists so a tester can relaunch and rematch immediately.
function readStoredDecks(): StoredDecks {
  if (typeof window === 'undefined') {
    return {};
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return typeof parsed === 'object' && parsed !== null ? (parsed as StoredDecks) : {};
  } catch {
    return {};
  }
}

const storedDecks = readStoredDecks();

class DeckImportStore {
  deck1Text = $state(typeof storedDecks.deck1Text === 'string' && storedDecks.deck1Text.trim() ? storedDecks.deck1Text : SAMPLE_DECK);
  deck2Text = $state(typeof storedDecks.deck2Text === 'string' && storedDecks.deck2Text.trim() ? storedDecks.deck2Text : SAMPLE_DECK);
  // 「デッキを貼り付け」で入力した内容の退避先。プリセット/保存デッキに切り替えても
  // 貼り付けデッキが失われないよう、切替時にここへ退避し、戻ったとき復元する。
  pasted1 = $state(typeof storedDecks.pasted1 === 'string' && storedDecks.pasted1.trim() ? storedDecks.pasted1 : (storedDecks.deck1Text ?? SAMPLE_DECK));
  pasted2 = $state(typeof storedDecks.pasted2 === 'string' && storedDecks.pasted2.trim() ? storedDecks.pasted2 : (storedDecks.deck2Text ?? SAMPLE_DECK));

  parseLocalGameDecks() {
    return parseLocalGameDecks(this.deck1Text, this.deck2Text);
  }

  parseRemoteDeck() {
    return parseLocalGameDeck(this.deck1Text, 'Your deck');
  }

  // Reads both deck texts so a caller can run this inside $effect and re-save on change.
  persist() {
    const snapshot: StoredDecks = {
      deck1Text: this.deck1Text,
      deck2Text: this.deck2Text,
      pasted1: this.pasted1,
      pasted2: this.pasted2,
    };
    if (typeof window === 'undefined') {
      return;
    }
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
    } catch {
      // Deck texts still apply for the current session when storage is unavailable.
    }
  }

  reset() {
    this.deck1Text = SAMPLE_DECK;
    this.deck2Text = SAMPLE_DECK;
  }
}

export const deckImportStore = new DeckImportStore();
