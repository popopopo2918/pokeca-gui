import type { EngineResponse } from '../lib/game/types';
import { gameStore } from './game.svelte';
import { promptLifecycleStore } from './promptLifecycle.svelte';
import { selectionStore } from './selection.svelte';

class GameSessionStore {
  async run(command: () => Promise<EngineResponse>) {
    const response = await gameStore.run(command);
    this.afterCommand(response);
    return response;
  }

  async resolve(command: () => Promise<EngineResponse>) {
    const response = await gameStore.resolve(command);
    this.afterCommand(response);
    return response;
  }

  reset() {
    gameStore.reset();
    selectionStore.clearAll();
    promptLifecycleStore.reset();
  }

  syncExternalUpdate() {
    if (gameStore.game) {
      this.afterCommand({ ok: true, view: gameStore.game });
    }
  }

  /** Apply a view update that did not come from this client's own command
   * (e.g., the opponent's move arriving over an online-room poll). */
  async applyExternal(response: EngineResponse) {
    const applied = await gameStore.apply(response);
    this.afterCommand(applied);
    return applied;
  }

  private afterCommand(response: EngineResponse) {
    promptLifecycleStore.syncPromptScopedState(response.view?.prompts[0] ?? gameStore.game?.prompts[0]);
    promptLifecycleStore.resetCommandSelection(response.view?.prompts.length ?? gameStore.game?.prompts.length ?? 0);
  }
}

export const gameSessionStore = new GameSessionStore();
