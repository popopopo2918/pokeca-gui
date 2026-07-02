import type { CardView } from '../lib/game/types';

class CardPreviewStore {
  hovered = $state<CardView | null>(null);

  set(card: CardView | null | undefined) {
    this.hovered = card ?? null;
  }

  clear(card?: CardView | null) {
    // Only clear if the leaving card is the one currently shown (avoids flicker when
    // moving between adjacent cards fires leave-after-enter out of order).
    if (!card || this.hovered === card) {
      this.hovered = null;
    }
  }
}

export const cardPreviewStore = new CardPreviewStore();
