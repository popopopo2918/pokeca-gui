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
    exportLog,
    exporting = false,
  }: Props = $props();
</script>

<div class="table-toolbar">
  <button
    class="danger concede-top"
    style="width:100%; font-weight:900; border:1px solid var(--danger-border); background:var(--danger-bg); color:var(--danger-strong);"
    disabled={busy || promptActive || gameFinished || reviewing}
    onclick={concede}
  >投了</button>
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
  <label>
    <input type="checkbox" bind:checked={showLogs} />
    ログを表示
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
  <div class="review-controls">
    <div class="rewind-row">
      <button disabled={!canStepBack} onclick={stepBack} title="一手もどって確認">◀ もどる</button>
      <button disabled={!reviewing} onclick={stepForward} title="一手すすむ">すすむ ▶</button>
    </div>
    <button class="live-btn" class:reviewing disabled={!reviewing} onclick={returnToLive}>
      {reviewing ? `最新へ戻る（${reviewLabel}）` : 'ライブ表示中'}
    </button>
    <button onclick={exportLog} disabled={exporting}>{exporting ? '出力中…' : 'ログ出力'}</button>
  </div>
  <div class="sidebar-turn-actions">
    <button disabled={busy || promptActive || gameFinished || reviewing} onclick={passTurn}>番を終える</button>
  </div>
  <button disabled={switchDisabled} onclick={switchSides}>視点を入れ替え</button>
  <button onclick={resetGame}>{resetLabel}</button>
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
    color: var(--danger-text);
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
