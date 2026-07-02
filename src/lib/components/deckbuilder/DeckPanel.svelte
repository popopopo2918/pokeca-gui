<script lang="ts">
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
</script>

<div class="panel">
  <div class="head">
    <input
      class="deck-name"
      value={deckName}
      placeholder="デッキ名"
      oninput={(e) => onName((e.currentTarget as HTMLInputElement).value)}
    />
    <span class="total" class:ok={validation.ok} class:bad={!validation.ok}>
      {validation.total}/{DECK_SIZE}
    </span>
  </div>

  <div class="summary">
    <span>ポケモン {validation.byCategory.pokemon}</span>
    <span>トレーナーズ {validation.byCategory.trainer}</span>
    <span>エネルギー {validation.byCategory.energy}</span>
  </div>

  {#if validation.errors.length}
    <ul class="errors">
      {#each validation.errors as err}<li>{err}</li>{/each}
    </ul>
  {:else}
    <p class="legal">✓ 構築ルール上は有効な60枚デッキです</p>
  {/if}

  <div class="list">
    {#each sections as section}
      {#if groups[section.key].length}
        <h4>{section.label} <span>{validation.byCategory[section.key]}</span></h4>
        {#each groups[section.key] as { card, count } (card.id)}
          <div class="row">
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
      <p class="empty">左のカードをクリックしてデッキに追加してください。</p>
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
  .panel {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  .head {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 8px;
  }
  .deck-name {
    flex: 1;
    min-width: 0;
    padding: 8px 10px;
    border: 1px solid var(--input-border);
    border-radius: var(--radius-sm);
    background: var(--input-bg);
    color: var(--input-text);
    font-size: 14px;
    font-weight: 600;
  }
  .total {
    font-size: 18px;
    font-weight: 800;
    padding: 4px 10px;
    border-radius: var(--radius-sm);
  }
  .total.ok { color: var(--accent-strong); background: var(--accent-tint); }
  .total.bad { color: var(--warning-text); background: var(--warning-soft); }
  .summary {
    display: flex;
    gap: 12px;
    font-size: 12px;
    color: var(--text-muted);
    margin-bottom: 8px;
  }
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
    margin: 0 0 8px;
    font-size: 12px;
    color: var(--accent-strong);
    font-weight: 600;
  }
  .list {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding-right: 4px;
  }
  h4 {
    display: flex;
    justify-content: space-between;
    margin: 10px 0 4px;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
    border-bottom: 1px solid var(--surface-inset-border);
    padding-bottom: 3px;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 3px 0;
  }
  .thumb {
    flex: none;
    width: 30px;
    height: 42px;
    padding: 0;
    border: 1px solid var(--surface-glass-border);
    border-radius: 3px;
    overflow: hidden;
    background: var(--surface-inset-bg);
    cursor: pointer;
  }
  .thumb img { width: 100%; height: 100%; object-fit: cover; }
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
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
  }
  .name .set { font-size: 11px; color: var(--text-muted); }
  .qty { display: flex; align-items: center; gap: 6px; }
  .qty button {
    width: 22px;
    height: 22px;
    border: 1px solid var(--button-border);
    border-radius: var(--radius-sm);
    background: var(--button-bg);
    color: var(--button-text);
    cursor: pointer;
    font-size: 13px;
    line-height: 1;
  }
  .qty button:disabled { opacity: var(--disabled-opacity); cursor: not-allowed; }
  .qty span { min-width: 16px; text-align: center; font-weight: 700; font-size: 13px; }
  .empty { color: var(--text-muted); font-size: 13px; padding: 20px 0; text-align: center; }
  .actions {
    margin-top: 8px;
    padding-top: 10px;
    border-top: 1px solid var(--surface-inset-border);
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .apply { display: flex; gap: 8px; }
  .apply .primary {
    flex: 1;
    padding: 10px;
    border: 1px solid var(--button-primary-border);
    border-radius: var(--radius-sm);
    background: var(--button-primary-bg);
    color: var(--button-primary-text);
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
  }
  .apply .primary.ghost {
    flex: 0 0 88px;
    background: var(--button-ghost-bg);
    border-color: var(--button-ghost-border);
    color: var(--button-ghost-text);
  }
  .apply .primary:disabled { opacity: var(--disabled-opacity); cursor: not-allowed; }
  .util { display: flex; gap: 8px; }
  .util button {
    flex: 1;
    padding: 8px;
    border: 1px solid var(--button-border);
    border-radius: var(--radius-sm);
    background: var(--button-bg);
    color: var(--button-text);
    font-size: 12px;
    cursor: pointer;
  }
  .util button:disabled { opacity: var(--disabled-opacity); cursor: not-allowed; }
  .util .danger { color: var(--danger-text); border-color: var(--danger-border); }
</style>
