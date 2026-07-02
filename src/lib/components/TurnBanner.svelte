<script lang="ts">
  // Prominent banner that flashes on every turn change so it is obvious whose turn it is now
  // (and that the previous turn ended).
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
      <strong class="turn-name">{name} の番</strong>
    </div>
  {/key}
{/if}

<style>
  .turn-banner {
    position: fixed;
    top: 38%;
    left: 50%;
    transform: translate(-50%, -50%);
    z-index: 45;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    padding: 16px 40px;
    border-radius: 16px;
    border: 2px solid var(--button-border);
    background: var(--surface-glass-bg);
    box-shadow: var(--surface-toolbar-shadow);
    backdrop-filter: blur(var(--backdrop-blur));
    pointer-events: none;
    animation: turn-banner-in 260ms ease-out;
  }

  .turn-banner.self {
    border-color: rgba(255, 214, 92, 0.95);
    box-shadow: 0 0 0 2px rgba(255, 214, 92, 0.55), var(--surface-toolbar-shadow);
  }

  .turn-label {
    color: var(--text-secondary);
    font-size: 13px;
    font-weight: 800;
    letter-spacing: 0.1em;
  }

  .turn-name {
    color: var(--text-primary);
    font-size: 30px;
    font-weight: 950;
    line-height: 1.1;
    white-space: nowrap;
  }

  @keyframes turn-banner-in {
    from { opacity: 0; transform: translate(-50%, -50%) scale(0.9); }
    to { opacity: 1; transform: translate(-50%, -50%) scale(1); }
  }

  @media (prefers-reduced-motion: reduce) {
    .turn-banner { animation: none; }
  }
</style>
