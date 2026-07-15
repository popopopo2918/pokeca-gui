import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { GameView } from '../lib/game/types';
import { GameStore } from './game.svelte';
import { viewSettingsStore } from './viewSettings.svelte';

function frame(turn: number, playbackOnly = false): GameView {
  return {
    ready: true,
    phase: 3,
    phaseLabel: 'プレイヤーの番',
    turn,
    activePlayerIndex: 0,
    players: [],
    prompts: playbackOnly ? [{
      id: turn,
      className: 'ConfirmPrompt',
      type: 'confirm',
      playerId: 0,
      playerIndex: 0,
      supported: true,
      resultSchema: 'boolean',
      fields: { playbackOnly: true },
    }] : [],
    logs: [],
    events: [],
  };
}

describe('GameStore sequence playback', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    viewSettingsStore.animateActions = true;
    viewSettingsStore.actionStepDelayMs = 650;
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('instantフレームは650ms待たずに最終ビューへ進む', async () => {
    const store = new GameStore();
    const applied = store.apply({
      ok: true,
      view: frame(2),
      sequence: [frame(1), frame(2)],
      sequencePlayback: ['instant', 'instant'],
    });

    await expect(applied).resolves.toMatchObject({ ok: true });
    expect(store.game?.turn).toBe(2);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('animateフレームは設定時間ごとに再生する', async () => {
    const store = new GameStore();
    const applied = store.apply({
      ok: true,
      view: frame(2),
      sequence: [frame(1), frame(2)],
      sequencePlayback: ['animate', 'animate'],
    });

    expect(store.game?.turn).toBe(1);
    await vi.advanceTimersByTimeAsync(650);
    expect(store.game?.turn).toBe(2);
    await vi.advanceTimersByTimeAsync(650);
    await expect(applied).resolves.toMatchObject({ ok: true });
  });

  it('playbackOnlyはinstant指定でも確認されるまで進めない', async () => {
    const store = new GameStore();
    const applied = store.apply({
      ok: true,
      view: frame(2),
      sequence: [frame(1, true), frame(2)],
      sequencePlayback: ['instant', 'instant'],
    });

    await Promise.resolve();
    expect(store.game?.turn).toBe(1);
    store.confirmPlaybackPrompt();
    await expect(applied).resolves.toMatchObject({ ok: true });
    expect(store.game?.turn).toBe(2);
  });
});
