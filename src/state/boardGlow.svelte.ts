/**
 * Tracks which board Pokémon should currently glow (e.g. right after its Ability is used). Board
 * slots read this store directly and match by absolute player index + card id, so no props have to
 * be threaded through the board component tree.
 */
class BoardGlowStore {
  key = $state('');
  private timer: ReturnType<typeof setTimeout> | undefined;

  glow(playerIndex: number, cardId: number, ms = 1500): void {
    this.key = `${playerIndex}:${cardId}`;
    clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.key = '';
    }, ms);
  }

  isGlowing(playerIndex: number | undefined, cardId: number | undefined): boolean {
    if (playerIndex === undefined || cardId === undefined || this.key === '') {
      return false;
    }
    return this.key === `${playerIndex}:${cardId}`;
  }

  reset(): void {
    clearTimeout(this.timer);
    this.key = '';
  }
}

export const boardGlowStore = new BoardGlowStore();
