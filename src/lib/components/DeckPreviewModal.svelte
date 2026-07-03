<script lang="ts">
  import { getCatalog, type CatalogCard } from '../cards/cardCatalog';

  type Props = {
    title: string;
    deckText: string;
    onClose: () => void;
  };

  let { title, deckText, onClose }: Props = $props();

  type PreviewEntry = { count: number; card?: CatalogCard; label: string };

  // Resolve pasted deck lines ("3 ヒカリ PFL 87") to catalog cards for image display.
  // Set+collector number wins; otherwise fall back to the (Japanese or English) name.
  function resolveEntries(text: string): PreviewEntry[] {
    const catalog = getCatalog();
    const bySetNumber = new Map<string, CatalogCard>();
    for (const card of catalog) {
      bySetNumber.set(`${card.set} ${card.setNumber}`.toLowerCase(), card);
    }
    const entries: PreviewEntry[] = [];
    for (const rawLine of text.split(/\r?\n/)) {
      const line = rawLine.replace(/\s+#.*$/, '').trim();
      if (!line || /^[^\d:][^:]+:\s*\d+\s*$/.test(line)) {
        continue; // empty or section header (ポケモン: 22 など)
      }
      const match = line.match(/^(\d+)\s+(.+)$/);
      const count = match ? Number(match[1]) : 1;
      const label = (match ? match[2] : line).trim();
      const tokens = label.split(/\s+/);
      const hasNumber = /^\d+[a-z]?$/i.test(tokens.at(-1) ?? '');
      const setCode = hasNumber ? tokens.at(-2) : tokens.at(-1);
      let card: CatalogCard | undefined;
      if (hasNumber && setCode) {
        card = bySetNumber.get(`${setCode} ${tokens.at(-1)}`.toLowerCase());
      }
      if (!card) {
        const bareName = (hasNumber ? tokens.slice(0, -2) : tokens.slice(0, -1)).join(' ') || label;
        card = catalog.find((item) => item.nameJa === bareName || item.name === bareName)
          ?? catalog.find((item) => item.nameJa === label || item.name === label);
      }
      entries.push({ count: Number.isFinite(count) && count > 0 ? count : 1, card, label });
    }
    return entries;
  }

  let entries = $derived(resolveEntries(deckText));
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
