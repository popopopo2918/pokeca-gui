type SelfPlayRouteRequest = {
  method: string;
  pathname: string;
  body: any;
  seatCode: string;
  coordinatorCode: string;
};

type SelfPlayRouteManager = {
  create(body: any): Promise<Record<string, any>>;
  seatState(code: string): Record<string, any>;
  seatDecision(code: string, body: any): Promise<Record<string, any>>;
  seatConcede(code: string, rationale: unknown): Promise<Record<string, any>>;
  progress(code: string): Record<string, any>;
  summary(code: string): Record<string, any>;
};

export type SelfPlayRouteResult = {
  status: number;
  body: Record<string, any>;
};

function statusFor(body: Record<string, any>): number {
  if (body.ok) return 200;
  const error = String(body.error ?? '');
  if (error.includes('コードが無効') || error.includes('期限切れ')) return 404;
  if (body.status === 'in-progress'
    || error.includes('局面が更新')
    || error.includes('手番ではありません')) return 409;
  return 400;
}

export async function handleCodexSelfPlayRoute(
  request: SelfPlayRouteRequest,
  manager: SelfPlayRouteManager,
): Promise<SelfPlayRouteResult | null> {
  if (request.pathname === '/local-engine/codex-self-play' && request.method === 'POST') {
    const body = await manager.create(request.body);
    return { status: statusFor(body), body };
  }
  if (request.pathname === '/local-engine/codex-self-play/seat-state' && request.method === 'GET') {
    const body = manager.seatState(request.seatCode);
    return { status: statusFor(body), body };
  }
  if (request.pathname === '/local-engine/codex-self-play/seat-decision' && request.method === 'POST') {
    const body = await manager.seatDecision(request.seatCode, request.body);
    return { status: statusFor(body), body };
  }
  if (request.pathname === '/local-engine/codex-self-play/seat-concede' && request.method === 'POST') {
    const body = await manager.seatConcede(request.seatCode, request.body?.rationale);
    return { status: statusFor(body), body };
  }
  if (request.pathname === '/local-engine/codex-self-play/progress' && request.method === 'GET') {
    const body = manager.progress(request.coordinatorCode);
    return { status: statusFor(body), body };
  }
  if (request.pathname === '/local-engine/codex-self-play/summary' && request.method === 'GET') {
    const body = manager.summary(request.coordinatorCode);
    return { status: statusFor(body), body };
  }
  if (request.pathname.startsWith('/local-engine/codex-self-play')) {
    return { status: 404, body: { ok: false, error: 'Not found' } };
  }
  return null;
}
