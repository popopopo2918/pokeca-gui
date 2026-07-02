<script lang="ts">
  import PromptPanel from './primitives/PromptPanel.svelte';
  import PromptIcon from './primitives/PromptIcon.svelte';
  import { promptTitle } from '../../game/promptCopy';
  import type { PromptView } from '../../game/types';

  type Props = {
    prompt: PromptView;
    resolving?: boolean;
    onresolve: (value: unknown) => void;
  };

  let { prompt, resolving = false, onresolve }: Props = $props();
</script>

<PromptPanel
  title={promptTitle(prompt, '相手の番を待っています')}
  warning={!prompt.supported ? (prompt.unsupportedReason ?? 'このプロンプトは高度なリゾルバが必要です。') : undefined}
>
  {#snippet icon()}<PromptIcon name="hourglass" />{/snippet}

  {#snippet actions()}
    <button disabled={resolving} onclick={() => onresolve(null)}>続ける</button>
  {/snippet}
</PromptPanel>
