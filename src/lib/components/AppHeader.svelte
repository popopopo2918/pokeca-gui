<script lang="ts">
  import Logo from './Logo.svelte';
  import { viewSettingsStore } from '../../state/viewSettings.svelte';

  type Props = {
    onOpenDeckBuilder?: () => void;
    profiles?: string[];
    activeProfile?: string;
    onSelectProfile?: (name: string) => void;
    onCreateProfile?: (name: string) => void;
    onImportSamples?: () => void;
    onManageAgents?: () => void;
  };
  let {
    onOpenDeckBuilder,
    profiles = [],
    activeProfile = '',
    onSelectProfile,
    onCreateProfile,
    onImportSamples,
    onManageAgents,
  }: Props = $props();

  let creating = $state(false);
  let newName = $state('');

  function submitNew() {
    const name = newName.trim();
    if (name) {
      onCreateProfile?.(name);
    }
    newName = '';
    creating = false;
  }
</script>

<header class="app-header">
  <div class="brand">
    <Logo size={36} />
  </div>
  <div class="actions">
    <div class="profile skin-picker">
      <span class="label">スキン</span>
      <select
        value={viewSettingsStore.skin}
        onchange={(e) => (viewSettingsStore.skin = (e.currentTarget as HTMLSelectElement).value)}
        aria-label="見た目スキン"
      >
        <option value="default">現行</option>
        <option value="tabletop">A 卓上プロ</option>
        <option value="broadcast">B 大会放送</option>
        <option value="binder">C バインダー</option>
      </select>
    </div>
    {#if onSelectProfile && profiles.length}
      <div class="profile">
        <span class="label">ユーザー</span>
        <select
          value={activeProfile}
          onchange={(e) => onSelectProfile?.((e.currentTarget as HTMLSelectElement).value)}
          aria-label="作業ユーザー（プロフィール）"
        >
          {#each profiles as profile}<option value={profile}>{profile}</option>{/each}
        </select>
        {#if creating}
          <input
            class="new-name"
            placeholder="新しいユーザー名"
            bind:value={newName}
            onkeydown={(e) => e.key === 'Enter' && submitNew()}
          />
          <button onclick={submitNew}>作成</button>
          <button class="ghost" onclick={() => { creating = false; newName = ''; }} aria-label="キャンセル">×</button>
        {:else}
          <button onclick={() => (creating = true)}>＋新規</button>
          {#if onManageAgents}
            <button onclick={onManageAgents} title="自作AI（main.py/deck.csv）をアップロード・管理">自作AI</button>
          {/if}
          {#if onImportSamples}
            <button onclick={onImportSamples} title="公式サンプルをこのユーザーのワークスペースにコピー">公式をコピー</button>
          {/if}
        {/if}
      </div>
    {/if}
    {#if onOpenDeckBuilder}
      <button class="nav-btn" onclick={onOpenDeckBuilder}>🃏 デッキ編成 / カード一覧</button>
    {/if}
  </div>
</header>

<style>
  .app-header {
    position: absolute;
    top: 20px;
    left: 24px;
    right: 24px;
    z-index: 5;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    pointer-events: none;
  }

  .app-header :global(.logo) {
    filter: none;
  }

  .actions {
    pointer-events: auto;
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .profile {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 8px;
    border-radius: var(--radius-pill);
    background: var(--surface-glass-bg);
    border: 1px solid var(--surface-glass-border);
    box-shadow: var(--surface-toolbar-shadow);
    backdrop-filter: blur(var(--backdrop-blur));
  }

  .profile .label {
    font-size: 12px;
    font-weight: 700;
    color: var(--text-muted);
    padding-left: 4px;
  }

  .profile select,
  .profile .new-name {
    padding: 5px 8px;
    border: 1px solid var(--input-border);
    border-radius: var(--radius-sm);
    background: var(--input-bg);
    color: var(--input-text);
    font-size: 13px;
    font-weight: 600;
  }

  .profile button {
    padding: 5px 10px;
    border: 1px solid var(--button-border);
    border-radius: var(--radius-sm);
    background: var(--button-bg);
    color: var(--button-text);
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
  }

  .profile button:hover {
    border-color: var(--accent-base);
  }

  .profile button.ghost {
    border: none;
    background: transparent;
    color: var(--text-muted);
  }

  .nav-btn {
    padding: 9px 16px;
    border: 1px solid var(--button-border);
    border-radius: var(--radius-pill);
    background: var(--surface-glass-bg);
    color: var(--button-text);
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    box-shadow: var(--surface-toolbar-shadow);
    backdrop-filter: blur(var(--backdrop-blur));
    transition: border-color var(--transition-fast);
  }

  .nav-btn:hover {
    border-color: var(--accent-base);
  }
</style>
