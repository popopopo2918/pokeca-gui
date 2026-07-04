<script lang="ts">
  import { cardPreviewStore } from '../../../state/cardPreview.svelte';
  import type { CatalogCard, DeckValidation } from '../../cards/cardCatalog';
  import { DECK_SIZE } from '../../cards/cardCatalog';
  import type { DeckGroups } from '../../../state/deckBuilder.svelte';

  type Props = {
    deckName: string;
    groups: DeckGroups;
    validation: DeckValidation;
    onName: (name: string) => void;
    onadd: (id: number) => void;
    onremove: (id: number) => void;
    oninspect: (card: CatalogCard) => void;
    onapply: (playerIndex: 0 | 1) => void;
    onexport: () => void;
    onsave: () => void;
    onclear: () => void;
  };
  // 対戦中と同じマウスオーバー拡大（CardZoom は DeckBuilderScreen 側で表示）
  const hoverOwners = new Map<number, object>();
  function ownerFor(id: number): object {
    let owner = hoverOwners.get(id);
    if (!owner) {
      owner = {};
      hoverOwners.set(id, owner);
    }
    return owner;
  }
  function hoverCard(card: CatalogCard) {
    cardPreviewStore.set({
      id: card.id,
      name: card.nameJa,
      fullName: card.nameJa,
      set: card.set,
      setNumber: card.setNumber,
      imageUrl: card.imageUrl,
    }, ownerFor(card.id));
  }
  function unhoverCard(id: number) {
    cardPreviewStore.clear(ownerFor(id));
  }
  $effect(() => () => {
    for (const owner of hoverOwners.values()) {
      cardPreviewStore.clear(owner);
    }
  });

  let {
    deckName,
    groups,
    validation,
    onName,
    onadd,
    onremove,
    oninspect,
    onapply,
    onexport,
    onsave,
    onclear,
  }: Props = $props();

  const sections: Array<{ key: 'pokemon' | 'trainer' | 'energy'; label: string }> = [
    { key: 'pokemon', label: 'ポケモン' },
    { key: 'trainer', label: 'トレーナーズ' },
    { key: 'energy', label: 'エネルギー' },
  ];

  function pct(count: number): string {
    return `${Math.min(100, (count / DECK_SIZE) * 100)}%`;
  }
</script>

