<script lang="ts">
  import BoardPerspectiveControls from './BoardPerspectiveControls.svelte';
  import { labelFor } from '../game/labels';
  import type { ThemePreference } from '../../state/viewSettings.svelte';

  type Props = {
    boardTilt: number;
    boardPerspective: number;
    boardScaleY: number;
    boardLift: number;
    followActive: boolean;
    autoConfirmPrompts: boolean;
    debugZones: boolean;
    showLogs: boolean;
    animateActions: boolean;
    showActionSpotlight: boolean;
    revealHands: boolean;
    actionStepDelayMs: number;
    themePreference: ThemePreference;
    busy?: boolean;
    promptActive?: boolean;
    gameFinished?: boolean;
    error?: string;
    resetPerspective: () => void;
    passTurn: () => void;
    concede: () => void;
    switchSides: () => void;
    switchDisabled?: boolean;
    resetGame: () => void;
    resetLabel?: string;
    reviewing?: boolean;
    reviewLabel?: string;
    canStepBack?: boolean;
    stepBack: () => void;
    stepForward: () => void;
    returnToLive: () => void;
    canUndo?: boolean;
    undoMove: () => void;
    exportLog: () => void;
    exporting?: boolean;
  };

  let {
    boardTilt = $bindable(),
    boardPerspective = $bindable(),
    boardScaleY = $bindable(),
    boardLift = $bindable(),
    followActive = $bindable(),
    autoConfirmPrompts = $bindable(),
    debugZones = $bindable(),
    showLogs = $bindable(),
    animateActions = $bindable(),
    showActionSpotlight = $bindable(),
    revealHands = $bindable(),
    actionStepDelayMs = $bindable(),
    themePreference = $bindable(),
    busy = false,
    promptActive = false,
    gameFinished = false,
    error = '',
    resetPerspective,
    passTurn,
    concede,
    switchSides,
    switchDisabled = false,
    resetGame,
    resetLabel = 'デッキを変更',
    reviewing = false,
    reviewLabel = '',
    canStepBack = false,
    stepBack,
    stepForward,
    returnToLive,
    canUndo = false,
    undoMove,
    exportLog,
    exporting = false,
  }: Props = $props();
</script>

