<script lang="ts">
  // Brief top toast on turn change — visible but does not cover the battle zone.
  type Props = {
    turn: number;
    activePlayerName?: string;
    activePlayerIndex?: number;
    selfIndex?: number;
    holdMs?: number;
  };

  let { turn, activePlayerName = '', activePlayerIndex, selfIndex, holdMs = 1600 }: Props = $props();

  let key = $derived(`${turn}:${activePlayerIndex ?? activePlayerName}`);
  let shownKey = $state('');
  let visible = $state(false);
  let name = $state('');
  let isSelf = $state(false);
  let shownTurn = $state(0);
  let timer: ReturnType<typeof setTimeout> | undefined;

  $effect(() => {
    const nextKey = key;
    if (nextKey && nextKey !== shownKey && activePlayerName) {
      shownKey = nextKey;
      name = activePlayerName;
      isSelf = activePlayerIndex !== undefined && selfIndex !== undefined && activePlayerIndex === selfIndex;
      shownTurn = turn;
      visible = true;
      clearTimeout(timer);
      timer = setTimeout(() => {
        visible = false;
      }, holdMs);
    }
    return () => clearTimeout(timer);
  });
</script>

{#if visible && name}
  {#key shownKey}
    <div class="turn-banner" class:self={isSelf} role="status" aria-live="polite">
      <span class="turn-label">ターン {shownTurn}</span>
      <span class="turn-sep" aria-hidden="true">·</span>
      <strong class="turn-name">{name} の番</strong>
    </div>
  {/key}
{/if}

<style>
  .turn-banner {
    position: fixed;
    top: 10px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 44;
    display: flex;
    align-items: center;
    gap: 8px;
    max-width: min(420px, 72vw);
    padding: 6px 16px;
    border-radius: 999px;
    border: 1px solid var(--button-border);
    background: var(--surface-glass-bg);
    box-shadow: var(--surface-toolbar-shadow);
    backdrop-filter: blur(var(--backdrop-blur));
    pointer-events: none;
    animation: turn-banner-in 220ms ease-out;
  }

  .turn-banner.self {
    border-color: rgba(255, 214, 92, 0.85);
    box-shadow: 0 0 0 1px rgba(255, 214, 92, 0.45), var(--surface-toolbar-shadow);
  }

  .turn-label {
    color: var(--text-secondary);
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.06em;
    white-space: nowrap;
  }

  .turn-sep {
    color: var(--text-muted);
    font-size: 12px;
    line-height: 1;
  }

  .turn-name {
    color: var(--text-primary);
    font-size: 14px;
    font-weight: 900;
    line-height: 1.1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  @keyframes turn-banner-in {
    from { opacity: 0; transform: translate(-50%, -10px); }
    to { opacity: 1; transform: translateX(-50%); }
  }

  @media (prefers-reduced-motion: reduce) {
    .turn-banner { animation: none; }
  }
</style>
