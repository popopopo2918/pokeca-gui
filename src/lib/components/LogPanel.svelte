<script lang="ts">
  import { labelFor } from '../game/labels';
  import type { ActionTimelineEvent, LogView } from '../game/types';

  type Props = {
    logs?: LogView[];
    timeline?: ActionTimelineEvent[];
  };

  let { logs = [], timeline = [] }: Props = $props();
  let entries = $derived(timeline.length ? timeline : logs);
  // Show the full log (newest first), scrollable — every action is recorded, nothing is truncated.
  let visibleEntries = $derived(entries.slice().reverse());

  function playerIndexOf(entry: LogView | ActionTimelineEvent): number | undefined {
    return 'playerIndex' in entry ? entry.playerIndex : undefined;
  }
</script>

<aside class="log-panel">
  <h2>{timeline.length ? '行動ログ' : 'ログ'}</h2>
  {#each visibleEntries as entry}
    <p class:player-0={playerIndexOf(entry) === 0} class:player-1={playerIndexOf(entry) === 1}>
      {labelFor(entry.message)}
    </p>
  {/each}
</aside>

<style>
  .log-panel {
    position: absolute;
    z-index: 8;
    right: 14px;
    top: auto;
    bottom: 14px;
    width: 210px;
    transform: none;
    align-self: center;
    max-height: min(46vh, 460px);
    overflow: auto;
    padding: 10px;
    border: 1px solid var(--surface-toolbar-border);
    border-radius: 6px;
    background: var(--surface-toolbar-bg);
    color: var(--text-secondary);
    box-shadow: var(--surface-toolbar-shadow);
    backdrop-filter: blur(var(--backdrop-blur));
    font-size: 11px;
    line-height: 1.35;
  }

  .log-panel h2 {
    margin: 0 0 7px;
    font-size: 11px;
    color: var(--text-primary);
  }

  .log-panel p {
    margin: 0 0 7px;
    padding-left: 6px;
    border-left: 2px solid transparent;
  }

  .log-panel p.player-0 {
    border-left-color: var(--accent-base);
  }

  .log-panel p.player-1 {
    border-left-color: var(--warning-base);
  }

  @media (max-width: 980px) {
    .log-panel {
      position: static;
      transform: none;
      width: auto;
      max-height: 180px;
    }
  }
</style>