<div class="panel">
  <div class="head">
    <input
      class="deck-name"
      value={deckName}
      placeholder="デッキ名を入力"
      oninput={(e) => onName((e.currentTarget as HTMLInputElement).value)}
    />
    <span class="total" class:ok={validation.ok} class:bad={!validation.ok}>
      {validation.total}<small>/{DECK_SIZE}</small>
    </span>
  </div>

  <!-- 60枚に向かって埋まる構成バー（表示のみ） -->
  <div class="comp">
    <div class="comp-bar" role="presentation">
      <i class="seg pk" style={`width:${pct(validation.byCategory.pokemon)}`}></i>
      <i class="seg tr" style={`width:${pct(validation.byCategory.trainer)}`}></i>
      <i class="seg en" style={`width:${pct(validation.byCategory.energy)}`}></i>
    </div>
    <div class="comp-legend">
      <span><i class="dot pk"></i>ポケモン <b>{validation.byCategory.pokemon}</b></span>
      <span><i class="dot tr"></i>トレーナーズ <b>{validation.byCategory.trainer}</b></span>
      <span><i class="dot en"></i>エネルギー <b>{validation.byCategory.energy}</b></span>
    </div>
  </div>

  {#if validation.errors.length}
    <ul class="errors">
      {#each validation.errors as err}<li>{err}</li>{/each}
    </ul>
  {:else}
    <p class="legal"><i>✓</i>構築ルール上は有効な60枚デッキです</p>
  {/if}

  <div class="list">
    {#each sections as section}
      {#if groups[section.key].length}
        <h4 class={section.key}>
          <span class="sec-label">{section.label}</span>
          <span class="sec-count">{validation.byCategory[section.key]}</span>
        </h4>
        {#each groups[section.key] as { card, count } (card.id)}
          <div
            class="row"
            role="presentation"
            onmouseenter={() => hoverCard(card)}
            onmouseleave={() => unhoverCard(card.id)}
          >
            <button class="thumb" onclick={() => oninspect(card)} title="詳細">
              <img src={card.imageUrl ?? '/assets/cardback.png'} alt={card.nameJa} loading="lazy" />
            </button>
            <button class="name" onclick={() => oninspect(card)}>
              <span class="ja">{card.nameJa}</span>
              <span class="set">{card.set} {card.setNumber}</span>
            </button>
            <div class="qty">
              <button onclick={() => onremove(card.id)} aria-label="減らす">−</button>
              <span>{count}</span>
              <button onclick={() => onadd(card.id)} disabled={count >= card.copyLimit} aria-label="増やす">＋</button>
            </div>
          </div>
        {/each}
      {/if}
    {/each}
    {#if validation.total === 0}
      <p class="empty">左のカードをクリックして<br />デッキに追加してください。</p>
    {/if}
  </div>

  <div class="actions">
    <div class="apply">
      <button class="primary" disabled={!validation.ok} onclick={() => onapply(0)}>このデッキをP1で使う</button>
      <button class="primary ghost" disabled={!validation.ok} onclick={() => onapply(1)}>P2で使う</button>
    </div>
    <div class="util">
      <button onclick={onsave}>保存</button>
      <button onclick={onexport} disabled={validation.total === 0}>deck.csv</button>
      <button class="danger" onclick={onclear} disabled={validation.total === 0}>クリア</button>
    </div>
  </div>
</div>

<style>
  /* カテゴリ色（このパネル内のみ）: 青=ポケモン / 緑=トレーナーズ / 金=エネルギー */
  .panel {
    --cat-pk: var(--accent-base, #4d8dff);
    --cat-tr: #3fbf8f;
    --cat-en: #d9a441;
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }

  /* ---- デッキ名 + 合計 ---- */
  .head {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 10px;
  }
  .deck-name {
    flex: 1;
    min-width: 0;
    padding: 6px 2px;
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    background: transparent;
    color: var(--text-primary);
    font-size: 17px;
    font-weight: 800;
    letter-spacing: 0.02em;
    transition: border-color 0.15s ease;
  }
  .deck-name::placeholder {
    color: var(--text-muted);
    font-weight: 600;
  }
  .deck-name:hover { border-bottom-color: var(--surface-inset-border); }
  .deck-name:focus {
    outline: none;
    border-bottom-color: var(--accent-base);
  }
  .total {
    flex: none;
    font-size: 20px;
    font-weight: 900;
    font-variant-numeric: tabular-nums;
    line-height: 1;
    padding: 7px 12px;
    border-radius: var(--radius-sm);
    letter-spacing: 0.01em;
  }
  .total small {
    font-size: 12px;
    font-weight: 700;
    opacity: 0.72;
    margin-left: 1px;
  }
  .total.ok { color: var(--accent-strong); background: var(--accent-tint); }
  .total.bad { color: var(--warning-text); background: var(--warning-soft); }

  /* ---- 構成バー ---- */
  .comp {
    display: grid;
    gap: 7px;
    margin-bottom: 10px;
  }
  .comp-bar {
    display: flex;
    height: 6px;
    border-radius: 999px;
    overflow: hidden;
    background: var(--surface-inset-bg);
    border: 1px solid var(--surface-inset-border);
  }
  .comp-bar .seg {
    display: block;
    height: 100%;
    transition: width 0.25s ease;
  }
  .seg.pk { background: var(--cat-pk); }
  .seg.tr { background: var(--cat-tr); }
  .seg.en { background: var(--cat-en); }
  .comp-legend {
    display: flex;
    gap: 14px;
    flex-wrap: wrap;
    font-size: 11.5px;
    color: var(--text-secondary);
  }
  .comp-legend b {
    color: var(--text-primary);
    font-weight: 800;
    font-variant-numeric: tabular-nums;
  }
  .dot {
    display: inline-block;
    width: 7px;
    height: 7px;
    border-radius: 999px;
    margin-right: 5px;
    vertical-align: 1px;
  }
  .dot.pk { background: var(--cat-pk); }
  .dot.tr { background: var(--cat-tr); }
  .dot.en { background: var(--cat-en); }

  /* ---- バリデーション ---- */
  .errors {
    margin: 0 0 8px;
    padding: 8px 10px 8px 26px;
    border-radius: var(--radius-sm);
    background: var(--danger-bg);
    border: 1px solid var(--danger-border);
    color: var(--danger-text);
    font-size: 12px;
    max-height: 96px;
    overflow-y: auto;
  }
  .legal {
    display: flex;
    align-items: center;
    gap: 7px;
    margin: 0 0 8px;
    font-size: 12px;
    color: var(--accent-strong);
    font-weight: 600;
  }
  .legal i {
    flex: none;
    display: grid;
    place-items: center;
    width: 16px;
    height: 16px;
    border-radius: 999px;
    background: var(--accent-tint);
    font-style: normal;
    font-size: 10px;
    font-weight: 900;
  }

  /* ---- カードリスト ---- */
  .list {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding-right: 4px;
  }
  h4 {
    position: sticky;
    top: 0;
    z-index: 1;
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 8px 0 4px;
    padding: 6px 0 6px;
    font-size: 11.5px;
    letter-spacing: 0.1em;
    color: var(--text-secondary);
    background: var(--app-backdrop-bg, #0b0e14);
    box-shadow: 0 6px 8px -6px rgba(0, 0, 0, 0.45);
  }
  h4::before {
    content: '';
    flex: none;
    width: 3px;
    height: 12px;
    border-radius: 2px;
  }
  h4.pokemon::before { background: var(--cat-pk); }
  h4.trainer::before { background: var(--cat-tr); }
  h4.energy::before { background: var(--cat-en); }
  .sec-label { flex: 1; }
  .sec-count {
    font-size: 11px;
    font-weight: 800;
    font-variant-numeric: tabular-nums;
    color: var(--text-primary);
    background: var(--surface-inset-bg);
    border: 1px solid var(--surface-inset-border);
    border-radius: 999px;
    padding: 1px 9px;
  }

  .row {
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 4px 6px;
    border-radius: 9px;
    transition: background 0.12s ease;
  }
  .row:hover { background: var(--surface-inset-bg); }
  .thumb {
    flex: none;
    width: 32px;
    height: 45px;
    padding: 0;
    border: 1px solid var(--surface-glass-border);
    border-radius: 4px;
    overflow: hidden;
    background: var(--surface-inset-bg);
    cursor: pointer;
    transition: transform 0.12s ease, border-color 0.12s ease;
  }
  .row:hover .thumb {
    transform: scale(1.05);
    border-color: var(--accent-base);
  }
  .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .name {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 1px;
    padding: 0;
    border: none;
    background: none;
    cursor: pointer;
    text-align: left;
  }
  .name .ja {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
  }
  .name .set { font-size: 10.5px; color: var(--text-muted); letter-spacing: 0.03em; }

  /* 一体型ステッパー（− 枚数 ＋ を1つのピルに） */
  .qty {
    flex: none;
    display: flex;
    align-items: center;
    border: 1px solid var(--surface-inset-border);
    border-radius: 999px;
    background: var(--surface-inset-bg);
    overflow: hidden;
  }
  .qty button {
    width: 26px;
    height: 26px;
    border: none;
    background: transparent;
    color: var(--text-secondary);
    cursor: pointer;
    font-size: 14px;
    font-weight: 800;
    line-height: 1;
    display: grid;
    place-items: center;
    transition: background 0.12s ease, color 0.12s ease;
  }
  .qty button:hover:not(:disabled) {
    background: var(--accent-tint);
    color: var(--accent-strong);
  }
  .qty button:disabled { opacity: var(--disabled-opacity); cursor: not-allowed; }
  .qty span {
    min-width: 20px;
    text-align: center;
    font-weight: 800;
    font-size: 13px;
    font-variant-numeric: tabular-nums;
    color: var(--text-primary);
  }

  .empty {
    color: var(--text-muted);
    font-size: 13px;
    line-height: 1.9;
    padding: 36px 0;
    text-align: center;
  }

  /* ---- アクション（主従を分離） ---- */
  .actions {
    margin-top: 10px;
    padding-top: 12px;
    border-top: 1px solid var(--surface-inset-border);
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .apply { display: flex; gap: 8px; }
  .apply .primary {
    flex: 1;
    padding: 11px;
    border: 1px solid var(--button-primary-border);
    border-radius: 10px;
    background: var(--button-primary-bg);
    color: var(--button-primary-text);
    font-size: 13px;
    font-weight: 800;
    letter-spacing: 0.04em;
    cursor: pointer;
    box-shadow: 0 6px 18px color-mix(in srgb, var(--accent-base) 22%, transparent);
    transition: filter 0.12s ease, transform 0.1s ease;
  }
  .apply .primary:not(:disabled):hover { filter: brightness(1.08); }
  .apply .primary:not(:disabled):active { transform: translateY(1px); }
  .apply .primary.ghost {
    flex: 0 0 96px;
    background: var(--button-ghost-bg);
    border-color: var(--button-ghost-border);
    color: var(--button-ghost-text);
    box-shadow: none;
  }
  .apply .primary:disabled { opacity: var(--disabled-opacity); cursor: not-allowed; box-shadow: none; }
  .util { display: flex; gap: 8px; }
  .util button {
    flex: 1;
    padding: 8px;
    border: 1px solid transparent;
    border-radius: 8px;
    background: transparent;
    color: var(--text-secondary);
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
    transition: background 0.12s ease, color 0.12s ease, border-color 0.12s ease;
  }
  .util button:hover:not(:disabled) {
    background: var(--surface-inset-bg);
    border-color: var(--surface-inset-border);
    color: var(--text-primary);
  }
  .util button:disabled { opacity: var(--disabled-opacity); cursor: not-allowed; }
  .util .danger:hover:not(:disabled) {
    color: var(--danger-text);
    border-color: var(--danger-border);
    background: var(--danger-bg);
  }
</style>
