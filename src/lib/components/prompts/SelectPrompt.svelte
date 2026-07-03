<script lang="ts">
  import PromptPanel from './primitives/PromptPanel.svelte';
  import { labelFor } from '../../game/labels';
  import { promptTitle } from '../../game/promptCopy';
  import { promptOptions } from '../../game/prompts';
  import type { PromptView } from '../../game/types';

  type Props = {
    prompt: PromptView;
    resolving?: boolean;
    onresolve: (value: unknown) => void;
  };

  let { prompt, resolving = false, onresolve }: Props = $props();

  let options = $derived(promptOptions(prompt));
  let values = $derived(Array.isArray(prompt.fields.values) ? prompt.fields.values : []);
  let mulliganDrawValues = $derived(getMulliganDrawValues(prompt, values));
  let isMulliganDrawPrompt = $derived(mulliganDrawValues.length > 0);
  let minMulliganDraw = $derived(isMulliganDrawPrompt ? Math.min(...mulliganDrawValues.map((item) => item.value)) : 0);
  let maxMulliganDraw = $derived(isMulliganDrawPrompt ? Math.max(...mulliganDrawValues.map((item) => item.value)) : 0);
  let mulliganDrawAmount = $state(0);
  let mulliganDrawKey = $state('');

  $effect(() => {
    const key = `${prompt.id}:${mulliganDrawValues.map((item) => item.value).join(',')}`;
    if (isMulliganDrawPrompt && mulliganDrawKey !== key) {
      const defaultIndex = normalizeSelectionLimit(options.defaultValue, 0);
      mulliganDrawAmount = mulliganDrawValues.find((item) => item.index === defaultIndex)?.value ?? maxMulliganDraw;
      mulliganDrawKey = key;
    } else if (!isMulliganDrawPrompt && mulliganDrawKey) {
      mulliganDrawKey = '';
      mulliganDrawAmount = 0;
    }
  });

  function submitMulliganDraw() {
    const option = mulliganDrawValues.find((item) => item.value === Number(mulliganDrawAmount));
    if (option) {
      onresolve(option.index);
    }
  }

  function parseMulliganDrawValue(value: unknown) {
    if (typeof value !== 'string') {
      return null;
    }
    const match = /^Draw\s+(\d+)\s+card\(s\)$/i.exec(value.trim());
    return match ? Number(match[1]) : null;
  }

  function getMulliganDrawValues(currentPrompt: PromptView, rawValues: unknown[]) {
    if (currentPrompt.message !== 'WANT_TO_DRAW_CARDS') {
      return [];
    }
    const parsed = rawValues.map((value, index) => {
      const drawValue = parseMulliganDrawValue(value);
      return drawValue === null ? null : { value: drawValue, index };
    });
    return parsed.every(Boolean) ? (parsed as Array<{ value: number; index: number }>) : [];
  }

  function normalizeSelectionLimit(raw: unknown, fallback: number) {
    const value = Number(raw);
    return Number.isFinite(value) ? value : fallback;
  }

  // CabtSelectContext.IS_FIRST = 41 (turn-order choice).
  let minSelections = $derived(normalizeSelectionLimit(options.min, 0));
  let isTurnOrderChoice = $derived((prompt.fields?.cabtSelect as { context?: number } | undefined)?.context === 41);

  function pickRandom() {
    if (values.length) {
      onresolve(Math.floor(Math.random() * values.length));
    }
  }
  function advanceFirstLegal() {
    onresolve(minSelections > 0 ? Array.from({ length: minSelections }, (_unused, index) => index) : []);
  }
</script>

<PromptPanel
  title={isMulliganDrawPrompt ? 'カードを追加で引きますか？' : promptTitle(prompt, '選ぶ')}
  warning={!prompt.supported ? (prompt.unsupportedReason ?? 'このプロンプトは高度なリゾルバが必要です。') : undefined}
>
  {#if isMulliganDrawPrompt}
    <div class="mulligan-slider">
      <div class="mulligan-slider-meta">
        <span>マリガン</span>
        <strong>{mulliganDrawAmount}枚引く</strong>
      </div>
      <input
        type="range"
        min={minMulliganDraw}
        max={maxMulliganDraw}
        step="1"
        bind:value={mulliganDrawAmount}
        aria-label={`カードを${mulliganDrawAmount}枚引く`}
      />
      <div class="mulligan-slider-scale" aria-hidden="true">
        <span>{minMulliganDraw}</span>
        <span>{maxMulliganDraw}</span>
      </div>
    </div>
  {:else if values.length}
    {#if typeof prompt.fields.detail === 'string' && prompt.fields.detail}
      <p class="prompt-detail">{prompt.fields.detail}</p>
    {/if}
    <div class="prompt-grid">
      {#each values as value, index}
        <button disabled={resolving} onclick={() => onresolve(index)}>{labelFor(value)}</button>
      {/each}
    </div>
  {:else}
    <p class="prompt-empty">この選択に対象がありません。「進める」で続行してください。</p>
  {/if}

  {#snippet actions()}
    {#if options.allowCancel}
      <button disabled={resolving} onclick={() => onresolve(null)}>キャンセル</button>
    {/if}
    {#if isTurnOrderChoice && values.length}
      <button disabled={resolving} onclick={pickRandom}>ランダム</button>
    {/if}
    {#if isMulliganDrawPrompt}
      <button class="primary" disabled={resolving} onclick={submitMulliganDraw}>確定</button>
    {:else if minSelections === 0}
      <button disabled={resolving} onclick={() => onresolve([])}>スキップ</button>
    {:else if !values.length}
      <button class="primary" disabled={resolving} onclick={advanceFirstLegal}>進める</button>
    {/if}
  {/snippet}
</PromptPanel>
