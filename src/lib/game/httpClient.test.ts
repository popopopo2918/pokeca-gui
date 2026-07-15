import { afterEach, describe, expect, it, vi } from 'vitest';
import { codexMatchApi, hostedAvailableActionsScope } from './httpClient';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('Codex match HTTP client', () => {
  it('creates a Codex match without putting credentials in the URL', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ok: true,
      matchId: 'm1',
      connectionCode: 'secret-code',
    })));
    vi.stubGlobal('fetch', fetchMock);

    await codexMatchApi.create([Array(60).fill('1'), Array(60).fill('2')], 1);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/local-engine/codex-matches');
    expect((init.headers as Record<string, string>)['x-cabt-client']).toBeTruthy();
    expect(String(url)).not.toContain('secret-code');
  });
});

describe('hosted headless requests', () => {
  it('skips legality dry-runs for latency-sensitive mutation responses', () => {
    expect(hostedAvailableActionsScope({ type: 'playCard' })).toBe('none');
    expect(hostedAvailableActionsScope({ type: 'resolvePrompt' })).toBe('none');
    expect(hostedAvailableActionsScope({ type: 'attack' })).toBe('none');
    expect(hostedAvailableActionsScope({ type: 'retreat' })).toBe('none');
  });

  it('keeps default active-player legality for initial and explicit state requests', () => {
    expect(hostedAvailableActionsScope({ type: 'newGame' })).toBeUndefined();
    expect(hostedAvailableActionsScope({ type: 'state' })).toBeUndefined();
    expect(hostedAvailableActionsScope({ type: 'passTurn' })).toBeUndefined();
  });

  it('allows callers to opt back into scoped legality', () => {
    expect(hostedAvailableActionsScope({ type: 'playCard', availableActionsScope: 'active' })).toBe('active');
    expect(hostedAvailableActionsScope({ type: 'state', availableActionsScope: 'full' })).toBe('full');
  });
});
