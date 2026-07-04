<script lang="ts">
  import { onMount } from 'svelte';
  import CardGallery from './CardGallery.svelte';
  import DeckPanel from './DeckPanel.svelte';
  import DeckLibrary from './DeckLibrary.svelte';
  import CardDetailModal from './CardDetailModal.svelte';
  import Logo from '../Logo.svelte';
  import { cardPreviewStore } from '../../../state/cardPreview.svelte';
  import { japaneseCardName } from '../../cabt/logFormat';
  import { getCatalog, resolveDeckTextEntries, type CatalogCard } from '../../cards/cardCatalog';
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

  let deckCode = $state('');
  let deckCodeBusy = $state(false);
  let deckCodeWarnings = $state<string[]>([]);

  // 公式サイトのデッキコードを読み込んで、このデッキ編成に展開する。
  // プール外のカードは警告に出して除外（編集・保存してから対戦で使う想定）。
  async function importDeckCode() {
    const code = deckCode.trim();
    if (!code || deckCodeBusy) return;
    deckCodeBusy = true;
    deckCodeWarnings = [];
    try {
      const response = await fetch(`/local-engine/deck-code/${encodeURIComponent(code)}`);
      const body = await response.json() as { ok: boolean; text?: string; warnings?: string[]; error?: string };
      if (!body.ok || !body.text) {
        flash(body.error ?? 'デッキコードを読み込めませんでした');
        return;
      }
      const counts: Record<number, number> = {};
      for (const entry of resolveDeckTextEntries(body.text)) {
        if (entry.card) {
          counts[entry.card.id] = (counts[entry.card.id] ?? 0) + entry.count;
        }
      }
      deckBuilderStore.loadCounts(counts);
      deckBuilderStore.activeDeckId = null;
      deckBuilderStore.activeDeckName = `コード ${code}`;
      deckCodeWarnings = body.warnings ?? [];
      tab = 'deck';
      flash('デッキコードを読み込みました');
    } catch (error) {
      flash(`読み込みに失敗しました: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      deckCodeBusy = false;
    }
  }
</script>

<div class="screen">
  <header class="bar">
    <div class="title">
      <button class="back" onclick={onclose} aria-label="戻る">← 対戦へ</button>
      <Logo size={26} emblemOnly />
      <h1>デッキ編成</h1>
      <span class="hint">{cards.length} 種のカードプール</span>
    </div>
    <div class="code-import">
      <input
        type="text"
        bind:value={deckCode}
        placeholder="公式デッキコード（例: VfVb1k-DwijHb-dFF5fF）"
        aria-label="公式デッキコード"
        spellcheck="false"
        onkeydown={(event) => event.key === 'Enter' && void importDeckCode()}
      />
      <button type="button" disabled={deckCodeBusy || !deckCode.trim()} onclick={() => void importDeckCode()}>
        {deckCodeBusy ? '読込中…' : 'コード読み込み'}
      </button>
    </div>
  </header>

  {#if deckCodeWarnings.length}
    <div class="code-warnings">
      <div class="code-warnings-head">
        <strong>デッキコード読み込みの注意（{deckCodeWarnings.length}件）</strong>
        <button type="button" onclick={() => (deckCodeWarnings = [])}>閉じる</button>
      </div>
      <ul>
        {#each deckCodeWarnings as warning}
          <li>{warning}</li>
        {/each}
      </ul>
    </div>
  {/if}

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

    <aside class="preview-pane" aria-label="カード拡大プレビュー">
      {#if cardPreviewStore.hovered}
        {@const hovered = cardPreviewStore.hovered}
        {#if hovered.imageUrl}
          <img src={hovered.imageUrl} alt={hovered.fullName ?? hovered.name} />
        {:else}
          <div class="preview-fallback">{(hovered.id ? japaneseCardName(hovered.id) : '') || hovered.fullName || hovered.name}</div>
        {/if}
        <span class="preview-name">{(hovered.id ? japaneseCardName(hovered.id) : '') || hovered.fullName || hovered.name}</span>
      {:else}
        <div class="preview-placeholder">カードにマウスを乗せると<br />ここに拡大表示されます</div>
      {/if}
    </aside>

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
  .preview-pane {
    min-height: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    padding: 18px 14px;
    border: 1px solid var(--surface-glass-border);
    border-radius: var(--radius-lg);
    background:
      radial-gradient(70% 46% at 50% 42%, rgba(77, 141, 255, 0.14), transparent 70%),
      var(--surface-glass-bg);
    box-shadow: var(--surface-glass-shadow);
  }

  .preview-pane img {
    width: 100%;
    max-height: calc(100% - 46px);
    object-fit: contain;
    border-radius: var(--radius-md);
    filter: drop-shadow(0 18px 32px rgba(0, 0, 0, 0.55));
  }

  .preview-name {
    font-size: 13px;
    font-weight: 700;
    color: var(--text-primary);
    text-align: center;
    padding: 6px 14px;
    border-radius: 999px;
    border: 1px solid var(--surface-inset-border);
    background: var(--surface-inset-bg);
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .preview-fallback {
    width: 100%;
    aspect-ratio: 63 / 88;
    display: grid;
    place-items: center;
    padding: 12px;
    border: 1px solid var(--surface-inset-border);
    border-radius: var(--radius-md);
    background: var(--surface-inset-bg);
    text-align: center;
  }

  .preview-placeholder {
    color: var(--text-muted);
    font-size: 12.5px;
    text-align: center;
    line-height: 1.8;
  }

  @media (max-width: 1100px) {
    .body {
      grid-template-columns: minmax(0, 1fr) minmax(320px, 380px);
    }
    .preview-pane {
      display: none;
    }
  }

  .bar {
    flex: none;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
    padding: 14px 20px;
    border-bottom: 1px solid var(--surface-toolbar-border);
    background: var(--surface-toolbar-bg);
    backdrop-filter: blur(var(--backdrop-blur));
  }
  .title { display: flex; align-items: center; gap: 14px; }
  .title h1 { font-size: 19px; letter-spacing: 0.06em; }
  .title .hint { color: var(--text-muted); font-size: 12px; }

  .code-import {
    display: grid;
    grid-template-columns: minmax(220px, 340px) auto;
    gap: 8px;
  }

  .code-import input {
    min-height: 36px;
    border-radius: 8px;
    border: 1px solid var(--input-border);
    background: var(--input-bg);
    color: var(--input-text);
    padding: 0 12px;
    font-size: 12px;
  }

  .code-import button {
    border: 1px solid var(--button-border);
    border-radius: 8px;
    background: var(--button-bg);
    color: var(--button-text);
    font-size: 12px;
    font-weight: 700;
    padding: 0 12px;
  }

  .code-warnings {
    margin: 10px 20px 0;
    padding: 10px 12px;
    border: 1px solid var(--warning-base, #b8860b);
    border-radius: 8px;
    background: var(--surface-inset-bg);
    color: var(--text-secondary);
    font-size: 12px;
  }

  .code-warnings-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    color: var(--text-primary);
  }

  .code-warnings ul {
    margin: 6px 0 0;
    padding-left: 18px;
    max-height: 120px;
    overflow: auto;
  }
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
    grid-template-columns: minmax(0, 1fr) clamp(220px, 19vw, 320px) minmax(320px, 380px);
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
  .tabs {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 4px;
    margin-bottom: 12px;
    flex: none;
    padding: 4px;
    border-radius: 10px;
    border: 1px solid var(--surface-inset-border);
    background: var(--surface-inset-bg);
  }
  .tabs button {
    border: 0;
    border-radius: 7px;
    padding: 8px;
    background: transparent;
    color: var(--text-secondary);
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
    transition: background 0.12s ease, color 0.12s ease;
  }
  .tabs button.active {
    background: var(--accent-base);
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
