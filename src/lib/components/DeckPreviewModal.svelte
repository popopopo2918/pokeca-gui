<script lang="ts">
  import { resolveDeckTextEntries } from '../cards/cardCatalog';

  type Props = {
    title: string;
    deckText: string;
    onClose: () => void;
  };

  let { title, deckText, onClose }: Props = $props();

  let entries = $derived(resolveDeckTextEntries(deckText));
  let totalCount = $derived(entries.reduce((sum, entry) => sum + entry.count, 0));
</script>

<div class="deck-preview-backdrop" role="presentation" onclick={onClose}>
  <section class="deck-preview" role="dialog" aria-label={title} onclick={(event) => event.stopPropagation()}>
    <header>
      <strong>{title}（{totalCount}枚）</strong>
      <button type="button" onclick={onClose}>✕ 閉じる</button>
    </header>
    {#if entries.length === 0}
      <p class="empty">デッキリストが空です。</p>
    {:else}
      <div class="deck-preview-grid">
        {#each entries as entry}
          <figure class:unresolved={!entry.card}>
            {#if entry.card?.imageUrl}
              <img src={entry.card.imageUrl} alt={entry.card.nameJa} loading="lazy" decoding="async" />
            {:else}
              <div class="fallback">{entry.card?.nameJa ?? entry.label}</div>
            {/if}
            <span class="count">×{entry.count}</span>
            <figcaption>{entry.card?.nameJa ?? `${entry.label}（未解決）`}</figcaption>
          </figure>
        {/each}
      </div>
    {/if}
  </section>
</div>

<style>
  .deck-preview-backdrop {
    position: fixed;
    inset: 0;
    z-index: 40;
    display: grid;
    place-items: center;
    background: rgba(10, 14, 20, 0.6);
    backdrop-filter: blur(3px);
  }

  .deck-preview {
    width: min(1080px, 94vw);
    max-height: 88vh;
    display: grid;
    grid-template-rows: auto minmax(0, 1fr);
    gap: 12px;
    padding: 16px;
    border-radius: var(--radius-lg);
    border: 1px solid var(--surface-glass-border);
    background: var(--surface-glass-bg);
    box-shadow: var(--surface-glass-shadow);
    color: var(--text-primary);
  }

  .deck-preview header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }

  .deck-preview-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(clamp(104px, 9vw, 136px), 1fr));
    gap: 12px;
    overflow: auto;
    padding-right: 4px;
  }

  figure {
    position: relative;
    margin: 0;
    display: grid;
    gap: 4px;
  }

  figure img {
    width: 100%;
    border-radius: 6px;
    display: block;
  }

  .fallback {
    aspect-ratio: 63 / 88;
    display: grid;
    place-items: center;
    padding: 8px;
    border-radius: 6px;
    border: 1px solid var(--surface-inset-border);
    background: var(--surface-inset-bg);
    font-size: 12px;
    text-align: center;
  }

  figure.unresolved .fallback {
    border-color: var(--danger-border);
    color: var(--danger-strong);
  }

  .count {
    position: absolute;
    top: 4px;
    right: 4px;
    padding: 2px 7px;
    border-radius: 999px;
    background: rgba(12, 16, 22, 0.82);
    color: #fff;
    font-size: 12px;
    font-weight: 800;
  }

  figcaption {
    font-size: 11px;
    color: var(--text-secondary);
    text-align: center;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .empty {
    margin: 0;
    color: var(--text-muted);
  }
</style>
