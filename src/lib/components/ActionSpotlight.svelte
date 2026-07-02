<script lang="ts">
  import cardRows from '../cabt/cardData.generated.json';
  import { japaneseCardName } from '../cabt/logFormat';
  import { CabtAreaType } from '../cabt/types';
  import { resolveCardImageUrl } from '../game/cardImages';
  import type { ActionTimelineEvent } from '../game/types';

  type Props = {
    timeline?: ActionTimelineEvent[];
    // How long the spotlight stays up after an action. Tied to the playback step delay so it
    // lingers roughly as long as the frame is shown.
    holdMs?: number;
  };

  let { timeline = [], holdMs = 1600 }: Props = $props();

  // Actions worth spotlighting (each carries a cardId so we can show the card art).
  const SPOTLIGHT_KINDS = new Set([
    'ability', 'Play', 'Attach', 'Attack', 'Evolve',
    'Devolve', 'MoveAttached', 'MoveCard', 'HPChange',
    'Poisoned', 'Burned', 'Asleep', 'Paralyzed', 'Confused',
  ]);
  const KIND_LABEL: Record<string, string> = {
    ability: '特性',
    Play: '発動',
    Attack: 'ワザ',
    Evolve: '進化',
    Devolve: '退化',
    MoveAttached: 'つけ替え',
  };
  const CONDITION_LABEL: Record<string, string> = {
    Poisoned: 'どく',
    Burned: 'やけど',
    Asleep: 'ねむり',
    Paralyzed: 'まひ',
    Confused: 'こんらん',
  };
  const AREA_LABEL: Record<number, string> = {
    [CabtAreaType.HAND]: '手札へ',
    [CabtAreaType.DISCARD]: 'トラッシュ',
    [CabtAreaType.DECK]: '山札へ',
    [CabtAreaType.PRIZE]: 'サイドへ',
    [CabtAreaType.BENCH]: 'ベンチへ',
    [CabtAreaType.ACTIVE]: 'バトル場へ',
  };
  // cardType 5/6 are energy cards in the generated card data.
  const ENERGY_CARD_TYPES = new Set([5, 6]);

  const cardById = new Map<number, { set?: string; setNumber?: string; name?: string; cardType?: number }>();
  for (const row of cardRows as Array<{ id: number; set?: string; setNumber?: string; name?: string; cardType?: number }>) {
    if (!cardById.has(row.id)) {
      cardById.set(row.id, row);
    }
  }

  function cardIdOf(event: ActionTimelineEvent | undefined): number | undefined {
    const params = event?.params as { cardId?: unknown } | undefined;
    const id = Number(params?.cardId);
    return Number.isFinite(id) && id > 0 ? id : undefined;
  }

  let latest = $derived.by(() => {
    for (let index = timeline.length - 1; index >= 0; index -= 1) {
      const event = timeline[index];
      if (event.kind && SPOTLIGHT_KINDS.has(event.kind) && cardIdOf(event) !== undefined) {
        return event;
      }
    }
    return undefined;
  });

  let shownId = $state<number | undefined>(undefined);
  let visible = $state(false);
  let current = $state<ActionTimelineEvent | undefined>(undefined);
  let timer: ReturnType<typeof setTimeout> | undefined;

  $effect(() => {
    const event = latest;
    if (event && event.id !== shownId) {
      shownId = event.id;
      current = event;
      visible = true;
      clearTimeout(timer);
      timer = setTimeout(() => {
        visible = false;
      }, holdMs);
    }
    return () => clearTimeout(timer);
  });

  let cardId = $derived(cardIdOf(current));
  let cardName = $derived(cardId ? japaneseCardName(cardId) : '');
  let imageUrl = $derived(cardId ? resolveCardImageUrl({ id: cardId, ...(cardById.get(cardId) ?? {}) }) : undefined);
  let kindLabel = $derived.by(() => {
    const kind = current?.kind;
    if (!kind) {
      return '発動';
    }
    const params = (current?.params ?? {}) as { value?: unknown; isRecover?: unknown; toArea?: unknown };
    if (kind === 'Attach') {
      const cardType = cardId ? cardById.get(cardId)?.cardType : undefined;
      return cardType !== undefined && ENERGY_CARD_TYPES.has(cardType) ? 'エネ付与' : 'どうぐ';
    }
    if (kind === 'Play') {
      // A Pokémon "Play" is placing it into play; trainers/items are "used".
      return (cardId ? cardById.get(cardId)?.cardType : undefined) === 0 ? '登場' : '発動';
    }
    if (kind === 'MoveCard') {
      return AREA_LABEL[Number(params.toArea)] ?? 'カード移動';
    }
    if (kind === 'HPChange') {
      const value = Number(params.value);
      if (Number.isFinite(value) && value < 0) {
        return 'ダメージ';
      }
      if (Number.isFinite(value) && value > 0) {
        return '回復';
      }
      return 'HP変化';
    }
    if (CONDITION_LABEL[kind]) {
      return params.isRecover ? `${CONDITION_LABEL[kind]}回復` : CONDITION_LABEL[kind];
    }
    return KIND_LABEL[kind] ?? '発動';
  });
  let actorLabel = $derived(current?.playerIndex === undefined ? '' : `プレイヤー${current.playerIndex + 1}`);

  function hideImage(event: Event) {
    (event.currentTarget as HTMLImageElement).style.display = 'none';
  }
