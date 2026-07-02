<script lang="ts">
  import PromptPanel from './primitives/PromptPanel.svelte';
  import PromptIcon from './primitives/PromptIcon.svelte';
  import { promptSubtitle } from '../../game/promptCopy';
  import type { PromptView } from '../../game/types';

  type Props = {
    prompt: PromptView;
    resolving?: boolean;
    onresolve: (value: unknown) => void;
  };

  let { prompt, resolving = false, onresolve }: Props = $props();
</script>

<PromptPanel
  title="オモテかウラか"
  subtitle={promptSubtitle(prompt, 'オモテかウラか')}
  warning={!prompt.supported ? (prompt.unsupportedReason ?? 'このプロンプトは高度なリゾルバが必要です。') : undefined}
>
  {#snippet icon()}<PromptIcon name="coin" />{/snippet}

  {#snippet actions()}
    <button class="primary" disabled={resolving} onclick={() => onresolve(true)}>オモテ</button>
    <button class="primary" disabled={resolving} onclick={() => onresolve(false)}>ウラ</button>
  {/snippet}
</PromptPanel>
