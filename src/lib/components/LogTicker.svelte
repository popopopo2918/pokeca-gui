<script lang="ts">
  import { labelFor } from '../game/labels';
  import type { ActionTimelineEvent, LogView } from '../game/types';

  type Props = {
    logs?: LogView[];
    timeline?: ActionTimelineEvent[];
    onHide: () => void;
  };

  let { logs = [], timeline = [], onHide }: Props = $props();
  let entries = $derived(timeline.length ? timeline : logs);
  // 直近3件だけの控えめな表示。全ログは従来どおり「ログを表示（L）」で。
  let visibleEntries = $derived(entries.slice(-3));

  function playerIndexOf(entry: LogView | ActionTimelineEvent): number | undefined {
    return 'playerIndex' in entry ? entry.playerIndex : undefined;
  }
</script>

{#if visibleEntries.length}
  <aside class="log-ticker">
    <button class="close" onclick={onHide} title="ミニログを隠す（「表示・デバッグ設定」から再表示できます）">✕</button>
    {#each visibleEntries as entry}
      <p class:player-0={playerIndexOf(entry) === 0} class:player-1={playerIndexOf(entry) === 1}>
        {labelFor(entry.message)}
      </p>
    {/each}
  </aside>
{/if}

<style>
  .log-ticker {
    position: absolute;
    z-index: 7;
    right: 14px;
    bottom: 14px;
    width: 210px;
    padding: 8px 24px 6px 10px;
    border: 1px solid var(--surface-toolbar-border);
    border-radius: 6px;
    background: var(--surface-toolbar-bg);
    color: var(--text-secondary);
    box-shadow: var(--surface-toolbar-shadow);
    backdrop-filter: blur(var(--backdrop-blur));
    font-size: 11px;
    line-height: 1.35;
  }

  .log-ticker p {
    margin: 0 0 5px;
    padding-left: 6px;
    border-left: 2px solid transparent;
  }

  .log-ticker p:last-child {
    margin-bottom: 0;
    color: var(--text-primary);
  }

  .log-ticker p.player-0 {
    border-left-color: var(--accent-base);
  }

  .log-ticker p.player-1 {
    border-left-color: var(--warning-base);
  }

  .log-ticker .close {
    position: absolute;
    top: 4px;
    right: 4px;
    border: 0;
    background: transparent;
    color: var(--text-muted);
    font-size: 11px;
    line-height: 1;
    cursor: pointer;
    padding: 3px;
  }

  .log-ticker .close:hover {
    color: var(--text-primary);
  }
</style>
