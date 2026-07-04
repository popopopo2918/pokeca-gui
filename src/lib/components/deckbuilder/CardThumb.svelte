<script lang="ts">
  import { cardPreviewStore } from '../../../state/cardPreview.svelte';
  import type { CatalogCard } from '../../cards/cardCatalog';

  type Props = {
    card: CatalogCard;
    count?: number;
    onadd?: () => void;
    onremove?: () => void;
    oninspect?: () => void;
  };
  let { card, count = 0, onadd, onremove, oninspect }: Props = $props();

  let failed = $state(false);
  let src = $derived(failed || !card.imageUrl ? '/assets/cardback.png' : card.imageUrl);
  let atLimit = $derived(count >= card.copyLimit);

  // 対戦中と同じマウスオーバー拡大（CardZoom は DeckBuilderScreen 側で表示）
  const previewOwner = {};
  $effect(() => () => cardPreviewStore.clear(previewOwner));

  function previewEnter() {
    cardPreviewStore.set({
      id: card.id,
      name: card.nameJa,
      fullName: card.nameJa,
      set: card.set,
      setNumber: card.setNumber,
      imageUrl: card.imageUrl,
    }, previewOwner);
  }
</script>

<div
  class="thumb"
  class:in-deck={count > 0}
  role="presentation"
  onmouseenter={previewEnter}
  onmouseleave={() => cardPreviewStore.clear(previewOwner)}
>
  <button class="art" onclick={onadd} disabled={atLimit} title={`${card.nameJa} を追加`}>
    <img {src} alt={card.nameJa} loading="lazy" decoding="async" onerror={() => (failed = true)} />
    {#if count > 0}<span class="count">{count}</span>{/if}
    {#if card.megaEx}<span class="tag mega">MEGA</span>
    {:else if card.ex}<span class="tag ex">ex</span>
    {:else if card.aceSpec}<span class="tag ace">ACE</span>{/if}
  </button>

  <div class="meta">
    <span class="name" title={card.name}>{card.nameJa}</span>
    <span class="sub">
      {#if card.typeIcon}<img class="ti" src={card.typeIcon} alt={card.typeLabel ?? ''} />{/if}
      <span class="set">{card.set} {card.setNumber}</span>
    </span>
  </div>

  <div class="controls">
    <button class="mini" onclick={onremove} disabled={count <= 0} aria-label="1枚減らす">−</button>
    <span class="c">{count}</span>
    <button class="mini" onclick={onadd} disabled={atLimit} aria-label="1枚増やす">＋</button>
    <button class="mini info" onclick={oninspect} aria-label="詳細">i</button>
  </div>
</div>

<style>
  .thumb {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .art {
    position: relative;
    display: block;
    padding: 0;
    border: 1px solid var(--surface-glass-border);
    border-radius: var(--radius-md);
    background: var(--surface-inset-bg);
    cursor: pointer;
    overflow: hidden;
    aspect-ratio: 367 / 512;
    transition: transform var(--transition-fast), box-shadow var(--transition-fast);
  }
  .art:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: var(--glow-hover-shadow);
  }
  .art:disabled {
    cursor: not-allowed;
  }
  .in-deck .art {
    border-color: var(--accent-base);
    box-shadow: var(--accent-glow-soft);
  }
  .art img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  .count {
    position: absolute;
    top: 5px;
    right: 5px;
    min-width: 22px;
    height: 22px;
    padding: 0 5px;
    border-radius: var(--radius-pill);
    background: var(--accent-base);
    color: var(--text-on-accent);
    font-size: 13px;
    font-weight: 700;
    display: grid;
    place-items: center;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
  }
  .tag {
    position: absolute;
    top: 5px;
    left: 5px;
    padding: 1px 6px;
    border-radius: var(--radius-pill);
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.04em;
    color: #fff;
    text-transform: uppercase;
  }
  .tag.mega { background: #7b3fb0; }
  .tag.ex { background: #c1462f; }
  .tag.ace { background: #b8860b; }
  .meta {
    display: flex;
    flex-direction: column;
    gap: 1px;
    min-width: 0;
  }
  .name {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .sub {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    color: var(--text-muted);
  }
  .ti { width: 13px; height: 13px; }
  .controls {
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .mini {
    width: 24px;
    height: 24px;
    border: 1px solid var(--button-border);
    border-radius: var(--radius-sm);
    background: var(--button-bg);
    color: var(--button-text);
    font-size: 14px;
    line-height: 1;
    cursor: pointer;
    display: grid;
    place-items: center;
  }
  .mini:hover:not(:disabled) { border-color: var(--accent-base); }
  .mini:disabled { opacity: var(--disabled-opacity); cursor: not-allowed; }
  .mini.info { margin-left: auto; font-style: italic; font-weight: 700; }
  .c {
    min-width: 18px;
    text-align: center;
    font-size: 13px;
    font-weight: 700;
    color: var(--text-secondary);
  }
</style>
