export type PlayerControl = 'self' | 'agent' | 'codex';

export function validateControls(controls: [PlayerControl, PlayerControl]): string | null {
  const codexCount = controls.filter((control) => control === 'codex').length;
  if (codexCount > 1) {
    return 'Codexは片方のプレイヤーだけに設定してください。';
  }
  if (codexCount === 1 && controls.some((control) => control === 'agent')) {
    return 'Codex対戦のもう一方は「自分」にしてください。';
  }
  return null;
}
