export type AgentOption = {
  id: string;
  name: string;
  description?: string;
  path?: string;
  deckUrl?: string;
};

export type GameLogEntry = {
  id: string;
  name: string;
  file: string;
  createdAt?: string;
  players?: string[];
  description?: string;
};

const FALLBACK_AGENT: AgentOption = {
  id: 'first-legal',
  name: '最初の有効手',
  description: 'ローカルエンジンが相手を操作するとき、常に最初の有効な選択肢を選びます。',
};

export async function loadAgentOptions(): Promise<AgentOption[]> {
  const agents = await loadJsonList<AgentOption>('/agents/agents.json', 'agents');
  return agents.length ? agents : [FALLBACK_AGENT];
}

export async function loadGameLogs(): Promise<GameLogEntry[]> {
  return loadJsonList<GameLogEntry>('/game-logs/logs.json', 'logs');
}

export async function loadProfiles(): Promise<string[]> {
  try {
    const response = await fetch('/local-engine/profiles');
    if (!response.ok) return ['default'];
    const json = await response.json();
    return Array.isArray(json.profiles) && json.profiles.length ? json.profiles : ['default'];
  } catch {
    return ['default'];
  }
}

export async function createProfile(name: string): Promise<string[]> {
  try {
    const response = await fetch('/local-engine/profiles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    const json = await response.json();
    return Array.isArray(json.profiles) ? json.profiles : [];
  } catch {
    return [];
  }
}

export async function loadWorkspaceAgents(profile: string): Promise<AgentOption[]> {
  try {
    const response = await fetch(`/local-engine/profiles/${encodeURIComponent(profile)}/agents`);
    if (!response.ok) return [];
    const json = await response.json();
    return Array.isArray(json.agents) ? json.agents : [];
  } catch {
    return [];
  }
}

/** All uploaded agents across every profile (shared so anyone's AI is usable by everyone). */
export async function loadAllWorkspaceAgents(): Promise<AgentOption[]> {
  try {
    const response = await fetch('/local-engine/workspace-agents');
    if (!response.ok) return [];
    const json = await response.json();
    return Array.isArray(json.agents) ? json.agents : [];
  } catch {
    return [];
  }
}

export async function importSampleAgents(profile: string): Promise<AgentOption[]> {
  try {
    const response = await fetch('/local-engine/profiles/import-samples', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile }),
    });
    const json = await response.json();
    return Array.isArray(json.agents) ? json.agents : [];
  } catch {
    return [];
  }
}

export type UploadAgentResult = { ok: boolean; error?: string };

export async function uploadWorkspaceAgent(
  profile: string,
  name: string,
  mainPy: string,
  deckCsv: string,
): Promise<UploadAgentResult> {
  try {
    const response = await fetch(`/local-engine/profiles/${encodeURIComponent(profile)}/agents`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, mainPy, deckCsv }),
    });
    const json = await response.json();
    return { ok: !!json.ok, error: json.error };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

export async function deleteWorkspaceAgent(profile: string, name: string): Promise<boolean> {
  try {
    const response = await fetch(
      `/local-engine/profiles/${encodeURIComponent(profile)}/agents/${encodeURIComponent(name)}`,
      { method: 'DELETE' },
    );
    const json = await response.json();
    return !!json.ok;
  } catch {
    return false;
  }
}

async function loadJsonList<T extends { id?: unknown }>(url: string, key: string): Promise<T[]> {
  const response = await fetch(url);
  if (!response.ok) {
    if (response.status === 404) {
      return [];
    }
    throw new Error(`${url}: ${response.status}`);
  }

  const json = await response.json();
  const list = Array.isArray(json) ? json : json?.[key];
  if (!Array.isArray(list)) {
    throw new Error(`${url}: expected an array or { "${key}": [...] }`);
  }
  return list.filter((item): item is T => !!item && typeof item === 'object' && typeof item.id === 'string');
}
