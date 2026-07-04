<script lang="ts">
  import DeckPreviewModal from './DeckPreviewModal.svelte';
  import { TOURNAMENT_DECKS } from '../game/presetDecks';
  import { resolveDeckTextEntries } from '../cards/cardCatalog';
  import type { AgentOption, GameLogEntry } from '../home/catalog';
  import type { PlayerControl } from '../game/httpClient';

  type HomeMode = 'play' | 'logs';
  type SavedDeckOption = { id: string; name: string };

  type Props = {
    homeMode: HomeMode;
    deck1Text: string;
    deck2Text: string;
    player1Control: PlayerControl;
    player2Control: PlayerControl;
    player1AgentId: string;
    player2AgentId: string;
    player1DeckSource: string;
    player2DeckSource: string;
    agents?: AgentOption[];
    savedDecks?: SavedDeckOption[];
    gameLogs?: GameLogEntry[];
    player1DeckLocked?: boolean;
    player2DeckLocked?: boolean;
    busy?: boolean;
    catalogBusy?: boolean;
    error?: string;
    catalogError?: string;
    setHomeMode: (mode: HomeMode) => void;
    startGame: () => void;
    onDeckSourceChange: (playerIndex: 0 | 1, source: string) => void;
    createOnlineRoom: () => void;
    joinOnlineRoom: (code: string) => void;
    onlineBusy?: boolean;
    loadGameLog: (log: GameLogEntry) => void;
    refreshCatalog: () => void;
  };

  let {
    homeMode,
    deck1Text = $bindable(),
    deck2Text = $bindable(),
    player1Control = $bindable(),
    player2Control = $bindable(),
    player1AgentId = $bindable(),
    player2AgentId = $bindable(),
    player1DeckSource = $bindable(),
    player2DeckSource = $bindable(),
    agents = [],
    savedDecks = [],
    gameLogs = [],
    player1DeckLocked = false,
    player2DeckLocked = false,
    busy = false,
    catalogBusy = false,
    error = '',
    catalogError = '',
    setHomeMode,
    startGame,
    onDeckSourceChange,
    createOnlineRoom,
    joinOnlineRoom,
    onlineBusy = false,
    loadGameLog,
    refreshCatalog,
  }: Props = $props();

  let onlineJoinCode = $state('');
  // ルームはサーバー内にしか存在しないため、ローカル版と共有URL版では別世界になる。
  const onLocalServer = typeof location !== 'undefined' && (location.hostname === '127.0.0.1' || location.hostname === 'localhost');

  let deckOptions = $derived(agents.filter((agent) => !!agent.deckUrl));
  let previewTarget = $state<0 | 1 | null>(null);
  let startDisabled = $derived(
    busy
      || (player1Control === 'agent' && !player1AgentId)
      || (player2Control === 'agent' && !player2AgentId),
  );

  // 表示専用のデッキ要約（枚数・内訳・先頭カードの画像）。挙動には影響しない。
  type DeckSummary = { total: number; pokemon: number; trainer: number; energy: number; art: string[] };
  function summarize(text: string): DeckSummary {
    const entries = resolveDeckTextEntries(text);
    const summary: DeckSummary = { total: 0, pokemon: 0, trainer: 0, energy: 0, art: [] };
    for (const entry of entries) {
      summary.total += entry.count;
      const category = entry.card?.category;
      if (category === 'pokemon') summary.pokemon += entry.count;
      else if (category === 'trainer') summary.trainer += entry.count;
      else if (category === 'energy') summary.energy += entry.count;
      if (category === 'pokemon' && entry.card?.imageUrl && summary.art.length < 6) {
        summary.art.push(entry.card.imageUrl);
      }
    }
    return summary;
  }
  let summary1 = $derived(summarize(deck1Text));
  let summary2 = $derived(summarize(deck2Text));

  function logPlayerLabel(log: GameLogEntry): string {
    return log.players?.length ? log.players.join(' vs ') : 'AI vs AI';
  }

  function setPlayerControl(playerIndex: 0 | 1, control: PlayerControl) {
    if (playerIndex === 0) {
      player1Control = control;
    } else {
      player2Control = control;
    }
  }
