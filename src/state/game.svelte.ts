import type { EngineResponse, GameView } from '../lib/game/types';
import { viewSettingsStore } from './viewSettings.svelte';

export class GameStore {
  game = $state<GameView | null>(null);
  error = $state('');
  busy = $state(false);
  resolvingPrompt = $state(false);
  playingSequence = $state(false);
  /** Snapshots of every board state shown this match, for the in-match review rewind. */
  history = $state<GameView[]>([]);
  /** null = following the live game; otherwise an index into `history` being reviewed. */
  reviewIndex = $state<number | null>(null);
  /** How many past decisions the engine can rewind with the undo command. */
  undoCount = $state(0);
  private playbackConfirmResolve: (() => void) | null = null;
  private generation = 0;

  get currentPrompt() {
    return this.game?.prompts[0];
  }

  get gameFinished() {
    return this.game?.phase === 7;
  }

  get reviewing() {
    return this.reviewIndex !== null;
  }

  /** The view to render: the reviewed historical frame while rewound, else the live game. */
  get displayView() {
    if (this.reviewIndex === null) {
      return this.game;
    }
    return this.history[this.reviewIndex] ?? this.game;
  }

  get canStepBack() {
    if (!this.history.length) return false;
    return this.reviewIndex === null ? this.history.length > 1 : this.reviewIndex > 0;
  }

  get reviewLabel() {
    if (this.reviewIndex === null) return '';
    return `${this.reviewIndex + 1} / ${this.history.length}`;
  }

  stepBack() {
    if (!this.history.length) return;
    const current = this.reviewIndex ?? this.history.length - 1;
    this.reviewIndex = Math.max(0, current - 1);
  }

  stepForward() {
    if (this.reviewIndex === null) return;
    if (this.reviewIndex >= this.history.length - 1) {
      this.reviewIndex = null;
      return;
    }
    this.reviewIndex += 1;
  }

  returnToLive() {
    this.reviewIndex = null;
  }

  /** After an engine undo the recorded frames describe an abandoned branch; restart
   * the in-match review history from the restored state. */
  restartHistoryFromCurrent() {
    this.history = this.game ? [this.game] : [];
    this.reviewIndex = null;
  }

  private recordHistory(sequence: GameView[] | undefined, view: GameView | null | undefined) {
    const frames = sequence?.length ? sequence : view ? [view] : [];
    if (!frames.length) return;
    this.history = [...this.history, ...frames];
    if (this.history.length > 600) {
      this.history = this.history.slice(-600);
    }
  }

  setError(message: string) {
    this.error = message;
  }

  reset() {
    this.generation += 1;
    this.game = null;
    this.error = '';
    this.busy = false;
    this.resolvingPrompt = false;
    this.playingSequence = false;
    this.history = [];
    this.reviewIndex = null;
    this.undoCount = 0;
    this.playbackConfirmResolve?.();
    this.playbackConfirmResolve = null;
  }

  async run(command: () => Promise<EngineResponse>) {
    const generation = this.generation;
    this.busy = true;
    try {
      return await this.apply(await command(), generation);
    } finally {
      if (generation === this.generation) {
        this.busy = false;
      }
    }
  }

  async resolve(command: () => Promise<EngineResponse>) {
    const generation = this.generation;
    this.resolvingPrompt = true;
    try {
      return await this.apply(await command(), generation);
    } finally {
      if (generation === this.generation) {
        this.resolvingPrompt = false;
      }
    }
  }

  /** 再生中のアニメーションを直ちに終わらせる（投了などの割り込み操作用）。 */
  fastForwardSequence() {
    if (this.playingSequence) {
      this.skipSequenceRequested = true;
      this.confirmPlaybackPrompt();
    }
  }

  private skipSequenceRequested = false;

  async apply(response: EngineResponse, generation = this.generation) {
    if (generation !== this.generation) {
      return response;
    }
    if (response.ok) {
      const sequence = response.sequence ?? [];
      const needsPlayback = sequence.some((view, index) =>
        hasPlaybackPrompt(view)
        || (viewSettingsStore.animateActions && (response.sequencePlayback?.[index] ?? 'animate') === 'animate'));
      if (sequence.length) {
        this.playingSequence = needsPlayback;
        try {
          for (let index = 0; index < sequence.length; index += 1) {
            if (this.skipSequenceRequested) {
              break;
            }
            const view = sequence[index];
            const playback = response.sequencePlayback?.[index] ?? 'animate';
            this.game = view;
            this.error = '';
            if (hasPlaybackPrompt(view)) {
              this.resolvingPrompt = false;
              await this.waitForPlaybackConfirm();
              if (generation !== this.generation) {
                return response;
              }
            } else if (viewSettingsStore.animateActions && playback === 'animate') {
              await wait(clampedActionStepDelay());
              if (generation !== this.generation) {
                return response;
              }
            }
          }
        } finally {
          if (generation === this.generation) {
            this.playingSequence = false;
            this.skipSequenceRequested = false;
          }
        }
      }
      if (generation !== this.generation) {
        return response;
      }
      this.game = response.view;
      this.error = '';
      this.recordHistory(response.sequence, response.view);
      if (typeof response.undoCount === 'number') {
        this.undoCount = response.undoCount;
      }
      return response;
    }

    this.error = response.error;
    if (response.view) {
      this.game = response.view;
    }
    return response;
  }

  confirmPlaybackPrompt() {
    this.playbackConfirmResolve?.();
    this.playbackConfirmResolve = null;
  }

  private waitForPlaybackConfirm() {
    return new Promise<void>((resolve) => {
      this.playbackConfirmResolve = resolve;
    });
  }
}

export const gameStore = new GameStore();

function clampedActionStepDelay() {
  return Math.min(2500, Math.max(50, Math.round(viewSettingsStore.actionStepDelayMs)));
}

function wait(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function hasPlaybackPrompt(view: GameView) {
  return view.prompts.some((prompt) => prompt.fields.playbackOnly === true);
}