<div class="table-toolbar">
  <button
    class="danger"
    disabled={busy || promptActive || gameFinished || reviewing}
    onclick={concede}
  >投了</button>
  <div class="sidebar-turn-actions">
    <button class="turn-end" disabled={busy || promptActive || gameFinished || reviewing} onclick={passTurn}>ターンエンド</button>
  </div>
  <div class="review-controls">
    <div class="rewind-row">
      <button disabled={!canStepBack} onclick={stepBack} title="一手もどって確認（Z）">◀ もどる</button>
      <button disabled={!reviewing} onclick={stepForward} title="一手すすむ（X）">すすむ ▶</button>
    </div>
    <button
      class="undo-btn"
      disabled={!canUndo || busy}
      onclick={undoMove}
      title="直前の自分の行動まで対戦を巻き戻して、別の手を指せます（山札の順番など非公開のカードは引き直し）"
    >1手戻して指し直す</button>
    <button class="live-btn" class:reviewing disabled={!reviewing} onclick={returnToLive}>
      {reviewing ? `最新へ戻る（${reviewLabel}）` : 'ライブ表示中'}
    </button>
    <button onclick={exportLog} disabled={exporting}>{exporting ? '出力中…' : 'ログ出力'}</button>
  </div>
  <button disabled={switchDisabled} onclick={switchSides}>視点を入れ替え</button>
  <label class="reveal-hands-toggle" title="AIの性能テスト用：相手（AI）の手札を表向きで表示します（H）">
    <input type="checkbox" bind:checked={revealHands} />
    相手の手札を見る（H）
  </label>
  <button onclick={resetGame}>{resetLabel}</button>
  <details class="display-settings">
    <summary>表示・デバッグ設定</summary>
    <div class="display-settings-body">
      <BoardPerspectiveControls
        bind:boardTilt
        bind:boardPerspective
        bind:boardScaleY
        bind:boardLift
        {resetPerspective}
      />
      <label>
        <input type="checkbox" bind:checked={followActive} />
        手番のプレイヤーを追従
      </label>
      <label>
        <input type="checkbox" bind:checked={autoConfirmPrompts} />
        公開を自動で確認
      </label>
      <label>
        <input type="checkbox" bind:checked={debugZones} />
        ゾーンをデバッグ表示
      </label>
      <label title="行動ログパネルの表示切替（L）">
        <input type="checkbox" bind:checked={showLogs} />
        ログを表示（L）
      </label>
      <label>
        <input type="checkbox" bind:checked={animateActions} />
        1手ずつ再生
      </label>
      <label>
        <input type="checkbox" bind:checked={showActionSpotlight} />
        アクション表示
      </label>
      <label>
        再生間隔(ms)
        <input
          class="compact-number"
          type="number"
          min="50"
          max="2500"
          step="50"
          bind:value={actionStepDelayMs}
          disabled={!animateActions}
        />
      </label>
      <label>
        テーマ
        <select bind:value={themePreference} aria-label="テーマ設定">
          <option value="system">システム</option>
          <option value="light">ライト</option>
          <option value="dark">ダーク</option>
        </select>
      </label>
    </div>
  </details>
  {#if error}
    <span class="inline-error">{labelFor(error)}</span>
  {/if}
</div>

<style>
  .table-toolbar {
    position: absolute;
    top: 54px;
    right: 14px;
    z-index: 8;
    width: 148px;
    min-height: 0;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    padding: 7px;
    border: 1px solid var(--surface-toolbar-border);
    background: var(--surface-toolbar-bg);
    border-radius: 6px;
    box-shadow: var(--surface-toolbar-shadow);
    backdrop-filter: blur(var(--backdrop-blur));
    flex-direction: column;
    align-items: stretch;
  }

  .table-toolbar label {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 2px 1px 5px;
    color: var(--text-secondary);
    font-size: 10px;
    line-height: 1.2;
  }

  .table-toolbar button {
    width: 100%;
    border-radius: 5px;
    padding: 6px 7px;
    border-color: var(--button-border);
    background: var(--button-bg);
    color: var(--button-text);
    font-size: 10px;
    font-weight: 700;
  }

  .table-toolbar input.compact-number {
    min-width: 0;
    width: 58px;
    padding: 2px 4px;
    border: 1px solid var(--input-border);
    border-radius: 4px;
    background: var(--input-bg);
    color: var(--input-text);
    font: inherit;
  }

  .review-controls {
    display: grid;
    gap: 6px;
    padding-bottom: 5px;
    border-bottom: 1px solid var(--surface-inset-border);
  }

  .review-controls .rewind-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
  }

  .review-controls .live-btn.reviewing {
    background: var(--accent-base);
    border-color: var(--accent-base);
    color: var(--text-on-accent);
  }

  .sidebar-turn-actions {
    display: grid;
    gap: 6px;
    padding-bottom: 5px;
    border-bottom: 1px solid var(--surface-inset-border);
  }

  .table-toolbar button.danger {
    border-color: var(--danger-border);
    background: var(--danger-bg);
    color: var(--danger-strong);
    font-weight: 900;
  }

  /* Stand-out turn-end button: fixed yellow works on both themes. */
  .table-toolbar button.turn-end {
    background: #f7c948;
    border-color: #d9a400;
    color: #1d232b;
    font-size: 12px;
    font-weight: 900;
    padding: 8px 7px;
  }

  .table-toolbar button.turn-end:not(:disabled):hover {
    background: #ffd75e;
  }

  .table-toolbar button.turn-end:disabled {
    opacity: 0.45;
  }

  .review-controls .undo-btn:not(:disabled) {
    border-color: var(--accent-base);
    color: var(--accent-base);
  }

  .reveal-hands-toggle {
    border: 1px solid var(--button-border);
    border-radius: 5px;
    padding: 6px 7px;
    background: var(--button-bg);
    color: var(--button-text);
    font-weight: 700;
    cursor: pointer;
    user-select: none;
  }

  .display-settings {
    border-top: 1px solid var(--surface-inset-border);
    padding-top: 5px;
  }

  .display-settings summary {
    padding: 6px 7px;
    border: 1px solid var(--button-border);
    border-radius: 5px;
    background: var(--button-bg);
    color: var(--button-text);
    font-size: 10px;
    font-weight: 700;
    text-align: center;
    cursor: pointer;
    user-select: none;
    list-style: none;
  }

  .display-settings summary::marker,
  .display-settings summary::-webkit-details-marker {
    display: none;
  }

  .display-settings[open] summary {
    background: var(--surface-inset-bg);
  }

  .display-settings-body {
    display: grid;
    gap: 2px;
    margin-top: 7px;
  }

  .table-toolbar select {
    min-width: 0;
    width: 100%;
    border: 1px solid var(--input-border);
    border-radius: var(--radius-sm);
    background: var(--input-bg);
    color: var(--input-text);
    font: inherit;
    font-weight: 700;
  }

  .inline-error {
    padding: 6px 8px;
    max-width: 100%;
    border-radius: 8px;
    border: 1px solid var(--danger-border);
    background: var(--danger-bg);
    color: var(--danger-strong);
    font-size: 11px;
  }
</style>
