<script lang="ts">
  import { cardPreviewStore } from '../../state/cardPreview.svelte';
  import { japaneseCardName } from '../cabt/logFormat';

  let card = $derived(cardPreviewStore.hovered);
  let failed = $state('');
  let imageUrl = $derived(card?.imageUrl);
  let showImage = $derived(!!imageUrl && failed !== imageUrl);
  // Prefer the Japanese card name (resolved by id) over the English CardView name.
  let label = $derived(
    (card?.id ? japaneseCardName(card.id) : '') || card?.fullName || card?.name || '',
  );
</script>

{#if card}
  <div class="card-zoom" aria-hidden="true">
    {#if showImage}
      <img src={imageUrl} alt="" onerror={() => (failed = imageUrl ?? '')} />
    {:else}
      <div class="fallback">
        <span class="name">{label}</span>
        {#if card.set}<span class="set">{card.set} {card.setNumber}</span>{/if}
      </div>
    {/if}
    {#if label}<span class="caption">{label}</span>{/if}
  </div>
{/if}

<style>
  .card-zoom {
    position: fixed;
    top: 52px;
    left: 16px;
    z-index: 28;
    width: clamp(160px, 17vw, 260px);
    padding: 8px;
    border-radius: var(--radius-lg);
    background: var(--surface-glass-bg);
    border: 1px solid var(--surface-glass-border);
    box-shadow: var(--surface-glass-shadow);
    backdrop-filter: blur(var(--backdrop-blur));
    pointer-events: none;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .card-zoom img {
    width: 100%;
    border-radius: var(--radius-md);
    display: block;
  }
  .fallback {
    aspect-ratio: 63 / 88;
    border-radius: var(--radius-md);
    background: var(--surface-inset-bg);
    border: 1px solid var(--surface-inset-border);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 12px;
    text-align: center;
  }
  .fallback .name { font-size: 14px; font-weight: 700; color: var(--text-primary); }
  .fallback .set { font-size: 12px; color: var(--text-muted); }
  .caption {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
    text-align: center;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
</style>
