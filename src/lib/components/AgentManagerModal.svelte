<script lang="ts">
  import type { AgentOption } from '../home/catalog';

  type Props = {
    profile: string;
    agents: AgentOption[];
    onupload: (name: string, mainPy: string, deckCsv: string) => Promise<{ ok: boolean; error?: string }>;
    ondelete: (name: string) => Promise<void> | void;
    onclose: () => void;
  };
  let { profile, agents, onupload, ondelete, onclose }: Props = $props();

  let name = $state('');
  let mainPy = $state('');
  let mainFileName = $state('');
  let deckCsv = $state('');
  let deckFileName = $state('');
  let uploading = $state(false);
  let message = $state('');
  let error = $state('');

  let canUpload = $derived(!!name.trim() && !!mainPy.trim() && !uploading);

  async function onMainFile(event: Event) {
    const file = (event.currentTarget as HTMLInputElement).files?.[0];
    if (!file) return;
    mainPy = await file.text();
    mainFileName = file.name;
  }
  async function onDeckFile(event: Event) {
    const file = (event.currentTarget as HTMLInputElement).files?.[0];
    if (!file) return;
    deckCsv = await file.text();
    deckFileName = file.name;
  }

  async function submit() {
    error = '';
    message = '';
    uploading = true;
    try {
      const result = await onupload(name.trim(), mainPy, deckCsv);
      if (result.ok) {
        message = `「${name.trim()}」をアップロードしました。`;
        name = '';
        mainPy = '';
        mainFileName = '';
        deckCsv = '';
        deckFileName = '';
      } else {
        error = result.error ?? 'アップロードに失敗しました。';
      }
    } finally {
      uploading = false;
    }
  }

  function onKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') onclose();
  }
</script>

<svelte:window onkeydown={onKeydown} />

<div class="backdrop" onclick={onclose} role="presentation">
  <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="自作AIの管理" tabindex="-1">
    <button class="close" onclick={onclose} aria-label="閉じる">×</button>
    <header>
      <h2>自作AIの管理</h2>
      <p>ユーザー「{profile}」のワークスペースに、自作AI（main.py）とデッキ（deck.csv）をアップロードします。</p>
    </header>

    <section class="upload">
      <label class="field">
        <span>エージェント名</span>
        <input bind:value={name} placeholder="例: my-mcts" spellcheck="false" />
      </label>
      <div class="files">
        <label class="filebtn">
          main.py を選ぶ
          <input type="file" accept=".py,text/x-python,text/plain" onchange={onMainFile} />
          {#if mainFileName}<em>{mainFileName}（{mainPy.length}字）</em>{/if}
        </label>
        <label class="filebtn">
          deck.csv を選ぶ（任意）
          <input type="file" accept=".csv,text/csv,text/plain" onchange={onDeckFile} />
          {#if deckFileName}<em>{deckFileName}</em>{/if}
        </label>
      </div>
      <button class="primary" disabled={!canUpload} onclick={submit}>
        {uploading ? 'アップロード中…' : 'アップロード'}
      </button>
      {#if message}<p class="ok">{message}</p>{/if}
      {#if error}<p class="err">{error}</p>{/if}
      <p class="hint">main.py は <code>agent(obs_dict) -&gt; list[int]</code> を定義する必要があります（公式サンプルと同形式）。アップロード後、対戦のエージェント選択に表示されます。</p>
    </section>

    <section class="list">
      <h3>このユーザーの自作AI（{agents.length}）</h3>
      {#if agents.length === 0}
        <p class="empty">まだありません。上のフォームから追加してください。</p>
      {:else}
        <ul>
          {#each agents as agent (agent.id)}
            <li>
              <span class="agent-name">{agent.name}</span>
              <button class="danger" onclick={() => ondelete(agent.name)}>削除</button>
            </li>
          {/each}
        </ul>
      {/if}
    </section>
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 60;
    background: var(--overlay-backdrop-bg);
    backdrop-filter: blur(var(--backdrop-blur));
    display: grid;
    place-items: center;
    padding: 24px;
  }
  .modal {
    position: relative;
    width: min(560px, 100%);
    max-height: 88vh;
    overflow-y: auto;
    padding: 22px;
    border-radius: var(--radius-lg);
    background: var(--surface-glass-bg);
    border: 1px solid var(--surface-glass-border);
    box-shadow: var(--surface-glass-shadow);
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  .close {
    position: absolute;
    top: 10px;
    right: 12px;
    width: 30px;
    height: 30px;
    border: none;
    border-radius: var(--radius-pill);
    background: var(--button-ghost-bg);
    color: var(--text-secondary);
    font-size: 20px;
    cursor: pointer;
  }
  header h2 { margin: 0; font-size: 20px; color: var(--text-primary); }
  header p { margin: 6px 0 0; font-size: 13px; color: var(--text-muted); line-height: 1.6; }
  .upload { display: flex; flex-direction: column; gap: 10px; }
  .field { display: grid; gap: 4px; }
  .field span { font-size: 12px; font-weight: 700; color: var(--text-secondary); }
  .field input {
    padding: 8px 10px;
    border: 1px solid var(--input-border);
    border-radius: var(--radius-sm);
    background: var(--input-bg);
    color: var(--input-text);
    font-size: 14px;
  }
  .files { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .filebtn {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 10px;
    border: 1px dashed var(--button-border);
    border-radius: var(--radius-sm);
    background: var(--surface-inset-bg);
    color: var(--text-secondary);
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
  }
  .filebtn input { display: none; }
  .filebtn em { font-style: normal; font-size: 11px; color: var(--accent-strong); word-break: break-all; }
  .primary {
    padding: 10px;
    border: 1px solid var(--button-primary-border);
    border-radius: var(--radius-sm);
    background: var(--button-primary-bg);
    color: var(--button-primary-text);
    font-size: 14px;
    font-weight: 700;
    cursor: pointer;
  }
  .primary:disabled { opacity: var(--disabled-opacity); cursor: not-allowed; }
  .ok { margin: 0; color: var(--accent-strong); font-size: 13px; font-weight: 600; }
  .err { margin: 0; color: var(--danger-text); font-size: 13px; white-space: pre-wrap; }
  .hint { margin: 0; font-size: 12px; color: var(--text-muted); line-height: 1.6; }
  .hint code { background: var(--surface-inset-bg); padding: 1px 5px; border-radius: 4px; }
  .list { border-top: 1px solid var(--surface-inset-border); padding-top: 12px; }
  .list h3 { margin: 0 0 8px; font-size: 13px; color: var(--text-secondary); }
  .empty { margin: 0; font-size: 13px; color: var(--text-muted); }
  .list ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
  .list li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 10px;
    border: 1px solid var(--surface-glass-border);
    border-radius: var(--radius-sm);
    background: var(--surface-inset-bg);
  }
  .agent-name { font-size: 14px; font-weight: 600; color: var(--text-primary); }
  .danger {
    padding: 5px 12px;
    border: 1px solid var(--danger-border);
    border-radius: var(--radius-sm);
    background: var(--button-bg);
    color: var(--danger-text);
    font-size: 12px;
    cursor: pointer;
  }
  @media (max-width: 560px) {
    .files { grid-template-columns: 1fr; }
  }
</style>
