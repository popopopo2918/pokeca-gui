import { describe, expect, it } from 'vitest';
import { validateControls } from './controlMode';

describe('Codex controls', () => {
  it('allows exactly one Codex seat against a human', () => {
    expect(validateControls(['self', 'codex'])).toBeNull();
    expect(validateControls(['codex', 'self'])).toBeNull();
  });

  it('rejects two Codex seats and uploaded AI mixed with Codex', () => {
    expect(validateControls(['codex', 'codex'])).toBe('Codexは片方のプレイヤーだけに設定してください。');
    expect(validateControls(['agent', 'codex'])).toBe('Codex対戦のもう一方は「自分」にしてください。');
  });
});
