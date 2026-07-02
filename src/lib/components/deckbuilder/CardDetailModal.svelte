<script lang="ts">
  import type { CatalogCard } from '../../cards/cardCatalog';

  type Props = {
    card: CatalogCard;
    count?: number;
    onadd?: () => void;
    onremove?: () => void;
    onclose?: () => void;
  };
  let { card, count = 0, onadd, onremove, onclose }: Props = $props();

  let failed = $state(false);
  let src = $derived(failed || !card.imageUrl ? '/assets/cardback.png' : card.imageUrl);
  let atLimit = $derived(count >= card.copyLimit);

  function onKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') onclose?.();
  }
</script>

<svelte:window onkeydown={onKeydown} />

<div class="backdrop" onclick={onclose} onkeydown={onKeydown} role="presentation">
  <div
    class="modal"
    onclick={(e) => e.stopPropagation()}
    onkeydown={onKeydown}
    role="dialog"
    aria-modal="true"
    aria-label={card.nameJa}
    tabindex="-1"
  >
    <button class="close" onclick={onclose} aria-label="閉じる">×</button>
    <div class="art">
      <img {src} alt={card.nameJa} onerror={() => (failed = true)} />
    </div>
    <div class="info">
      <header>
        <h2>{card.nameJa}</h2>
        <p class="en">{card.name}</p>
        <p class="line">
          <span class="chip">{card.subtypeJa}</span>
          {#if card.typeIcon}<img class="ti" src={card.typeIcon} alt={card.typeLabel ?? ''} />{/if}
          {#if card.hp}<span class="chip">HP {card.hp}</span>{/if}
          <span class="chip subtle">{card.set} {card.setNumber}</span>
        </p>
        {#if card.ruleJa}<p class="rule">{card.ruleJa}</p>{/if}
        {#if card.evolvesFrom}<p class="evo">進化元：{card.evolvesFrom}</p>{/if}
      </header>

      {#if card.abilities.length}
        <section>
          <h3>特性 / Ability</h3>
          {#each card.abilities as ability}
            <div class="block">
              <strong>{ability.name.trim()}</strong>
              <p>{ability.text}</p>
            </div>
          {/each}
        </section>
      {/if}

      {#if card.movesJa.length}
        <section>
          <h3>ワザ / 効果</h3>
          {#each card.movesJa as move}
            <div class="block">
              <div class="move-head">
                <strong>{move.name}</strong>
                {#if move.cost}<span class="cost">{move.cost}</span>{/if}
                {#if move.damage}<span class="dmg">{move.damage}</span>{/if}
              </div>
              {#if move.effect}<p>{move.effect}</p>{/if}
            </div>
          {/each}
        </section>
      {/if}

      <section class="stats">
        <span>にげる：{card.retreat}</span>
        <span>同名上限：{card.copyLimit >= 60 ? '無制限' : `${card.copyLimit}枚`}</span>
        <span>ID：{card.id}</span>
      </section>

      <footer>
        <button class="mini" onclick={onremove} disabled={count <= 0}>− 減らす</button>
        <span class="count">{count} 枚</span>
        <button class="mini primary" onclick={onadd} disabled={atLimit}>＋ デッキに追加</button>
      </footer>
    </div>
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
    display: grid;
    grid-template-columns: minmax(220px, 300px) minmax(0, 1fr);
    gap: 20px;
    max-width: 760px;
    width: 100%;
    max-height: 88vh;
    padding: 22px;
    border-radius: var(--radius-lg);
    background: var(--surface-glass-bg);
    border: 1px solid var(--surface-glass-border);
    box-shadow: var(--surface-glass-shadow);
    overflow: hidden;
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
  .art img {
    width: 100%;
    border-radius: var(--radius-md);
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.24);
  }
  .info {
    overflow-y: auto;
    padding-right: 4px;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  h2 { margin: 0; font-size: 20px; color: var(--text-primary); }
  .en { margin: 1px 0 0; font-size: 13px; color: var(--text-muted); }
  .line { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin: 8px 0 0; }
  .chip {
    padding: 2px 8px;
    border-radius: var(--radius-pill);
    background: var(--accent-tint);
    color: var(--accent-strong);
    font-size: 12px;
    font-weight: 600;
  }
  .chip.subtle { background: var(--surface-inset-bg); color: var(--text-secondary); }
  .ti { width: 18px; height: 18px; }
  .rule { margin: 8px 0 0; font-size: 12px; font-weight: 700; color: var(--warning-text); }
  .evo { margin: 4px 0 0; font-size: 12px; color: var(--text-secondary); }
  section h3 {
    margin: 0 0 6px;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
  }
  .block { margin-bottom: 8px; }
  .block strong { font-size: 14px; color: var(--text-primary); }
  .block p { margin: 3px 0 0; font-size: 13px; line-height: 1.55; color: var(--text-secondary); white-space: pre-wrap; }
  .move-head { display: flex; align-items: baseline; gap: 8px; }
  .cost { font-size: 12px; color: var(--accent-strong); font-weight: 700; }
  .dmg { margin-left: auto; font-size: 15px; font-weight: 800; color: var(--text-primary); }
  .stats { display: flex; gap: 14px; flex-wrap: wrap; font-size: 12px; color: var(--text-muted); }
  footer { display: flex; align-items: center; gap: 10px; margin-top: 4px; }
  .count { font-weight: 700; color: var(--text-secondary); }
  .mini {
    padding: 7px 12px;
    border: 1px solid var(--button-border);
    border-radius: var(--radius-sm);
    background: var(--button-bg);
    color: var(--button-text);
    font-size: 13px;
    cursor: pointer;
  }
  .mini.primary {
    margin-left: auto;
    background: var(--button-primary-bg);
    border-color: var(--button-primary-border);
    color: var(--button-primary-text);
  }
  .mini:disabled { opacity: var(--disabled-opacity); cursor: not-allowed; }
  @media (max-width: 640px) {
    .modal { grid-template-columns: 1fr; }
  }
</style>
