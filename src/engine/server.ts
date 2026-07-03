import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { LocalEngineController, GAME_LOGS_DIR } from './localEngine';
import { importOfficialDeckCode } from './officialDeck';
import { createRoom, joinRoom, leaveRoom, roomCommand, roomState } from './rooms';
import { WORKSPACES_DIR } from './workspaces';
import { dataSyncEnabled, pullAll } from './dataStore';

const port = Number(process.env.PORT ?? process.env.LOCAL_ENGINE_PORT ?? 8095);
const host = process.env.LOCAL_ENGINE_HOST ?? (process.env.PORT ? '0.0.0.0' : '127.0.0.1');

// Serve the built front-end (dist/) so a single process can host both the app and the
// API. Used for the cloud deployment; local dev still uses the Vite dev server + proxy.
const DIST_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'dist');
const MIME: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
  '.woff': 'font/woff',
  '.txt': 'text/plain; charset=utf-8',
  '.csv': 'text/csv; charset=utf-8',
};

function serveStatic(res: http.ServerResponse, pathname: string): void {
  if (!fs.existsSync(DIST_DIR)) {
    writeJson(res, 404, { ok: false, error: 'Static build not found. Run `npm run build`.' });
    return;
  }
  const rel = decodeURIComponent(pathname).replace(/^\/+/, '');
  let filePath = path.join(DIST_DIR, rel);
  if (!filePath.startsWith(DIST_DIR)) {
    writeJson(res, 403, { ok: false, error: 'Forbidden' });
    return;
  }
  if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
    filePath = path.join(DIST_DIR, 'index.html');
  }
  fs.readFile(filePath, (err, data) => {
    if (err) {
      writeJson(res, 404, { ok: false, error: 'Not found' });
      return;
    }
    const type = MIME[path.extname(filePath).toLowerCase()] ?? 'application/octet-stream';
    res.writeHead(200, { 'Content-Type': type, 'Content-Length': data.length });
    res.end(data);
  });
}

// One isolated engine (and Python bridge) per browser client, so several people can
// play at the same time over a shared URL without clashing on a single session.
// Each controller holds a Python engine process (~100MB+), so idle ones must be
// reaped even when no new client ever connects — leaked engines eventually exhaust
// memory and every later process spawn fails with 0xC0000142.
const controllers = new Map<string, { controller: LocalEngineController; lastUsed: number }>();
const MAX_CONTROLLERS = 8;
const IDLE_MS = 30 * 60 * 1000;
setInterval(pruneControllers, 5 * 60 * 1000).unref();

function clientIdOf(req: http.IncomingMessage): string {
  const raw = req.headers['x-cabt-client'];
  const id = Array.isArray(raw) ? raw[0] : raw;
  return (id && id.trim()) || 'default';
}

function controllerFor(req: http.IncomingMessage): LocalEngineController {
  const clientId = clientIdOf(req);
  let entry = controllers.get(clientId);
  if (!entry) {
    pruneControllers();
    entry = { controller: new LocalEngineController(), lastUsed: Date.now() };
    controllers.set(clientId, entry);
  }
  entry.lastUsed = Date.now();
  return entry.controller;
}

function pruneControllers(): void {
  const now = Date.now();
  for (const [id, entry] of controllers) {
    if (now - entry.lastUsed > IDLE_MS) {
      entry.controller.close();
      controllers.delete(id);
    }
  }
  while (controllers.size >= MAX_CONTROLLERS) {
    let oldestId = '';
    let oldest = Infinity;
    for (const [id, entry] of controllers) {
      if (entry.lastUsed < oldest) {
        oldest = entry.lastUsed;
        oldestId = id;
      }
    }
    if (!oldestId) break;
    controllers.get(oldestId)?.controller.close();
    controllers.delete(oldestId);
  }
}

function readBody(req: http.IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    let body = '';
    req.setEncoding('utf8');
    req.on('data', (chunk) => {
      body += chunk;
      if (body.length > 1_000_000) {
        reject(new Error('Request body too large'));
        req.destroy();
      }
    });
    req.on('end', () => resolve(body));
    req.on('error', reject);
  });
}

