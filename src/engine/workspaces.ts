import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(__dirname, '..', '..');
const WORKSPACE_ROOT = path.resolve(FRONTEND_ROOT, '..');

export const WORKSPACES_DIR = path.join(WORKSPACE_ROOT, 'workspaces');
const OFFICIAL_AGENTS_DIR = path.join(FRONTEND_ROOT, 'public', 'agents');
const DEFAULT_PROFILE = 'default';

export type WorkspaceAgent = {
  id: string;
  name: string;
  description?: string;
  path: string;
  deckUrl?: string;
};

export function sanitizeProfile(name: unknown): string {
  const cleaned = String(name ?? '')
    .trim()
    .replace(/[^\w.\- ]+/g, '')
    .replace(/\s+/g, ' ')
    .slice(0, 40);
  return cleaned || DEFAULT_PROFILE;
}

function agentsDir(profile: string): string {
  return path.join(WORKSPACES_DIR, sanitizeProfile(profile), 'agents');
}

export function ensureProfile(profile: string): string {
  const name = sanitizeProfile(profile);
  fs.mkdirSync(agentsDir(name), { recursive: true });
  return name;
}

export function listProfiles(): string[] {
  ensureProfile(DEFAULT_PROFILE);
  try {
    const names = fs
      .readdirSync(WORKSPACES_DIR, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name);
    return names.includes(DEFAULT_PROFILE) ? names : [DEFAULT_PROFILE, ...names];
  } catch {
    return [DEFAULT_PROFILE];
  }
}

/** Scan a profile's agents directory for folders that contain a runnable main.py. */
export function listWorkspaceAgents(profile: string): WorkspaceAgent[] {
  const name = sanitizeProfile(profile);
  const dir = agentsDir(name);
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return [];
  }
  const agents: WorkspaceAgent[] = [];
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const agentDir = path.join(dir, entry.name);
    if (!fs.existsSync(path.join(agentDir, 'main.py'))) continue;
    const hasDeck = fs.existsSync(path.join(agentDir, 'deck.csv'));
    agents.push({
      id: `ws:${name}:${entry.name}`,
      name: entry.name,
      description: `${name} のワークスペースの自作エージェント`,
      path: toPosix(path.join('workspaces', name, 'agents', entry.name, 'main.py')),
      deckUrl: hasDeck
        ? `/local-engine/profiles/${encodeURIComponent(name)}/agents/${encodeURIComponent(entry.name)}/deck.csv`
        : undefined,
    });
  }
  return agents.sort((a, b) => a.name.localeCompare(b.name));
}

/** Every uploaded agent across all profiles (so anyone's agent is usable by everyone). */
export function listAllWorkspaceAgents(): WorkspaceAgent[] {
  const agents: WorkspaceAgent[] = [];
  for (const profile of listProfiles()) {
    agents.push(...listWorkspaceAgents(profile));
  }
  return agents.sort((a, b) => a.id.localeCompare(b.id));
}

/** Dataset repo paths for an agent's files (used to mirror deletes to the persistent store). */
export function workspaceAgentRepoFiles(profile: string, id: string): string[] {
  const base = `workspaces/${sanitizeProfile(profile)}/agents/${sanitizeAgentId(id)}`;
  return [`${base}/main.py`, `${base}/deck.csv`];
}

/** Resolve a `ws:<profile>:<id>` agent id to a WORKSPACE_ROOT-relative main.py path. */
export function resolveWorkspaceAgentPath(agentId: string): string | undefined {
  const parsed = parseWorkspaceAgentId(agentId);
  if (!parsed) return undefined;
  const main = path.join(agentsDir(parsed.profile), parsed.id, 'main.py');
  if (!fs.existsSync(main)) return undefined;
  return toPosix(path.join('workspaces', sanitizeProfile(parsed.profile), 'agents', parsed.id, 'main.py'));
}

const MAX_AGENT_BYTES = 900_000;

/** Save an uploaded agent (main.py + optional deck.csv) into a profile's workspace. */
export function saveWorkspaceAgent(profile: string, name: unknown, mainPy: unknown, deckCsv: unknown): WorkspaceAgent {
  const profileName = ensureProfile(profile);
  const id = sanitizeAgentId(name);
  if (!id) {
    throw new Error('エージェント名は英数字・「-」「_」で指定してください。');
  }
  if (typeof mainPy !== 'string' || !mainPy.trim()) {
    throw new Error('main.py の内容が空です。');
  }
  if (mainPy.length > MAX_AGENT_BYTES) {
    throw new Error('main.py が大きすぎます。');
  }
  if (deckCsv !== undefined && deckCsv !== null && typeof deckCsv !== 'string') {
    throw new Error('deck.csv が不正です。');
  }
  const dir = path.join(agentsDir(profileName), id);
  if (!dir.startsWith(WORKSPACES_DIR + path.sep)) {
    throw new Error('保存先が不正です。');
  }
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'main.py'), mainPy, 'utf8');
  if (typeof deckCsv === 'string' && deckCsv.trim()) {
    fs.writeFileSync(path.join(dir, 'deck.csv'), deckCsv, 'utf8');
  }
  const agent = listWorkspaceAgents(profileName).find((a) => a.name === id);
  if (!agent) {
    throw new Error('保存後にエージェントを確認できませんでした。');
  }
  return agent;
}

export function deleteWorkspaceAgent(profile: string, id: string): boolean {
  const dir = path.join(agentsDir(profile), sanitizeAgentId(id));
  if (!dir.startsWith(WORKSPACES_DIR + path.sep)) {
    return false;
  }
  try {
    fs.rmSync(dir, { recursive: true, force: true });
    return true;
  } catch {
    return false;
  }
}

export function readWorkspaceAgentDeck(profile: string, id: string): string | undefined {
  const deck = path.join(agentsDir(profile), sanitizeAgentId(id), 'deck.csv');
  if (!deck.startsWith(WORKSPACES_DIR)) return undefined;
  try {
    return fs.readFileSync(deck, 'utf8');
  } catch {
    return undefined;
  }
}

/** Copy the bundled official sample agents into a profile so the user can edit their own copies. */
export function importOfficialSamples(profile: string): number {
  const name = ensureProfile(profile);
  const dest = agentsDir(name);
  let copied = 0;
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(OFFICIAL_AGENTS_DIR, { withFileTypes: true });
  } catch {
    return 0;
  }
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const from = path.join(OFFICIAL_AGENTS_DIR, entry.name);
    if (!fs.existsSync(path.join(from, 'main.py'))) continue;
    const to = path.join(dest, entry.name);
    if (fs.existsSync(to)) continue;
    fs.cpSync(from, to, { recursive: true });
    copied += 1;
  }
  return copied;
}

function parseWorkspaceAgentId(agentId: string): { profile: string; id: string } | undefined {
  if (typeof agentId !== 'string' || !agentId.startsWith('ws:')) return undefined;
  const rest = agentId.slice(3);
  const sep = rest.indexOf(':');
  if (sep < 0) return undefined;
  return { profile: rest.slice(0, sep), id: sanitizeAgentId(rest.slice(sep + 1)) };
}

function sanitizeAgentId(id: unknown): string {
  return String(id ?? '').replace(/[^\w.\- ]+/g, '');
}

function toPosix(value: string): string {
  return value.split(path.sep).join('/');
}
