<script lang="ts">
  import { resolveCardImageUrl } from '../game/cardImages';
  import type { ActionTimelineEvent } from '../game/types';

  // When the viewer draws a card, show it briefly falling in from the top toward the hand, so it is
  // clear a card was added. Only the viewer's own draws carry a cardId ('Draw'); the opponent's are
  // hidden ('DrawReverse'), so nothing leaks.
  type Props = {
    timeline?: ActionTimelineEvent[];
    selfIndex?: number;
    holdMs?: number;
  };

  let { timeline = [], selfIndex, holdMs = 700 }: Props = $props();

  function cardIdOf(event: ActionTimelineEvent | undefined): number | undefined {
    const id = Number((event?.params as { cardId?: unknown } | undefined)?.cardId);
    return Number.isFinite(id) && id > 0 ? id : undefined;
  }

  let latest = $derived.by(() => {
    for (let index = timeline.length - 1; index >= 0; index -= 1) {
      const event = timeline[index];
      if (
        event.kind === 'Draw'
        && cardIdOf(event) !== undefined
        && (selfIndex === undefined || event.playerIndex === selfIndex)
      ) {
        return event;
      }
    }
    return undefined;
  });

  let shownId = $state(-1);
  let visible = $state(false);
  let imageUrl = $state<string | undefined>(undefined);
  let timer: ReturnType<typeof setTimeout> | undefined;

  $effect(() => {
    const event = latest;
    if (event && event.id !== shownId) {
      shownId = event.id;
      imageUrl = resolveCardImageUrl({ id: cardIdOf(event) });
      visible = true;
      clearTimeout(timer);
      timer = setTimeout(() => {
        visible = false;
      }, holdMs);
    }
    return () => clearTimeout(timer);
  });

  function hide(event: Event) {
    (event.currentTarget as HTMLImageElement).style.display = 'none';
  }
</script>

{#if visible && imageUrl}
  {#key shownId}
    <img class="draw-fly-in" src={imageUrl} alt="" onerror={hide} />
  {/key}
{/if}

<style>
  .draw-fly-in {
    position: fixed;
    left: 50%;
    bottom: 12%;
    width: clamp(90px, 9vw, 140px);
    border-radius: 8px;
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.45);
    z-index: 36;
    pointer-events: none;
    animation: draw-fly-in 700ms ease-out forwards;
  }

  /* Fall in from the top and fade, settling toward the hand at the bottom. */
  @keyframes draw-fly-in {
    0% { opacity: 0; transform: translate(-50%, -46vh) scale(0.82); }
    35% { opacity: 1; }
    80% { opacity: 1; transform: translate(-50%, 0) scale(1); }
    100% { opacity: 0; transform: translate(-50%, 6px) scale(1); }
  }

  @media (prefers-reduced-motion: reduce) {
    .draw-fly-in { animation: draw-fly-in-reduced 500ms ease-out forwards; }
    @keyframes draw-fly-in-reduced {
      0% { opacity: 0; }
      30% { opacity: 1; transform: translate(-50%, 0); }
      100% { opacity: 0; transform: translate(-50%, 0); }
    }
  }
</style>
