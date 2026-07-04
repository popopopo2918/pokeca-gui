<script lang="ts">
  // 勝敗リザルト演出。クリックで閉じて盤面を確認できる。素材: 空想曲線 vol.20 テキストプレート
  type Outcome = 'win' | 'lose' | 'draw' | 'neutral';
  type Props = {
    outcome: Outcome;
    label?: string;
    onclose: () => void;
  };
  let { outcome, label = '', onclose }: Props = $props();

  const titles: Record<Outcome, string> = {
    win: '勝利',
    lose: '敗北',
    draw: '引き分け',
    neutral: '対戦終了',
  };
  const plates: Record<Outcome, string> = {
    win: 'text_plate_02',
    lose: 'text_plate_04',
    draw: 'text_plate_01',
    neutral: 'text_plate_01',
  };
</script>

<button type="button" class={`result-overlay ${outcome}`} onclick={onclose} aria-label="結果表示を閉じて盤面を確認">
  <span class="veil"></span>
  <span class="stack">
    <span class="band" style={`background-image:url('/assets/ui/${plates[outcome]}.png')`}>
      <strong class="title">{titles[outcome]}</strong>
    </span>
    {#if label}<span class="sub">{label}</span>{/if}
    <span class="hint">クリックで盤面を確認</span>
  </span>
</button>

<style>
  .result-overlay {
    position: fixed;
    inset: 0;
    z-index: 76;
    display: grid;
    place-items: center;
    border: 0;
    padding: 0;
    background: transparent;
    cursor: pointer;
  }

  .veil {
    position: absolute;
    inset: 0;
    background: radial-gradient(62% 52% at 50% 46%, rgba(9, 12, 17, 0.84), rgba(9, 12, 17, 0.6));
    animation: veil-in 0.35s ease;
  }

  .stack {
    position: relative;
    display: grid;
    justify-items: center;
    gap: 16px;
  }

  .band {
    width: min(680px, 84vw);
    height: 92px;
    background-size: 100% 100%;
    display: grid;
    place-items: center;
    filter: drop-shadow(0 18px 44px rgba(0, 0, 0, 0.55));
    animation: band-in 0.55s cubic-bezier(0.2, 0.9, 0.25, 1);
  }

  .title {
    font-family: 'Zen Kaku Gothic New', 'Noto Sans JP', sans-serif;
    font-weight: 900;
    font-size: 50px;
    letter-spacing: 0.4em;
    text-indent: 0.4em;
    line-height: 1;
    animation: title-in 0.7s cubic-bezier(0.2, 0.9, 0.25, 1);
  }

  .win .title { color: #06252f; text-shadow: 0 1px 0 rgba(255, 255, 255, 0.25); }
  .lose .title { color: #d7dde8; text-shadow: 0 0 14px rgba(120, 130, 150, 0.4); }
  .draw .title,
  .neutral .title { color: #1d232b; }

  .sub {
    font-size: 15px;
    font-weight: 700;
    color: #dbe6f5;
    text-shadow: 0 2px 8px rgba(0, 0, 0, 0.6);
  }

  .hint {
    font-size: 11.5px;
    letter-spacing: 0.14em;
    color: #8fa0b5;
  }

  @keyframes veil-in {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  @keyframes band-in {
    0% { transform: scaleX(0.25); opacity: 0; }
    60% { transform: scaleX(1.04); opacity: 1; }
    100% { transform: scaleX(1); }
  }

  @keyframes title-in {
    0% { letter-spacing: 0.9em; opacity: 0; }
    100% { letter-spacing: 0.4em; opacity: 1; }
  }

  @media (prefers-reduced-motion: reduce) {
    .veil, .band, .title { animation: none; }
  }
</style>