function writeJson(res: http.ServerResponse, status: number, body: unknown): void {
  const json = JSON.stringify(body);
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(json),
  });
  res.end(json);
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url ?? '/', 'http://localhost');

  // Saved replays/logs are served from the writable runtime dir (not the build), so
  // auto-saved matches show up in the replay viewer in the cloud deployment.
  if (url.pathname.startsWith('/game-logs/') && (req.method === 'GET' || req.method === 'HEAD')) {
    const rel = decodeURIComponent(url.pathname.slice('/game-logs/'.length)).replace(/^\/+/, '');
    const filePath = path.join(GAME_LOGS_DIR, rel);
    if (!filePath.startsWith(GAME_LOGS_DIR)) {
      writeJson(res, 403, { ok: false, error: 'Forbidden' });
      return;
    }
    fs.readFile(filePath, (err, data) => {
      if (err) {
        writeJson(res, 404, { ok: false, error: 'Not found' });
        return;
      }
      res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': data.length });
      res.end(data);
    });
    return;
  }

  // Everything that is not the engine API is the static front-end (SPA).
  if (!url.pathname.startsWith('/local-engine')) {
    if (req.method === 'GET' || req.method === 'HEAD') {
      serveStatic(res, url.pathname);
    } else {
      writeJson(res, 404, { ok: false, error: 'Not found' });
    }
    return;
  }

  if (req.method === 'GET' && url.pathname === '/local-engine/health') {
    writeJson(res, 200, { ok: true });
    return;
  }

  const controller = controllerFor(req);

  if (req.method === 'GET' && url.pathname === '/local-engine/replays') {
    writeJson(res, 200, controller.listReplays());
    return;
  }

  if (req.method === 'GET' && url.pathname.startsWith('/local-engine/replays/')) {
    const id = decodeURIComponent(url.pathname.slice('/local-engine/replays/'.length));
    const response = controller.loadReplay(id);
    writeJson(res, response.ok ? 200 : 404, response);
    return;
  }

  if (req.method === 'POST' && url.pathname === '/local-engine/replays/load') {
    try {
      const raw = await readBody(req);
      const body = raw ? JSON.parse(raw) : {};
      const response = controller.loadReplayData(body.replayData, body.name);
      writeJson(res, response.ok ? 200 : 400, response);
    } catch (error) {
      writeJson(res, 400, {
        ok: false,
        error: error instanceof Error ? error.message : String(error),
      });
    }
    return;
  }

  if (req.method === 'POST' && url.pathname === '/local-engine/save-replay') {
    const response = controller.saveReplay();
    writeJson(res, response.ok ? 200 : 400, response);
    return;
  }

  // ---- 遠隔対戦ルーム ----
  if (url.pathname.startsWith('/local-engine/rooms')) {
    const clientId = clientIdOf(req);
    try {
      if (req.method === 'POST' && url.pathname === '/local-engine/rooms') {
        const body = JSON.parse((await readBody(req)) || '{}');
        writeJson(res, 200, createRoom(clientId, body.deck));
        return;
      }
      const match = url.pathname.match(/^\/local-engine\/rooms\/([A-Za-z0-9]+)\/(join|state|command|leave)$/);
      if (match) {
        const [, roomCode, action] = match;
        if (action === 'state' && req.method === 'GET') {
          const since = Number(url.searchParams.get('since') ?? 0) || 0;
          writeJson(res, 200, roomState(clientId, roomCode, since));
          return;
        }
        const body = JSON.parse((await readBody(req)) || '{}');
        if (action === 'join' && req.method === 'POST') {
          writeJson(res, 200, await joinRoom(clientId, roomCode, body.deck));
          return;
        }
        if (action === 'command' && req.method === 'POST') {
          const response = await roomCommand(clientId, roomCode, body);
          writeJson(res, response.ok ? 200 : 400, response);
          return;
        }
        if (action === 'leave' && req.method === 'POST') {
          writeJson(res, 200, leaveRoom(clientId, roomCode));
          return;
        }
      }
      writeJson(res, 404, { ok: false, error: 'Not found' });
    } catch (error) {
      writeJson(res, 400, { ok: false, error: error instanceof Error ? error.message : String(error) });
    }
    return;
  }

  if (req.method === 'GET' && url.pathname.startsWith('/local-engine/deck-code/')) {
    const code = decodeURIComponent(url.pathname.slice('/local-engine/deck-code/'.length)).replace(/\/+$/, '');
    const result = await importOfficialDeckCode(code);
    writeJson(res, result.ok ? 200 : 400, result);
    return;
  }

  if (req.method === 'GET' && url.pathname === '/local-engine/profiles') {
    writeJson(res, 200, controller.listProfiles());
    return;
  }

  if (req.method === 'GET' && url.pathname === '/local-engine/workspace-agents') {
    writeJson(res, 200, controller.listAllWorkspaceAgents());
    return;
  }

  if (req.method === 'POST' && url.pathname === '/local-engine/profiles') {
    try {
      const raw = await readBody(req);
      const body = raw ? JSON.parse(raw) : {};
      writeJson(res, 200, controller.createProfile(body.name));
    } catch (error) {
      writeJson(res, 400, { ok: false, error: error instanceof Error ? error.message : String(error) });
    }
    return;
  }

  if (req.method === 'POST' && url.pathname === '/local-engine/profiles/import-samples') {
    try {
      const raw = await readBody(req);
      const body = raw ? JSON.parse(raw) : {};
      writeJson(res, 200, controller.importOfficialSamples(body.profile));
    } catch (error) {
      writeJson(res, 400, { ok: false, error: error instanceof Error ? error.message : String(error) });
    }
    return;
  }

  if (req.method === 'GET') {
    const agentsMatch = url.pathname.match(/^\/local-engine\/profiles\/([^/]+)\/agents$/);
    if (agentsMatch) {
      writeJson(res, 200, controller.listWorkspaceAgents(decodeURIComponent(agentsMatch[1])));
      return;
    }
    const deckMatch = url.pathname.match(/^\/local-engine\/profiles\/([^/]+)\/agents\/([^/]+)\/deck\.csv$/);
    if (deckMatch) {
      const deck = controller.workspaceAgentDeck(decodeURIComponent(deckMatch[1]), decodeURIComponent(deckMatch[2]));
      if (deck === undefined) {
        writeJson(res, 404, { ok: false, error: 'Deck not found.' });
        return;
      }
      const body = Buffer.from(deck, 'utf8');
      res.writeHead(200, { 'Content-Type': 'text/csv; charset=utf-8', 'Content-Length': body.length });
      res.end(body);
      return;
    }
  }

  if (req.method === 'POST') {
    const uploadMatch = url.pathname.match(/^\/local-engine\/profiles\/([^/]+)\/agents$/);
    if (uploadMatch) {
      try {
        const raw = await readBody(req);
        const body = raw ? JSON.parse(raw) : {};
        writeJson(res, 200, controller.saveWorkspaceAgent(decodeURIComponent(uploadMatch[1]), body));
      } catch (error) {
        writeJson(res, 400, { ok: false, error: error instanceof Error ? error.message : String(error) });
      }
      return;
    }
  }

  if (req.method === 'DELETE') {
    const deleteMatch = url.pathname.match(/^\/local-engine\/profiles\/([^/]+)\/agents\/([^/]+)$/);
    if (deleteMatch) {
      writeJson(res, 200, controller.deleteWorkspaceAgent(decodeURIComponent(deleteMatch[1]), decodeURIComponent(deleteMatch[2])));
      return;
    }
  }

  if (req.method !== 'POST' || url.pathname !== '/local-engine') {
    writeJson(res, 404, { ok: false, error: 'Not found' });
    return;
  }

  try {
    const raw = await readBody(req);
    const command = raw ? JSON.parse(raw) : { type: 'state' };
    const response = await controller.handle(command);
    logCommand(clientIdOf(req), command, response);
    writeJson(res, response.ok ? 200 : 400, response);
  } catch (error) {
    writeJson(res, 400, {
      ok: false,
      error: error instanceof Error ? error.message : String(error),
    });
  }
});

