<script lang="ts">
  import Logo from './Logo.svelte';

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
    <!-- 設定類は1本のコントロールバーにまとめる -->
    {#if onSelectProfile && profiles.length}
      <div class="cluster">
        <div class="group">
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
            <button class="quiet" onclick={submitNew}>作成</button>
            <button class="quiet ghost" onclick={() => { creating = false; newName = ''; }} aria-label="キャンセル">×</button>
          {:else}
            <button class="quiet" onclick={() => (creating = true)}>＋新規</button>
            {#if onManageAgents}
              <button class="quiet" onclick={onManageAgents} title="自作AI（main.py/deck.csv）をアップロード・管理">自作AI</button>
            {/if}
            {#if onImportSamples}
              <button class="quiet" onclick={onImportSamples} title="公式サンプルをこのユーザーのワークスペースにコピー">公式をコピー</button>
            {/if}
          {/if}
        </div>
      </div>
    {/if}
    {#if onOpenDeckBuilder}
      <button class="nav-btn" onclick={onOpenDeckBuilder}>デッキ編成・カード一覧</button>
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

  /* 1本のバー: 中の要素は高さ30pxで統一し、縦の区切り線でグループを分ける */
  .cluster {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 7px 12px;
    border-radius: var(--radius-pill);
    background: var(--surface-glass-bg);
    border: 1px solid var(--surface-glass-border);
    box-shadow: var(--surface-toolbar-shadow);
    backdrop-filter: blur(var(--backdrop-blur));
  }

  .group {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .label {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.06em;
    color: var(--text-muted);
  }

  .group select,
  .group .new-name {
    height: 30px;
    padding: 0 8px;
    border: 1px solid transparent;
    border-radius: 8px;
    background: transparent;
    color: var(--input-text);
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.12s ease, border-color 0.12s ease;
  }

  .group select:hover,
  .group .new-name:focus {
    background: var(--surface-inset-bg);
    border-color: var(--surface-inset-border);
  }

  .group .new-name {
    cursor: text;
    width: 150px;
    border-color: var(--input-border);
    background: var(--input-bg);
  }

  .group .new-name:focus {
    outline: none;
    border-color: var(--accent-base);
  }

  button.quiet {
    height: 30px;
    padding: 0 10px;
    border: 1px solid transparent;
    border-radius: 8px;
    background: transparent;
    color: var(--text-secondary);
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
    transition: background 0.12s ease, color 0.12s ease, border-color 0.12s ease;
  }

  button.quiet:hover {
    background: var(--surface-inset-bg);
    border-color: var(--surface-inset-border);
    color: var(--text-primary);
  }

  button.quiet.ghost {
    padding: 0 7px;
    color: var(--text-muted);
  }

  .nav-btn {
    height: 44px;
    padding: 0 18px;
    border: 1px solid color-mix(in srgb, var(--accent-base) 55%, transparent);
    border-radius: var(--radius-pill);
    background: color-mix(in srgb, var(--accent-base) 14%, var(--surface-glass-bg));
    color: var(--text-primary);
    font-size: 13px;
    font-weight: 800;
    letter-spacing: 0.04em;
    cursor: pointer;
    box-shadow: var(--surface-toolbar-shadow);
    backdrop-filter: blur(var(--backdrop-blur));
    transition: border-color var(--transition-fast), background 0.12s ease;
  }

  .nav-btn:hover {
    border-color: var(--accent-base);
    background: color-mix(in srgb, var(--accent-base) 24%, var(--surface-glass-bg));
  }
</style>
