<script lang="ts">
  import DeckPreviewModal from './DeckPreviewModal.svelte';
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
  <div class="home-tabs" role="tablist" aria-label="ホームモード">
    <button class:active={homeMode === 'play'} type="button" onclick={() => setHomeMode('play')}>対戦</button>
    <button class:active={homeMode === 'logs'} type="button" onclick={() => setHomeMode('logs')}>対戦ログ</button>
  </div>

  {#if homeMode === 'play'}
    <div class="deck-import two-column">
      <div class="player-config">
        <span class="deck-label-row">
          プレイヤー1
          <button type="button" class="preview-button" onclick={() => (previewTarget = 0)}>🃏 画像で確認</button>
        </span>
        <span class="control-tabs" role="tablist" aria-label="プレイヤー1の操作">
          <button
            type="button"
            role="tab"
            aria-selected={player1Control === 'self'}
            class:active={player1Control === 'self'}
            disabled={busy}
            onclick={() => setPlayerControl(0, 'self')}
          >自分</button>
          <button
            type="button"
            role="tab"
            aria-selected={player1Control === 'agent'}
            class:active={player1Control === 'agent'}
            disabled={busy}
            onclick={() => setPlayerControl(0, 'agent')}
          >AI</button>
        </span>
        <span class:self-only={player1Control === 'self'} class="setup-fields">
          {#if player1Control === 'agent'}
            <span class="field-row">
              <span>AI</span>
              <select
                bind:value={player1AgentId}
                disabled={busy || agents.length === 0}
                aria-label="プレイヤー1のAI"
              >
                {#each agents as agent}
                  <option value={agent.id}>{agent.name}</option>
                {/each}
              </select>
            </span>
          {/if}
          <span class="field-row">
            <span>デッキ</span>
            <select
              bind:value={player1DeckSource}
              disabled={busy}
              aria-label="プレイヤー1のデッキ"
            >
              <option value="import">デッキを貼り付け</option>
              <option value="preset:sample">フーディン（サンプルデッキ）</option>
              {#if savedDecks.length}
                <optgroup label="保存したデッキ（デッキ編成）">
                  {#each savedDecks as deck}
                    <option value={`deck:${deck.id}`}>{deck.name}</option>
                  {/each}
                </optgroup>
              {/if}
              {#each deckOptions as agent}
                <option value={agent.id}>{agent.name}</option>
              {/each}
            </select>
          </span>
        </span>
        <textarea
          bind:value={deck1Text}
          aria-label="プレイヤー1のデッキリスト"
          readonly={player1DeckLocked}
          class:locked={player1DeckLocked}
          spellcheck="false"
        ></textarea>
      </div>
      <div class="player-config">
        <span class="deck-label-row">
          プレイヤー2
          <button type="button" class="preview-button" onclick={() => (previewTarget = 1)}>🃏 画像で確認</button>
        </span>
        <span class="control-tabs" role="tablist" aria-label="プレイヤー2の操作">
          <button
            type="button"
            role="tab"
            aria-selected={player2Control === 'self'}
            class:active={player2Control === 'self'}
            disabled={busy}
            onclick={() => setPlayerControl(1, 'self')}
          >自分</button>
          <button
            type="button"
            role="tab"
            aria-selected={player2Control === 'agent'}
            class:active={player2Control === 'agent'}
            disabled={busy}
            onclick={() => setPlayerControl(1, 'agent')}
          >AI</button>
        </span>
        <span class:self-only={player2Control === 'self'} class="setup-fields">
          {#if player2Control === 'agent'}
            <span class="field-row">
              <span>AI</span>
              <select
                bind:value={player2AgentId}
                disabled={busy || agents.length === 0}
                aria-label="プレイヤー2のAI"
              >
                {#each agents as agent}
                  <option value={agent.id}>{agent.name}</option>
                {/each}
              </select>
            </span>
          {/if}
          <span class="field-row">
            <span>デッキ</span>
            <select
              bind:value={player2DeckSource}
              disabled={busy}
              aria-label="プレイヤー2のデッキ"
            >
              <option value="import">デッキを貼り付け</option>
              <option value="preset:sample">フーディン（サンプルデッキ）</option>
              {#if savedDecks.length}
                <optgroup label="保存したデッキ（デッキ編成）">
                  {#each savedDecks as deck}
                    <option value={`deck:${deck.id}`}>{deck.name}</option>
                  {/each}
                </optgroup>
              {/if}
              {#each deckOptions as agent}
                <option value={agent.id}>{agent.name}</option>
              {/each}
            </select>
          </span>
        </span>
        <textarea
          bind:value={deck2Text}
          aria-label="プレイヤー2のデッキリスト"
          readonly={player2DeckLocked}
          class:locked={player2DeckLocked}
          spellcheck="false"
        ></textarea>
      </div>
    </div>
    <button class="primary" disabled={startDisabled} onclick={startGame}>
      {busy ? '開始中…' : '対戦開始'}
    </button>

    <div class="online-box">
      <strong>🌐 オンライン対戦（遠隔の相手とリアルタイム）</strong>
      <p>プレイヤー1のデッキを使用します。ルームを作って表示されたコードを相手に伝えるか、相手から聞いたコードで参加してください（相手も同じURLを開きます）。</p>
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
          <input
            type="text"
            bind:value={onlineJoinCode}
            placeholder="ルームコード（例: ABC234）"
            aria-label="参加するルームコード"
            maxlength="8"
            spellcheck="false"
            onkeydown={(event) => event.key === 'Enter' && onlineJoinCode.trim() && joinOnlineRoom(onlineJoinCode)}
          />
          <button type="button" disabled={busy || onlineBusy || !onlineJoinCode.trim()} onclick={() => joinOnlineRoom(onlineJoinCode)}>
            参加
          </button>
        </span>
      </div>
    </div>

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
              {#if log.createdAt}
                <small>{log.createdAt}</small>
              {/if}
              <small>{log.file}</small>
            </span>
          </button>
        {/each}
      </div>
    {/if}
  {/if}
</section>

<style>
  .import-screen {
    min-height: 100vh;
    /* body は盤面用に overflow:hidden なので、この画面自身をスクロールさせる */
    max-height: 100vh;
    overflow-y: auto;
    display: grid;
    gap: 14px;
    align-content: start;
    padding: 92px 24px 32px;
  }

  .home-tabs {
    justify-self: stretch;
    display: inline-grid;
    grid-template-columns: repeat(2, minmax(96px, 1fr));
    gap: 4px;
    padding: 4px;
    border-radius: 8px;
    border: 1px solid var(--surface-inset-border);
    background: var(--surface-inset-bg);
    box-shadow: var(--surface-toolbar-shadow);
  }

  .home-tabs button {
    border: 0;
    border-radius: 6px;
    background: transparent;
    color: var(--text-secondary);
  }

  .home-tabs button.active {
    background: var(--button-bg);
    color: var(--button-text);
    box-shadow: var(--surface-toolbar-shadow);
  }

  .log-toolbar {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: 12px;
  }

  .deck-import {
    display: grid;
    gap: 16px;
  }

  .deck-import.two-column {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .player-config {
    display: grid;
    gap: 8px;
    color: var(--text-primary);
    font-weight: 800;
  }

  .deck-label-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  .control-tabs {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 4px;
    padding: 4px;
    border-radius: 8px;
    border: 1px solid var(--surface-inset-border);
    background: var(--surface-inset-bg);
  }

  .control-tabs button {
    border: 0;
    border-radius: 6px;
    background: transparent;
    color: var(--text-secondary);
    font-weight: 900;
  }

  .control-tabs button.active {
    background: var(--button-bg);
    color: var(--button-text);
    box-shadow: var(--surface-toolbar-shadow);
  }

  .setup-fields {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 10px;
    min-height: 40px;
  }

  .setup-fields.self-only {
    grid-template-columns: 1fr;
  }

  .field-row {
    display: grid;
    grid-template-columns: 52px minmax(0, 1fr);
    align-items: center;
    gap: 8px;
    color: var(--text-secondary);
    font-size: 12px;
    font-weight: 900;
  }

  textarea {
    width: 100%;
    /* オンライン対戦欄が初期表示で見えるよう、少し低めにする（伸ばせる） */
    min-height: 40vh;
    resize: vertical;
    border-radius: 8px;
    border: 1px solid var(--input-border);
    background: var(--input-bg);
    color: var(--input-text);
    padding: 12px;
  }

  textarea.locked {
    background: var(--surface-inset-bg);
    /* Keep the deck list fully readable even when read-only (the read-only state is signalled by
       the inset background, not by dimming the text). */
    color: var(--text-primary);
    cursor: default;
  }

  select {
    min-height: 40px;
    border-radius: 8px;
    border: 1px solid var(--input-border);
    background: var(--input-bg);
    color: var(--input-text);
    padding: 0 12px;
  }

  /* The OS-drawn dropdown popup follows the element's color-scheme, not its CSS colors.
     Without this, dark theme showed a white popup with near-white text. */
  :global([data-theme='dark']) select {
    color-scheme: dark;
  }

  :global([data-theme='light']) select {
    color-scheme: light;
  }

  /* Some Windows/Chromium environments draw the popup light no matter what
     color-scheme says, while still honoring the option's `color`. Hard-code a
     light row + dark text so options are readable under either rendering. */
  select option,
  select optgroup {
    background: #ffffff;
    color: #1d232b;
  }

  .online-box {
    display: grid;
    gap: 8px;
    padding: 14px;
    border: 1px solid var(--surface-inset-border);
    border-radius: 8px;
    background: var(--surface-inset-bg);
    color: var(--text-primary);
  }

  .online-box p {
    margin: 0;
    color: var(--text-secondary);
    font-size: 12px;
    font-weight: 400;
  }

  .online-box .online-warning {
    padding: 8px 10px;
    border: 1px solid var(--warning-base, #b8860b);
    border-radius: 6px;
    color: var(--text-primary);
  }

  .online-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
  }

  .online-actions button {
    border: 1px solid var(--button-border);
    border-radius: 8px;
    background: var(--button-bg);
    color: var(--button-text);
    font-weight: 700;
    padding: 9px 14px;
  }

  .online-join {
    display: grid;
    grid-template-columns: minmax(160px, 220px) auto;
    gap: 8px;
  }

  .online-join input {
    min-height: 38px;
    border-radius: 8px;
    border: 1px solid var(--input-border);
    background: var(--input-bg);
    color: var(--input-text);
    padding: 0 12px;
    text-transform: uppercase;
  }

  .preview-button {
    border: 1px solid var(--button-border);
    border-radius: 6px;
    background: var(--button-bg);
    color: var(--button-text);
    font-size: 12px;
    font-weight: 700;
    padding: 6px 10px;
  }


  .log-toolbar strong {
    font-size: 16px;
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
    border-radius: 8px;
    text-align: left;
    background: var(--button-bg);
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
    border-radius: 8px;
    background: var(--danger-bg);
    border: 1px solid var(--danger-border);
    color: var(--danger-strong);
    white-space: pre-wrap;
  }

  @media (max-width: 980px) {
    .deck-import.two-column,
    .log-list button {
      grid-template-columns: 1fr;
    }

    .log-toolbar {
      align-items: stretch;
      flex-direction: column;
    }

  }
</style>