// Diagnostic trail of every engine command, so "a card picked itself" reports can be
// traced to the exact request that made the selection. One line per command.
const COMMAND_LOG = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'logs', 'cabt-commands.log');
const COMMAND_LOG_MAX_BYTES = 4 * 1024 * 1024;

function logCommand(clientId: string, command: any, response: any): void {
  if (command?.type === 'state') {
    return; // polling noise
  }
  try {
    const payload = command?.payload ?? {};
    const parts = [
      new Date().toISOString(),
      `client=${String(clientId).slice(0, 12)}`,
      `type=${command?.type}`,
    ];
    for (const key of ['id', 'result', 'handIndex', 'playerIndex', 'to', 'count'] as const) {
      if (payload[key] !== undefined) {
        parts.push(`${key}=${JSON.stringify(payload[key]).slice(0, 80)}`);
      }
    }
    const prompt = response?.view?.prompts?.[0];
    parts.push(`-> ok=${response?.ok}`);
    parts.push(prompt ? `prompt=${prompt.className}#${prompt.id}(${JSON.stringify(prompt.message).slice(0, 40)})` : 'prompt=none');
    if (!response?.ok && response?.error) {
      parts.push(`error=${JSON.stringify(String(response.error).split('\n')[0]).slice(0, 120)}`);
    }
    fs.mkdirSync(path.dirname(COMMAND_LOG), { recursive: true });
    try {
      if (fs.statSync(COMMAND_LOG).size > COMMAND_LOG_MAX_BYTES) {
        fs.renameSync(COMMAND_LOG, `${COMMAND_LOG}.old`);
      }
    } catch {
      // first write
    }
    fs.appendFileSync(COMMAND_LOG, `${parts.join(' ')}\n`);
  } catch {
    // logging must never break the game
  }
}

// Kill every engine bridge when the server stops, so no Python processes leak.
function closeAllControllers(): void {
  for (const [id, entry] of controllers) {
    try {
      entry.controller.close();
    } catch {
      // best-effort shutdown
    }
    controllers.delete(id);
  }
}
for (const signal of ['SIGINT', 'SIGTERM', 'SIGHUP'] as const) {
  process.on(signal, () => {
    closeAllControllers();
    process.exit(0);
  });
}
process.on('exit', closeAllControllers);

server.listen(port, host, () => {
  process.stdout.write(`[cabt-local-engine] listening on http://${host}:${port}\n`);
  if (dataSyncEnabled) {
    process.stdout.write('[cabt-local-engine] data sync enabled; pulling persistent data\n');
    void pullAll([
      { repoPrefix: 'workspaces', dir: WORKSPACES_DIR },
      { repoPrefix: 'game-logs', dir: GAME_LOGS_DIR },
    ]);
  }
});
