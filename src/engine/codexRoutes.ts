type CodexRouteRequest = {
  method: string;
  pathname: string;
  searchParams: URLSearchParams;
  clientId: string;
  body: any;
  connectionCode: string;
};

type CodexRouteManager = {
  create(clientId: string, body: any): Promise<Record<string, any>>;
  browserState(clientId: string, matchId: string, since: number): Record<string, any>;
  browserCommand(clientId: string, matchId: string, body: any): Promise<Record<string, any>>;
  leave(clientId: string, matchId: string): Record<string, any>;
  agentState(connectionCode: string): Record<string, any>;
  agentDecision(connectionCode: string, body: any): Promise<Record<string, any>>;
  browserSaveReplay(clientId: string, matchId: string): Record<string, any>;
  summary(connectionCode: string): Record<string, any>;
};

export type CodexRouteResult = {
  status: number;
  body: Record<string, any>;
};

function statusFor(body: Record<string, any>, agent = false): number {
  if (body.ok) return 200;
  const error = String(body.error ?? '');
  if (agent && error.includes('接続コード')) return 404;
  if (error.includes('見つからない') || error.includes('参加者では')) return 404;
  if (error.includes('局面が更新') || error.includes('手番') || error.includes('操作待ち')) return 409;
  return 400;
}

export async function handleCodexRoute(
  request: CodexRouteRequest,
  manager: CodexRouteManager,
): Promise<CodexRouteResult | null> {
  if (request.pathname === '/local-engine/codex-matches' && request.method === 'POST') {
    const body = await manager.create(request.clientId, request.body);
    return { status: statusFor(body), body };
  }

  const browserMatch = request.pathname.match(/^\/local-engine\/codex-matches\/([^/]+)\/(state|command|leave|save-replay)$/);
  if (browserMatch) {
    const matchId = decodeURIComponent(browserMatch[1]);
    const action = browserMatch[2];
    if (action === 'state' && request.method === 'GET') {
      const since = Number(request.searchParams.get('since') ?? 0) || 0;
      const body = manager.browserState(request.clientId, matchId, since);
      return { status: statusFor(body), body };
    }
    if (action === 'command' && request.method === 'POST') {
      const body = await manager.browserCommand(request.clientId, matchId, request.body);
      return { status: statusFor(body), body };
    }
    if (action === 'leave' && request.method === 'POST') {
      const body = manager.leave(request.clientId, matchId);
      return { status: statusFor(body), body };
    }
    if (action === 'save-replay' && request.method === 'POST') {
      const body = manager.browserSaveReplay(request.clientId, matchId);
      return { status: statusFor(body), body };
    }
    return { status: 405, body: { ok: false, error: 'Method not allowed' } };
  }

  if (request.pathname === '/local-engine/codex-agent/state' && request.method === 'GET') {
    const body = manager.agentState(request.connectionCode);
    return { status: statusFor(body, true), body };
  }
  if (request.pathname === '/local-engine/codex-agent/decision' && request.method === 'POST') {
    const body = await manager.agentDecision(request.connectionCode, request.body);
    return { status: statusFor(body, true), body };
  }
  if (request.pathname === '/local-engine/codex-agent/summary' && request.method === 'GET') {
    const body = manager.summary(request.connectionCode);
    return { status: statusFor(body, true), body };
  }
  if (request.pathname.startsWith('/local-engine/codex-matches')
    || request.pathname.startsWith('/local-engine/codex-agent')) {
    return { status: 404, body: { ok: false, error: 'Not found' } };
  }
  return null;
}
