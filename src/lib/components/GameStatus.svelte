<script lang="ts">
  type Props = {
    phaseLabel: string;
    turn: number;
    activePlayerName?: string;
    resultLabel?: string;
    modeLabel?: string;
    gameFinished?: boolean;
    thinking?: boolean;
  };

  let {
    phaseLabel,
    turn,
    activePlayerName = '',
    resultLabel = '',
    modeLabel = '',
    gameFinished = false,
    thinking = false,
  }: Props = $props();
</script>

<div class="game-status">
  <strong>{resultLabel || phaseLabel}</strong>
  {#if modeLabel && !gameFinished}
    <span class="mode">{modeLabel}</span>
  {/if}
  <span>ターン {turn}</span>
  {#if !gameFinished}
    <span>{activePlayerName}</span>
  {/if}
  {#if thinking && !gameFinished}
    <span class="thinking" role="status">AI思考中…</span>
  {/if}
</div>

<style>
  .game-status {
    position: absolute;
    top: 14px;
    right: 14px;
    z-index: 9;
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    pointer-events: auto;
    padding: 5px 9px;
    border-radius: 999px;
    border: 1px solid var(--surface-toolbar-border);
    background: var(--surface-toolbar-bg);
    color: var(--text-secondary);
    box-shadow: var(--surface-toolbar-shadow);
    backdrop-filter: blur(var(--backdrop-blur));
    font-size: 11px;
  }

  .game-status strong {
    color: var(--accent-strong);
  }

  .mode {
    color: var(--accent-strong);
    font-weight: 900;
  }

  .thinking {
    color: var(--text-primary);
    font-weight: 700;
    animation: thinking-pulse 1.2s ease-in-out infinite;
  }

  @keyframes thinking-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.45; }
  }

  @media (prefers-reduced-motion: reduce) {
    .thinking {
      animation: none;
    }
  }
</style>