</script>

<section class="import-screen">
  <div class="page">
    <div class="page-head">
      <div>
        <p class="eyebrow">MATCH SETUP</p>
        <h2>対戦をはじめる</h2>
      </div>
      <div class="home-tabs" role="tablist" aria-label="ホームモード">
        <button class:active={homeMode === 'play'} type="button" onclick={() => setHomeMode('play')}>対戦</button>
        <button class:active={homeMode === 'logs'} type="button" onclick={() => setHomeMode('logs')}>対戦ログ</button>
      </div>
    </div>

    {#if homeMode === 'play'}
      <div class="setup-grid">
        <!-- ============ プレイヤー1 ============ -->
        <article class="player-card">
          <header>
            <span class="player-tag p1">PLAYER 1</span>
            <span class="control-tabs" role="tablist" aria-label="プレイヤー1の操作">
              <button type="button" role="tab" aria-selected={player1Control === 'self'}
                class:active={player1Control === 'self'} disabled={busy}
                onclick={() => setPlayerControl(0, 'self')}>自分</button>
              <button type="button" role="tab" aria-selected={player1Control === 'agent'}
                class:active={player1Control === 'agent'} disabled={busy}
                onclick={() => setPlayerControl(0, 'agent')}>AI</button>
            </span>
          </header>

          {#if player1Control === 'agent'}
            <div class="field">
              <label for="p1-agent">AI</label>
              <select id="p1-agent" bind:value={player1AgentId} disabled={busy || agents.length === 0}>
                {#each agents as agent}<option value={agent.id}>{agent.name}</option>{/each}
              </select>
            </div>
          {/if}

          <div class="field">
            <label for="p1-deck">デッキ</label>
            <select id="p1-deck" value={player1DeckSource} disabled={busy}
              onchange={(event) => {
                player1DeckSource = event.currentTarget.value;
                onDeckSourceChange(0, event.currentTarget.value);
              }}>
              <option value="import">デッキを貼り付け</option>
              <option value="preset:sample">フーディン（サンプルデッキ）</option>
              <optgroup label="上位アーキ0704">
                {#each TOURNAMENT_DECKS as deck}<option value={`preset:${deck.id}`}>{deck.name}</option>{/each}
              </optgroup>
              {#if savedDecks.length}
                <optgroup label="保存したデッキ（デッキ編成）">
                  {#each savedDecks as deck}<option value={`deck:${deck.id}`}>{deck.name}</option>{/each}
                </optgroup>
              {/if}
              {#each deckOptions as agent}<option value={agent.id}>{agent.name}</option>{/each}
            </select>
          </div>

          <button type="button" class="deck-strip" onclick={() => (previewTarget = 0)} title="デッキをカード画像で確認">
            <span class="fan">
              {#each summary1.art.slice(0, 4) as art}
                <img src={art} alt="" loading="lazy" decoding="async" />
              {/each}
            </span>
            <span class="strip-meta">
              <b class:bad={summary1.total !== 60}>{summary1.total}<small>枚</small></b>
              <small>ポケモン {summary1.pokemon}・トレーナーズ {summary1.trainer}・エネルギー {summary1.energy}</small>
              <small class="link">🃏 画像で確認</small>
            </span>
          </button>

          <details class="deck-editor" open={player1DeckSource === 'import'}>
            <summary>デッキリスト（テキスト）</summary>
            <textarea bind:value={deck1Text} aria-label="プレイヤー1のデッキリスト"
              readonly={player1DeckLocked} class:locked={player1DeckLocked} spellcheck="false"></textarea>
          </details>
        </article>

        <div class="vs" aria-hidden="true"><span>VS</span></div>

        <!-- ============ プレイヤー2 ============ -->
        <article class="player-card">
          <header>
            <span class="player-tag p2">PLAYER 2</span>
            <span class="control-tabs" role="tablist" aria-label="プレイヤー2の操作">
              <button type="button" role="tab" aria-selected={player2Control === 'self'}
                class:active={player2Control === 'self'} disabled={busy}
                onclick={() => setPlayerControl(1, 'self')}>自分</button>
              <button type="button" role="tab" aria-selected={player2Control === 'agent'}
                class:active={player2Control === 'agent'} disabled={busy}
                onclick={() => setPlayerControl(1, 'agent')}>AI</button>
            </span>
          </header>

          {#if player2Control === 'agent'}
            <div class="field">
              <label for="p2-agent">AI</label>
              <select id="p2-agent" bind:value={player2AgentId} disabled={busy || agents.length === 0}>
                {#each agents as agent}<option value={agent.id}>{agent.name}</option>{/each}
              </select>
            </div>
          {/if}

          <div class="field">
            <label for="p2-deck">デッキ</label>
            <select id="p2-deck" value={player2DeckSource} disabled={busy}
              onchange={(event) => {
                player2DeckSource = event.currentTarget.value;
                onDeckSourceChange(1, event.currentTarget.value);
              }}>
              <option value="import">デッキを貼り付け</option>
              <option value="preset:sample">フーディン（サンプルデッキ）</option>
              <optgroup label="上位アーキ0704">
                {#each TOURNAMENT_DECKS as deck}<option value={`preset:${deck.id}`}>{deck.name}</option>{/each}
              </optgroup>
              {#if savedDecks.length}
                <optgroup label="保存したデッキ（デッキ編成）">
                  {#each savedDecks as deck}<option value={`deck:${deck.id}`}>{deck.name}</option>{/each}
                </optgroup>
              {/if}
              {#each deckOptions as agent}<option value={agent.id}>{agent.name}</option>{/each}
            </select>
          </div>

          <button type="button" class="deck-strip" onclick={() => (previewTarget = 1)} title="デッキをカード画像で確認">
            <span class="fan">
              {#each summary2.art.slice(0, 4) as art}
                <img src={art} alt="" loading="lazy" decoding="async" />
              {/each}
            </span>
            <span class="strip-meta">
              <b class:bad={summary2.total !== 60}>{summary2.total}<small>枚</small></b>
              <small>ポケモン {summary2.pokemon}・トレーナーズ {summary2.trainer}・エネルギー {summary2.energy}</small>
              <small class="link">🃏 画像で確認</small>
            </span>
          </button>

          <details class="deck-editor" open={player2DeckSource === 'import'}>
            <summary>デッキリスト（テキスト）</summary>
            <textarea bind:value={deck2Text} aria-label="プレイヤー2のデッキリスト"
              readonly={player2DeckLocked} class:locked={player2DeckLocked} spellcheck="false"></textarea>
          </details>
        </article>
      </div>

      <button class="primary start" disabled={startDisabled} onclick={startGame}>
        {busy ? '開始中…' : '対戦開始'}
      </button>

      <article class="online-card">
        <header>
          <strong>🌐 オンライン対戦</strong>
          <span>遠隔の相手とリアルタイム — プレイヤー1のデッキを使用します</span>
        </header>
        {#if onLocalServer}
          <p class="online-warning">
            ⚠ いま開いているのは<strong>このPC専用のローカル版</strong>です。遠隔の相手とはルームがつながりません。
            2人とも共有URL <strong>https://kahtgf-pokeca-cabt.hf.space</strong> を開いてください。
          </p>
        {/if}
        <div class="online-actions">
          <button type="button" disabled={busy || onlineBusy} onclick={createOnlineRoom}>
            {onlineBusy ? '処理中…' : 'ルームを作成'}
          </button>
          <span class="online-join">
            <input type="text" bind:value={onlineJoinCode} placeholder="ルームコード（例: ABC234）"
              aria-label="参加するルームコード" maxlength="8" spellcheck="false"
              onkeydown={(event) => event.key === 'Enter' && onlineJoinCode.trim() && joinOnlineRoom(onlineJoinCode)} />
            <button type="button" disabled={busy || onlineBusy || !onlineJoinCode.trim()}
              onclick={() => joinOnlineRoom(onlineJoinCode)}>参加</button>
          </span>
        </div>
      </article>

      {#if error}
        <pre class="error">{error}</pre>
      {/if}
      {#if previewTarget !== null}
        <DeckPreviewModal
          title={previewTarget === 0 ? 'プレイヤー1のデッキ' : 'プレイヤー2のデッキ'}
          deckText={previewTarget === 0 ? deck1Text : deck2Text}
          onClose={() => (previewTarget = null)}
        />
      {/if}
    {:else}
      <div class="log-toolbar">
        <strong>対戦ログ</strong>
        <button type="button" disabled={catalogBusy} onclick={refreshCatalog}>
          {catalogBusy ? '更新中…' : '更新'}
        </button>
      </div>

      {#if catalogError || error}
        <pre class="error">{catalogError || error}</pre>
      {/if}

      {#if catalogBusy && gameLogs.length === 0}
        <p class="empty">対戦ログを読み込み中…</p>
      {:else if gameLogs.length === 0}
        <p class="empty"><code>public/game-logs</code> に対戦ログがありません。</p>
      {:else}
        <div class="log-list">
          {#each gameLogs as log}
            <button type="button" disabled={busy} onclick={() => loadGameLog(log)}>
              <span>
                <strong>{log.name}</strong>
                <small>{logPlayerLabel(log)}</small>
              </span>
              <span>
                {#if log.createdAt}<small>{log.createdAt}</small>{/if}
                <small>{log.file}</small>
              </span>
            </button>
          {/each}
        </div>
      {/if}
    {/if}
  </div>
</section>

<style>
  .import-screen {
    min-height: 100vh;
    max-height: 100vh;
    overflow-y: auto;
    padding: 84px 0 64px;
  }

  .page {
    width: min(1120px, calc(100vw - 48px));
    margin: 0 auto;
    display: grid;
    gap: 20px;
    align-content: start;
  }

  .page-head {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
  }

  .eyebrow {
    margin: 0 0 2px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.24em;
    color: var(--accent-base);
  }

  h2 {
    margin: 0;
    font-size: 26px;
    font-weight: 900;
    letter-spacing: 0.02em;
    color: var(--text-primary);
  }

  .home-tabs {
    display: inline-grid;
    grid-template-columns: repeat(2, minmax(104px, 1fr));
    gap: 4px;
    padding: 4px;
    border-radius: 10px;
    border: 1px solid var(--surface-inset-border);
    background: var(--surface-inset-bg);
  }

  .home-tabs button {
    border: 0;
    border-radius: 7px;
    padding: 8px 14px;
    background: transparent;
    color: var(--text-secondary);
    font-weight: 700;
  }

  .home-tabs button.active {
    background: var(--accent-base);
    color: var(--text-on-accent);
  }

  /* ---- セットアップ2カラム ---- */
  .setup-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
    gap: 14px;
    align-items: stretch;
  }

  .player-card {
    display: grid;
    gap: 14px;
    align-content: start;
    padding: 18px;
    border-radius: 14px;
    border: 1px solid var(--surface-glass-border);
    background: var(--surface-glass-bg);
    box-shadow: var(--surface-glass-shadow);
  }

  .player-card header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }

  .player-tag {
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.2em;
    padding: 5px 10px;
    border-radius: 6px;
    color: var(--text-on-accent);
    background: var(--accent-base);
  }

  .player-tag.p2 {
    background: var(--surface-inset-bg);
    color: var(--text-secondary);
    border: 1px solid var(--surface-inset-border);
  }

  .control-tabs {
    display: grid;
    grid-template-columns: repeat(2, 72px);
    gap: 4px;
    padding: 3px;
    border-radius: 9px;
    border: 1px solid var(--surface-inset-border);
    background: var(--surface-inset-bg);
  }

  .control-tabs button {
    border: 0;
    border-radius: 6px;
    padding: 6px 0;
    background: transparent;
    color: var(--text-secondary);
    font-weight: 800;
  }

  .control-tabs button.active {
    background: var(--accent-base);
    color: var(--text-on-accent);
  }

  .field {
    display: grid;
    grid-template-columns: 52px minmax(0, 1fr);
    align-items: center;
    gap: 10px;
  }

  .field label {
    font-size: 12px;
    font-weight: 800;
    color: var(--text-secondary);
  }

  select {
    min-height: 42px;
    border-radius: 10px;
    border: 1px solid var(--input-border);
    background: var(--input-bg);
    color: var(--input-text);
    padding: 0 12px;
    font-weight: 600;
  }

  /* OSが描くドロップダウンは常に「白地×黒文字」に固定して確実に読めるようにする */
  :global([data-theme='dark']) select { color-scheme: dark; }
  :global([data-theme='light']) select { color-scheme: light; }
  select option,
  select optgroup {
    background: #ffffff;
    color: #1d232b;
  }

  /* ---- デッキ要約ストリップ（クリックで画像プレビュー） ---- */
  .deck-strip {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    gap: 16px;
    padding: 12px 14px;
    border-radius: 12px;
    border: 1px solid var(--surface-inset-border);
    background: var(--surface-inset-bg);
    cursor: pointer;
    text-align: left;
    transition: border-color 0.15s ease, transform 0.15s ease;
  }

  .deck-strip:hover {
    border-color: var(--accent-base);
    transform: translateY(-1px);
  }

  .fan {
    display: flex;
    min-width: 118px;
  }

  .fan img {
    width: 52px;
    border-radius: 4px;
    border: 1px solid rgba(255, 255, 255, 0.14);
    box-shadow: -5px 4px 12px rgba(0, 0, 0, 0.4);
  }

  .fan img + img {
    margin-left: -26px;
  }

  .fan img:nth-child(2) { transform: rotate(3deg) translateY(2px); }
  .fan img:nth-child(3) { transform: rotate(6deg) translateY(5px); }
  .fan img:nth-child(4) { transform: rotate(9deg) translateY(9px); }

  .strip-meta {
    display: grid;
    gap: 2px;
  }

  .strip-meta b {
    font-size: 22px;
    font-weight: 900;
    color: var(--text-primary);
    line-height: 1.1;
  }

  .strip-meta b small {
    font-size: 12px;
    font-weight: 700;
    color: var(--text-secondary);
    margin-left: 2px;
  }

  .strip-meta b.bad {
    color: var(--danger-strong);
  }

  .strip-meta small {
    font-size: 11.5px;
    color: var(--text-secondary);
  }

  .strip-meta .link {
    color: var(--accent-base);
    font-weight: 700;
  }

  /* ---- 折りたたみ式のテキスト編集 ---- */
  .deck-editor summary {
    cursor: pointer;
    user-select: none;
    font-size: 12px;
    font-weight: 700;
    color: var(--text-secondary);
    padding: 4px 2px;
  }

  .deck-editor[open] summary {
    color: var(--text-primary);
  }

  .deck-editor textarea {
    margin-top: 8px;
    width: 100%;
    min-height: 34vh;
    resize: vertical;
    border-radius: 10px;
    border: 1px solid var(--input-border);
    background: var(--input-bg);
    color: var(--input-text);
    padding: 12px;
    font-size: 13px;
    line-height: 1.6;
  }

  .deck-editor textarea.locked {
    background: var(--surface-inset-bg);
    color: var(--text-primary);
    cursor: default;
  }

  .vs {
    align-self: center;
    display: grid;
    place-items: center;
  }

  .vs span {
    font-size: 15px;
    font-weight: 900;
    letter-spacing: 0.1em;
    color: var(--text-muted);
    border: 1px solid var(--surface-inset-border);
    background: var(--surface-inset-bg);
    border-radius: 999px;
    padding: 10px 12px;
  }

  /* ---- 開始ボタン・オンライン ---- */
  .primary.start {
    border: 0;
    border-radius: 12px;
    min-height: 54px;
    font-size: 17px;
    font-weight: 900;
    letter-spacing: 0.24em;
    color: var(--text-on-accent);
    background: var(--accent-base);
    box-shadow: 0 10px 30px color-mix(in srgb, var(--accent-base) 32%, transparent);
    transition: filter 0.15s ease, transform 0.1s ease;
  }

  .primary.start:not(:disabled):hover {
    filter: brightness(1.08);
  }

  .primary.start:not(:disabled):active {
    transform: translateY(1px);
  }

  .primary.start:disabled {
    opacity: 0.5;
    box-shadow: none;
  }

  .online-card {
    display: grid;
    gap: 12px;
    padding: 16px 18px;
    border-radius: 14px;
    border: 1px solid var(--surface-glass-border);
    background: var(--surface-glass-bg);
  }

  .online-card header {
    display: flex;
    align-items: baseline;
    gap: 12px;
    flex-wrap: wrap;
  }

  .online-card header strong {
    color: var(--text-primary);
  }

  .online-card header span {
    font-size: 12px;
    color: var(--text-secondary);
  }

  .online-warning {
    margin: 0;
    padding: 10px 12px;
    border: 1px solid var(--warning-base, #b8860b);
    border-radius: 8px;
    font-size: 12.5px;
    color: var(--text-primary);
    background: var(--surface-inset-bg);
  }

  .online-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
  }

  .online-actions button {
    border: 1px solid var(--button-border);
    border-radius: 9px;
    background: var(--button-bg);
    color: var(--button-text);
    font-weight: 700;
    padding: 10px 16px;
  }

  .online-join {
    display: grid;
    grid-template-columns: minmax(170px, 230px) auto;
    gap: 8px;
  }

  .online-join input {
    min-height: 40px;
    border-radius: 9px;
    border: 1px solid var(--input-border);
    background: var(--input-bg);
    color: var(--input-text);
    padding: 0 12px;
    text-transform: uppercase;
  }

  /* ---- 対戦ログタブ ---- */
  .log-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }

  .log-toolbar strong {
    font-size: 16px;
    color: var(--text-primary);
  }

  .log-toolbar button {
    border: 1px solid var(--button-border);
    border-radius: 9px;
    background: var(--button-bg);
    color: var(--button-text);
    font-weight: 700;
    padding: 8px 16px;
  }

  .log-list {
    display: grid;
    gap: 8px;
    max-height: min(72vh, 820px);
    overflow: auto;
  }

  .log-list button {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(140px, auto);
    gap: 12px;
    align-items: center;
    min-height: 58px;
    padding: 10px 14px;
    border: 1px solid var(--surface-glass-border);
    border-radius: 12px;
    text-align: left;
    background: var(--surface-glass-bg);
    color: var(--text-primary);
    transition: border-color 0.15s ease;
  }

  .log-list button:hover {
    border-color: var(--accent-base);
  }

  .log-list span {
    display: grid;
    min-width: 0;
    gap: 2px;
  }

  .log-list strong,
  .log-list small {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .log-list small {
    color: var(--text-secondary);
    font-size: 12px;
  }

  .empty {
    margin: 0;
    color: var(--text-muted);
    font-size: 13px;
  }

  .error {
    margin: 0;
    padding: 12px;
    border-radius: 10px;
    background: var(--danger-bg);
    border: 1px solid var(--danger-border);
    color: var(--danger-strong);
    white-space: pre-wrap;
  }

  @media (max-width: 980px) {
    .setup-grid {
      grid-template-columns: 1fr;
    }

    .vs {
      display: none;
    }

    .log-list button {
      grid-template-columns: 1fr;
    }
  }
</style>
