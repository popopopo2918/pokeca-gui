import { describe, expect, it, vi } from 'vitest';
import { handleCodexSelfPlayRoute } from './codexSelfPlayRoutes';

function manager() {
  return {
    create: vi.fn().mockResolvedValue({ ok: true, matchId: 'm1' }),
    seatState: vi.fn().mockReturnValue({ ok: true, status: 'decision' }),
    seatDecision: vi.fn().mockResolvedValue({ ok: false, error: '局面が更新されています。' }),
    progress: vi.fn().mockReturnValue({ ok: true, decisionCount: 3 }),
    summary: vi.fn().mockReturnValue({ ok: true, status: 'finished' }),
  };
}

function request(
  method: string,
  pathname: string,
  options: { body?: any; seatCode?: string; coordinatorCode?: string } = {},
) {
  return {
    method,
    pathname,
    body: options.body ?? {},
    seatCode: options.seatCode ?? '',
    coordinatorCode: options.coordinatorCode ?? '',
  };
}

describe('Codex self-play HTTP route handler', () => {
  it('自己対戦作成をルーティングする', async () => {
    const fake = manager();
    const body = { decks: [Array(60).fill(1), Array(60).fill(2)], alakazamSeat: 0 };
    const result = await handleCodexSelfPlayRoute(request('POST', '/local-engine/codex-self-play', { body }), fake as never);

    expect(result).toEqual({ status: 200, body: { ok: true, matchId: 'm1' } });
    expect(fake.create).toHaveBeenCalledWith(body);
  });

  it('席コードをURLではなくヘッダー相当値からだけ渡す', async () => {
    const fake = manager();
    const state = await handleCodexSelfPlayRoute(request('GET', '/local-engine/codex-self-play/seat-state', {
      seatCode: 'seat-secret',
    }), fake as never);
    const decision = await handleCodexSelfPlayRoute(request('POST', '/local-engine/codex-self-play/seat-decision', {
      seatCode: 'seat-secret',
      body: { decisionId: 'd1' },
    }), fake as never);

    expect(fake.seatState).toHaveBeenCalledWith('seat-secret');
    expect(fake.seatDecision).toHaveBeenCalledWith('seat-secret', { decisionId: 'd1' });
    expect(state?.status).toBe(200);
    expect(decision?.status).toBe(409);
  });

  it('管理コードで進捗と終了サマリーを取得する', async () => {
    const fake = manager();
    const progress = await handleCodexSelfPlayRoute(request('GET', '/local-engine/codex-self-play/progress', {
      coordinatorCode: 'coordinator-secret',
    }), fake as never);
    const summary = await handleCodexSelfPlayRoute(request('GET', '/local-engine/codex-self-play/summary', {
      coordinatorCode: 'coordinator-secret',
    }), fake as never);

    expect(fake.progress).toHaveBeenCalledWith('coordinator-secret');
    expect(fake.summary).toHaveBeenCalledWith('coordinator-secret');
    expect(progress?.body.decisionCount).toBe(3);
    expect(summary?.body.status).toBe('finished');
  });

  it('未知の自己対戦経路を404にする', async () => {
    const result = await handleCodexSelfPlayRoute(request('GET', '/local-engine/codex-self-play/unknown'), manager() as never);
    expect(result).toEqual({ status: 404, body: { ok: false, error: 'Not found' } });
  });
});
