<script lang="ts">
  // CABT バトルビューアのロゴ。エンブレム＝交差する2枚のカード（対戦）＋
  // 金の「オンエア」ドット（観戦・放送）。テキスト無し（emblemOnly）でも使える。
  type Props = {
    size?: number;
    emblemOnly?: boolean;
  };
  let { size = 34, emblemOnly = false }: Props = $props();
</script>

<span class="logo" style={`--logo-size:${size}px`}>
  <svg viewBox="0 0 48 48" width={size} height={size} aria-hidden="true">
    <defs>
      <linearGradient id="cabt-card" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#5d99ff" />
        <stop offset="1" stop-color="#3566d9" />
      </linearGradient>
    </defs>
    <!-- 後ろのカード（金の輪郭） -->
    <g transform="rotate(12 29 24)">
      <rect x="19" y="9" width="20" height="29" rx="3.2" fill="none" stroke="#d9a441" stroke-width="2.4" />
    </g>
    <!-- 前のカード（ブルー） -->
    <g transform="rotate(-9 19 25)">
      <rect x="8" y="10" width="20" height="29" rx="3.2" fill="url(#cabt-card)" stroke="rgba(255,255,255,0.85)" stroke-width="1.5" />
      <rect x="11" y="14" width="14" height="9" rx="1.6" fill="rgba(255,255,255,0.28)" />
      <rect x="11" y="26" width="10" height="2.4" rx="1.2" fill="rgba(255,255,255,0.4)" />
      <rect x="11" y="30.5" width="12" height="2.4" rx="1.2" fill="rgba(255,255,255,0.22)" />
    </g>
    <!-- オンエアドット -->
    <circle cx="41" cy="8.5" r="3" fill="#d9a441" />
    <circle cx="41" cy="8.5" r="5.6" fill="none" stroke="#d9a441" stroke-width="1.2" opacity="0.45" />
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
    font-family: 'Barlow Condensed', 'Noto Sans JP', sans-serif;
    font-weight: 700;
    font-size: calc(var(--logo-size) * 0.62);
    letter-spacing: 0.22em;
    color: var(--text-primary, #edf1f7);
  }

  .wordmark small {
    font-size: calc(var(--logo-size) * 0.28);
    font-weight: 700;
    letter-spacing: 0.34em;
    color: var(--text-secondary, #98a2b3);
  }
</style>
