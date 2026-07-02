<script lang="ts">
  import CardThumb from './CardThumb.svelte';
  import {
    filterCatalog,
    listSets,
    listTypes,
    EMPTY_FILTERS,
    type CatalogCard,
    type CardFilters,
  } from '../../cards/cardCatalog';

  type Props = {
    cards: CatalogCard[];
    countOf: (id: number) => number;
    onadd: (id: number) => void;
    onremove: (id: number) => void;
    oninspect: (card: CatalogCard) => void;
  };
  let { cards, countOf, onadd, onremove, oninspect }: Props = $props();

  const PAGE = 80;
  let filters = $state<CardFilters>({ ...EMPTY_FILTERS });
  let visible = $state(PAGE);

  let sets = $derived(listSets(cards));
  let types = $derived(listTypes(cards));
  const categories: Array<{ key: CardFilters['category']; label: string }> = [
    { key: 'all', label: 'すべて' },
    { key: 'pokemon', label: 'ポケモン' },
    { key: 'trainer', label: 'トレーナーズ' },
    { key: 'energy', label: 'エネルギー' },
  ];
  const traits: Array<{ key: CardFilters['trait']; label: string }> = [
    { key: 'all', label: '特性なし' },
    { key: 'ex', label: 'ex/MEGA' },
    { key: 'megaEx', label: 'MEGA' },
    { key: 'tera', label: 'テラスタル' },
    { key: 'aceSpec', label: 'ACE SPEC' },
    { key: 'basic', label: 'たね' },
    { key: 'stage1', label: '1進化' },
    { key: 'stage2', label: '2進化' },
  ];

  let filtered = $derived(filterCatalog(cards, filters));
  let shown = $derived(filtered.slice(0, visible));

  // Reset paging whenever the filter result changes.
  $effect(() => {
    void filters.query;
    void filters.category;
    void filters.set;
    void filters.type;
    void filters.trait;
    visible = PAGE;
  });
</script>

<div class="gallery">
  <div class="filters">
    <input
      class="search"
      type="search"
      placeholder="カード名で検索（日本語 / English）"
      bind:value={filters.query}
    />
    <div class="pills">
      {#each categories as cat}
        <button class:active={filters.category === cat.key} onclick={() => (filters.category = cat.key)}>
          {cat.label}
        </button>
      {/each}
    </div>
    <div class="selects">
      <select bind:value={filters.set}>
        <option value="all">全セット</option>
        {#each sets as set}<option value={set}>{set}</option>{/each}
      </select>
      <select bind:value={filters.type}>
        <option value="all">全タイプ</option>
        {#each types as type}<option value={type}>{type}</option>{/each}
      </select>
      <select bind:value={filters.trait}>
        {#each traits as trait}<option value={trait.key}>{trait.label}</option>{/each}
      </select>
    </div>
    <span class="count">{filtered.length} 枚</span>
  </div>

  <div class="grid">
    {#each shown as card (card.id)}
      <CardThumb
        {card}
        count={countOf(card.id)}
        onadd={() => onadd(card.id)}
        onremove={() => onremove(card.id)}
        oninspect={() => oninspect(card)}
      />
    {/each}
  </div>

  {#if shown.length < filtered.length}
    <button class="more" onclick={() => (visible += PAGE)}>
      さらに表示（残り {filtered.length - shown.length} 枚）
    </button>
  {:else if filtered.length === 0}
    <p class="empty">条件に一致するカードがありません。</p>
  {/if}
</div>

<style>
  .gallery { display: flex; flex-direction: column; height: 100%; min-height: 0; }
  .filters {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    padding-bottom: 10px;
    margin-bottom: 8px;
    border-bottom: 1px solid var(--surface-inset-border);
  }
  .search {
    flex: 1 1 240px;
    padding: 8px 12px;
    border: 1px solid var(--input-border);
    border-radius: var(--radius-pill);
    background: var(--input-bg);
    color: var(--input-text);
    font-size: 14px;
  }
  .pills { display: flex; gap: 4px; flex-wrap: wrap; }
  .pills button {
    padding: 6px 12px;
    border: 1px solid var(--button-border);
    border-radius: var(--radius-pill);
    background: var(--button-bg);
    color: var(--button-text);
    font-size: 12px;
    cursor: pointer;
  }
  .pills button.active {
    background: var(--accent-base);
    border-color: var(--accent-base);
    color: var(--text-on-accent);
  }
  .selects { display: flex; gap: 6px; }
  .selects select {
    padding: 7px 8px;
    border: 1px solid var(--input-border);
    border-radius: var(--radius-sm);
    background: var(--input-bg);
    color: var(--input-text);
    font-size: 12px;
    max-width: 130px;
  }
  .count { margin-left: auto; font-size: 12px; color: var(--text-muted); font-weight: 600; }
  .grid {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 12px;
    padding: 4px 4px 12px;
    align-content: start;
  }
  .more {
    margin: 8px auto 0;
    padding: 9px 18px;
    border: 1px solid var(--button-border);
    border-radius: var(--radius-pill);
    background: var(--button-bg);
    color: var(--button-text);
    font-size: 13px;
    cursor: pointer;
  }
  .empty { text-align: center; color: var(--text-muted); padding: 30px; }
</style>
