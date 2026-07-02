<script lang="ts">
  import type { SavedDeck } from '../../cards/deckStorage';

  type Props = {
    library: SavedDeck[];
    activeDeckId: string | null;
    onload: (id: string) => void;
    onduplicate: (id: string) => void;
    ondelete: (id: string) => void;
    onrename: (id: string, name: string) => void;
    onsaveNew: () => void;
  };
  let { library, activeDeckId, onload, onduplicate, ondelete, onrename, onsaveNew }: Props = $props();

  function total(deck: SavedDeck): number {
    return Object.values(deck.counts).reduce((sum, n) => sum + n, 0);
  }
  function when(ts: number): string {
    try {
      return new Date(ts).toLocaleString('ja-JP', { dateStyle: 'short', timeStyle: 'short' });
    } catch {
      return '';
    }
  }
</script>

<div class="library">
  <button class="save-new" onclick={onsaveNew}>＋ 現在のデッキを新規保存</button>

  {#if library.length === 0}
    <p class="empty">保存済みデッキはありません。デッキを組んで「保存」すると、ここに一覧表示されます。</p>
  {:else}
    <ul>
      {#each library as deck (deck.id)}
        <li class:active={deck.id === activeDeckId}>
          <div class="top">
            <input
              class="rename"
              value={deck.name}
              onchange={(e) => onrename(deck.id, (e.currentTarget as HTMLInputElement).value)}
            />
            <span class="size" class:full={total(deck) === 60}>{total(deck)}/60</span>
          </div>
          <p class="meta">更新: {when(deck.updatedAt)}</p>
          <div class="row-actions">
            <button class="primary" onclick={() => onload(deck.id)}>読込</button>
            <button onclick={() => onduplicate(deck.id)}>複製</button>
            <button class="danger" onclick={() => ondelete(deck.id)}>削除</button>
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .library { display: flex; flex-direction: column; gap: 10px; height: 100%; min-height: 0; }
  .save-new {
    padding: 9px;
    border: 1px dashed var(--accent-soft);
    border-radius: var(--radius-sm);
    background: var(--accent-tint);
    color: var(--accent-strong);
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
  }
  .empty { color: var(--text-muted); font-size: 13px; line-height: 1.6; }
  ul { list-style: none; margin: 0; padding: 0; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
  li {
    padding: 10px;
    border: 1px solid var(--surface-glass-border);
    border-radius: var(--radius-md);
    background: var(--surface-inset-bg);
  }
  li.active { border-color: var(--accent-base); box-shadow: var(--accent-glow-soft); }
  .top { display: flex; align-items: center; gap: 8px; }
  .rename {
    flex: 1;
    min-width: 0;
    padding: 5px 8px;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-primary);
    font-size: 14px;
    font-weight: 600;
  }
  .rename:focus { background: var(--input-bg); border-color: var(--input-border); outline: none; }
  .size { font-size: 12px; font-weight: 700; color: var(--warning-text); }
  .size.full { color: var(--accent-strong); }
  .meta { margin: 4px 0 8px; font-size: 11px; color: var(--text-muted); }
  .row-actions { display: flex; gap: 6px; }
  .row-actions button {
    flex: 1;
    padding: 6px;
    border: 1px solid var(--button-border);
    border-radius: var(--radius-sm);
    background: var(--button-bg);
    color: var(--button-text);
    font-size: 12px;
    cursor: pointer;
  }
  .row-actions .primary { background: var(--button-primary-bg); border-color: var(--button-primary-border); color: var(--button-primary-text); }
  .row-actions .danger { color: var(--danger-text); border-color: var(--danger-border); }
</style>
