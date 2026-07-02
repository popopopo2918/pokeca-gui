<script lang="ts">
  import { onMount } from 'svelte';
  import CardGallery from './CardGallery.svelte';
  import DeckPanel from './DeckPanel.svelte';
  import DeckLibrary from './DeckLibrary.svelte';
  import CardDetailModal from './CardDetailModal.svelte';
  import { getCatalog, type CatalogCard } from '../../cards/cardCatalog';
  import { deckBuilderStore } from '../../../state/deckBuilder.svelte';

  type Props = {
    onApply: (playerIndex: 0 | 1, deckText: string) => void;
    onclose: () => void;
  };
  let { onApply, onclose }: Props = $props();

  const cards = getCatalog();
  let tab = $state<'deck' | 'library'>('deck');
  let inspect = $state<CatalogCard | null>(null);
  let toast = $state('');
  let toastTimer: ReturnType<typeof setTimeout> | undefined;

  onMount(() => deckBuilderStore.init());

  function flash(message: string) {
    toast = message;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = ''), 2600);
  }

  function applyTo(playerIndex: 0 | 1) {
    if (!deckBuilderStore.validation.ok) return;
    onApply(playerIndex, deckBuilderStore.toSetupDeckText());
    flash(`デッキを ${playerIndex === 0 ? 'プレイヤー1' : 'プレイヤー2'} に適用しました`);
  }

  function exportCsv() {
    const blob = new Blob([`${deckBuilderStore.toCabtCsv()}\n`], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const name = (deckBuilderStore.activeDeckName || 'deck').replace(/[^\w.-]+/g, '_');
    a.href = url;
    a.download = `${name}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    flash('deck.csv をダウンロードしました');
  }

  function save() {
    deckBuilderStore.saveActive();
    flash('デッキを保存しました');
  }
</script>

<div class="screen">
  <header class="bar">
    <div class="title">
      <button class="back" onclick={onclose} aria-label="戻る">← 対戦へ</button>
      <h1>デッキ編成</h1>
      <span class="hint">{cards.length} 種のカードプール</span>
    </div>
  </header>

  <div class="body">
    <section class="left">
      <CardGallery
        {cards}
        countOf={(id) => deckBuilderStore.countOf(id)}
        onadd={(id) => deckBuilderStore.add(id)}
        onremove={(id) => deckBuilderStore.remove(id)}
        oninspect={(card) => (inspect = card)}
      />
    </section>

    <aside class="right">
      <div class="tabs">
        <button class:active={tab === 'deck'} onclick={() => (tab = 'deck')}>デッキ</button>
        <button class:active={tab === 'library'} onclick={() => (tab = 'library')}>
          ライブラリ{#if deckBuilderStore.library.length}（{deckBuilderStore.library.length}）{/if}
        </button>
      </div>

      <div class="tab-body">
        {#if tab === 'deck'}
          <DeckPanel
            deckName={deckBuilderStore.activeDeckName}
            groups={deckBuilderStore.groups}
            validation={deckBuilderStore.validation}
            onName={(name) => (deckBuilderStore.activeDeckName = name)}
            onadd={(id) => deckBuilderStore.add(id)}
            onremove={(id) => deckBuilderStore.remove(id)}
            oninspect={(card) => (inspect = card)}
            onapply={applyTo}
            onexport={exportCsv}
            onsave={save}
            onclear={() => deckBuilderStore.clear()}
          />
        {:else}
          <DeckLibrary
            library={deckBuilderStore.library}
            activeDeckId={deckBuilderStore.activeDeckId}
            onload={(id) => {
              deckBuilderStore.loadDeck(id);
              tab = 'deck';
              flash('デッキを読み込みました');
            }}
            onduplicate={(id) => deckBuilderStore.duplicateDeck(id)}
            ondelete={(id) => deckBuilderStore.deleteDeck(id)}
            onrename={(id, name) => deckBuilderStore.renameDeck(id, name)}
            onsaveNew={() => {
              deckBuilderStore.saveAs(deckBuilderStore.activeDeckName);
              flash('新規デッキとして保存しました');
            }}
          />
        {/if}
      </div>
    </aside>
  </div>

  {#if inspect}
    <CardDetailModal
      card={inspect}
      count={deckBuilderStore.countOf(inspect.id)}
      onadd={() => inspect && deckBuilderStore.add(inspect.id)}
      onremove={() => inspect && deckBuilderStore.remove(inspect.id)}
      onclose={() => (inspect = null)}
    />
  {/if}

  {#if toast}<div class="toast">{toast}</div>{/if}
</div>

<style>
  .screen {
    position: fixed;
    inset: 0;
    z-index: 40;
    display: flex;
    flex-direction: column;
    background: var(--app-backdrop-bg);
    color: var(--app-text);
  }
  .bar {
    flex: none;
    padding: 14px 20px;
    border-bottom: 1px solid var(--surface-toolbar-border);
    background: var(--surface-toolbar-bg);
    backdrop-filter: blur(var(--backdrop-blur));
  }
  .title { display: flex; align-items: center; gap: 14px; }
  .back {
    padding: 7px 12px;
    border: 1px solid var(--button-border);
    border-radius: var(--radius-pill);
    background: var(--button-bg);
    color: var(--button-text);
    font-size: 13px;
    cursor: pointer;
  }
  h1 { margin: 0; font-size: 20px; }
  .hint { font-size: 12px; color: var(--text-muted); }
  .body {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(320px, 380px);
    gap: 16px;
    padding: 16px 20px;
  }
  .left, .right {
    min-height: 0;
    padding: 14px;
    border: 1px solid var(--surface-glass-border);
    border-radius: var(--radius-lg);
    background: var(--surface-glass-bg);
    box-shadow: var(--surface-glass-shadow);
  }
  .left { display: flex; }
  .right { display: flex; flex-direction: column; }
  .tabs { display: flex; gap: 6px; margin-bottom: 12px; flex: none; }
  .tabs button {
    flex: 1;
    padding: 8px;
    border: 1px solid var(--button-border);
    border-radius: var(--radius-sm);
    background: var(--button-bg);
    color: var(--button-text);
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
  }
  .tabs button.active {
    background: var(--accent-base);
    border-color: var(--accent-base);
    color: var(--text-on-accent);
  }
  .tab-body { flex: 1; min-height: 0; }
  .toast {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 70;
    padding: 10px 18px;
    border-radius: var(--radius-pill);
    background: var(--accent-base);
    color: var(--text-on-accent);
    font-size: 13px;
    font-weight: 600;
    box-shadow: var(--surface-glass-shadow);
  }
  @media (max-width: 900px) {
    .body { grid-template-columns: 1fr; grid-template-rows: 1fr 1fr; }
  }
</style>
