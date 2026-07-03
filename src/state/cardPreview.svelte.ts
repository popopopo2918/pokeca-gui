import type { CardView } from '../lib/game/types';

class CardPreviewStore {
  hovered = $state<CardView | null>(null);
  // Which tile currently owns the preview. Ownership is tracked by a per-tile token
  // (not by the card object): views are rebuilt on every game update, so the card
  // object identity changes mid-hover and a `hovered === card` check would leave the
  // zoom stuck on screen after the mouse leaves.
  private owner: object | null = null;

  set(card: CardView | null | undefined, owner: object) {
    if (!card) {
      return;
    }
    this.hovered = card;
    this.owner = owner;
  }

  clear(owner: object) {
    // Only the owning tile may clear (avoids flicker when moving between adjacent
    // cards fires leave-after-enter out of order).
    if (this.owner === owner) {
      this.hovered = null;
      this.owner = null;
    }
  }
}

export const cardPreviewStore = new CardPreviewStore();
