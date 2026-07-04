<script lang="ts">
  // 対戦開始カットイン（表示のみ・操作を奪わない）。素材: 空想曲線 vol.20 text_plate_03
  type Props = { label?: string };
  let { label = '対戦開始' }: Props = $props();
</script>

<div class="cutin" aria-hidden="true">
  <span class="band"><b>{label}</b></span>
</div>

<style>
  .cutin {
    position: fixed;
    inset: 0;
    z-index: 74;
    pointer-events: none;
    display: grid;
    place-items: center;
  }

  .band {
    width: min(620px, 80vw);
    height: 72px;
    background: url('/assets/ui/text_plate_03.png');
    background-size: 100% 100%;
    display: grid;
    place-items: center;
    filter: drop-shadow(0 14px 34px rgba(0, 0, 0, 0.5));
    animation: cutin 1.55s cubic-bezier(0.22, 0.85, 0.3, 1) forwards;
  }

  .band b {
    font-family: 'Zen Kaku Gothic New', 'Noto Sans JP', sans-serif;
    font-weight: 900;
    font-size: 32px;
    letter-spacing: 0.5em;
    text-indent: 0.5em;
    color: #eaf3ff;
    text-shadow: 0 2px 10px rgba(10, 30, 80, 0.55);
  }

  @keyframes cutin {
    0% { transform: translateX(-46vw); opacity: 0; }
    16% { transform: translateX(0); opacity: 1; }
    78% { transform: translateX(0); opacity: 1; }
    100% { transform: translateX(9vw); opacity: 0; }
  }

  @media (prefers-reduced-motion: reduce) {
    .band { animation: cutin-fade 1.55s ease forwards; }
    @keyframes cutin-fade {
      0% { opacity: 0; }
      15% { opacity: 1; }
      80% { opacity: 1; }
      100% { opacity: 0; }
    }
  }
</style>