</script>

{#if visible && current}
  {#key current.id}
    <div class="action-spotlight" role="status" aria-live="polite">
      {#if imageUrl}
        <img class="spot-card" src={imageUrl} alt={cardName} loading="eager" onerror={hideImage} />
      {/if}
      <div class="spot-text">
        <span class="spot-kind">{kindLabel}</span>
        {#if actorLabel}<span class="spot-actor">{actorLabel}</span>{/if}
        <strong class="spot-name">{cardName}</strong>
        {#if current.message}<span class="spot-message">{current.message}</span>{/if}
      </div>
    </div>
  {/key}
{/if}

<style>
  .action-spotlight {
    position: fixed;
    top: 64px;
    left: 16px;
    z-index: 30;
    display: flex;
    align-items: center;
    gap: 14px;
    max-width: min(92vw, 460px);
    padding: 12px 16px;
    border-radius: 16px;
    border: 1px solid var(--button-border);
    background: var(--surface-glass-bg);
    box-shadow: var(--surface-toolbar-shadow);
    backdrop-filter: blur(var(--backdrop-blur));
    pointer-events: none;
    animation: spotlight-pop 220ms ease-out;
  }

  .spot-card {
    width: 92px;
    height: auto;
    border-radius: 8px;
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.35);
    animation: spotlight-card 260ms ease-out;
  }

  .spot-text {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }

  .spot-kind {
    align-self: flex-start;
    padding: 2px 10px;
    border-radius: 999px;
    background: var(--button-primary-bg);
    color: var(--button-primary-text);
    font-size: 11px;
    font-weight: 900;
    letter-spacing: 0.06em;
  }

  .spot-actor {
    color: var(--text-secondary);
    font-size: 11px;
    font-weight: 700;
  }

  .spot-name {
    color: var(--text-primary);
    font-size: 17px;
    font-weight: 900;
    line-height: 1.2;
  }

  .spot-message {
    color: var(--text-secondary);
    font-size: 12px;
    overflow-wrap: anywhere;
  }

  @keyframes spotlight-pop {
    from { opacity: 0; transform: translateY(-8px); }
    to { opacity: 1; transform: translateY(0); }
  }

  @keyframes spotlight-card {
    from { opacity: 0; transform: scale(0.82) rotate(-3deg); }
    to { opacity: 1; transform: scale(1) rotate(0); }
  }

  @media (prefers-reduced-motion: reduce) {
    .action-spotlight,
    .spot-card {
      animation: none;
    }
  }
</style>
