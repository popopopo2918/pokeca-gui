import { describe, expect, it, vi } from 'vitest';
import { handleCodexRoute } from './codexRoutes';

function manager() {
  return {
    create: vi.fn().mockResolvedValue({ ok: true, matchId: 'm1' }),
    browserState: vi.fn().mockReturnValue({ ok: true, revision: 2 }),
    browserCommand: vi.fn().mockResolvedValue({ ok: true, revision: 3 }),
    leave: vi.fn().mockReturnValue({ ok: true }),
    agentState: vi.fn().mockReturnValue({ ok: true, status: 'decision' }),
    agentDecision: vi.fn().mockResolvedValue({ ok: false, error: '局面が更新されています。最新の合法手を取得してください。' }),
    browserSaveReplay: vi.fn().mockReturnValue({ ok: true, file: 'replay.json' }),
    summary: vi.fn().mockReturnValue({ ok: true, status: 'finished', replayFile: 'replay.json' }),
  };
}

describe('Codex HTTP route handler', () => {
  it('routes browser match creation and state by client id', async () => {
    const fake = manager();
    const created = await handleCodexRoute({
      method: 'POST',
      pathname: '/local-engine/codex-matches',
      searchParams: new URLSearchParams(),
      clientId: 'browser-1',
      body: { decks: [[], []], codexSeat: 1 },
      connectionCode: '',
    }, fake as never);
    const state = await handleCodexRoute({
      method: 'GET',
      pathname: '/local-engine/codex-matches/m1/state',
      searchParams: new URLSearchParams('since=1'),
      clientId: 'browser-1',
      body: {},
      connectionCode: '',
    }, fake as never);

    expect(created).toEqual({ status: 200, body: { ok: true, matchId: 'm1' } });
    expect(fake.create).toHaveBeenCalledWith('browser-1', expect.objectContaining({ codexSeat: 1 }));
    expect(state?.status).toBe(200);
    expect(fake.browserState).toHaveBeenCalledWith('browser-1', 'm1', 1);
  });

  it('uses only the header connection code for agent routes and maps stale to 409', async () => {
    const fake = manager();
    const result = await handleCodexRoute({
      method: 'POST',
      pathname: '/local-engine/codex-agent/decision',
      searchParams: new URLSearchParams(),
      clientId: 'browser-1',
      body: { decisionId: 'd1', tokens: ['d1-o0'] },
      connectionCode: 'secret-code',
    }, fake as never);

    expect(fake.agentDecision).toHaveBeenCalledWith('secret-code', expect.objectContaining({ decisionId: 'd1' }));
    expect(result?.status).toBe(409);
  });

  it('routes replay saving and finished summary without putting the code in the URL', async () => {
    const fake = manager();
    const saved = await handleCodexRoute({
      method: 'POST',
      pathname: '/local-engine/codex-matches/m1/save-replay',
      searchParams: new URLSearchParams(),
      clientId: 'browser-1',
      body: {},
      connectionCode: '',
    }, fake as never);
    const summary = await handleCodexRoute({
      method: 'GET',
      pathname: '/local-engine/codex-agent/summary',
      searchParams: new URLSearchParams(),
      clientId: 'browser-1',
      body: {},
      connectionCode: 'secret-code',
    }, fake as never);

    expect(saved?.body.file).toBe('replay.json');
    expect(fake.browserSaveReplay).toHaveBeenCalledWith('browser-1', 'm1');
    expect(summary?.body.status).toBe('finished');
    expect(fake.summary).toHaveBeenCalledWith('secret-code');
  });
});
