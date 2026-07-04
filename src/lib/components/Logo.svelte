<script lang="ts">
  // CABT バトルビューアのロゴ（Canvaで選定したA案をSVGで忠実に再構成）。
  // エンブレム＝二重のプレイ三角（観戦・再生）＋ブラケットフレーム（放送画面）。
  type Props = {
    size?: number;
    emblemOnly?: boolean;
  };
  let { size = 34, emblemOnly = false }: Props = $props();
</script>

<span class="logo" style={`--logo-size:${size}px`}>
  <svg viewBox="0 0 48 48" width={size} height={size} aria-hidden="true">
    <defs>
      <linearGradient id="cabt-play" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#3fa2ff" />
        <stop offset="1" stop-color="#1670e0" />
      </linearGradient>
    </defs>
    <!-- 背面フレーム（右） -->
    <path d="M25 13 h13 v22 h-13" fill="none" stroke="url(#cabt-play)" stroke-width="2.4" />
    <!-- ブラケット（左） -->
    <path d="M15 13 h-6 v22 h6" fill="none" stroke="url(#cabt-play)" stroke-width="2.4" />
    <!-- プレイ三角（外） -->
    <path d="M17 9.5 L41 24 L17 38.5 Z" fill="none" stroke="url(#cabt-play)" stroke-width="2.8" stroke-linejoin="round" />
    <!-- プレイ三角（内） -->
    <path d="M23.5 18.5 L33 24 L23.5 29.5 Z" fill="none" stroke="url(#cabt-play)" stroke-width="2.2" stroke-linejoin="round" />
  </svg>
  {#if !emblemOnly}
    <span class="wordmark">
      <b>CABT</b>
      <small>バトルビューア</small>
    </span>
  {/if}
</span>

<style>
  .logo {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    line-height: 1;
    user-select: none;
  }

  svg {
    display: block;
    filter: drop-shadow(0 3px 10px rgba(0, 0, 0, 0.45));
  }

  .wordmark {
    display: grid;
    gap: 3px;
  }

  .wordmark b {
    font-family: 'Zen Kaku Gothic New', 'Noto Sans JP', sans-serif;
    font-weight: 900;
    font-size: calc(var(--logo-size) * 0.6);
    letter-spacing: 0.1em;
    color: var(--text-primary, #edf1f7);
  }

  .wordmark small {
    font-size: calc(var(--logo-size) * 0.26);
    font-weight: 700;
    letter-spacing: 0.3em;
    color: var(--text-secondary, #98a2b3);
  }
</style>
