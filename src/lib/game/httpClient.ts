import type { GameCommandApi } from './gameApi';
import type { CardTarget, EngineResponse } from './types';

type Command = {
  type: string;
  payload?: unknown;
  availableActionsScope?: AvailableActionsScope;
};

type AvailableActionsScope = 'none' | 'active' | 'full';
export type PlayerControl = 'self' | 'agent';

type StartOptions = {
  player1Control?: PlayerControl;
  player2Control?: PlayerControl;
  player1AgentId?: string;
  player2AgentId?: string;
};

export type SaveReplayResponse = {
  ok: boolean;
  file?: string;
  id?: string;
  error?: string;
};

let currentSessionId = '';

function getClientId(): string {
  try {
    let id = localStorage.getItem('cabt:clientId');
    if (!id) {
      id = `c-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
      localStorage.setItem('cabt:clientId', id);
    }
    return id;
  } catch {
    return 'default';
  }
}

function jsonHeaders(): Record<string, string> {
  return { 'Content-Type': 'application/json', 'x-cabt-client': getClientId() };
}

async function send(command: Command): Promise<EngineResponse> {
  const commandWithSession = command.type === 'startGame' || !currentSessionId
    ? command
    : {
        ...command,
        payload: {
          ...(command.payload && typeof command.payload === 'object' ? command.payload : {}),
          sessionId: currentSessionId,
        },
      };
  const response = await fetch('/local-engine', {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(commandWithSession),
  });
  const body = await response.json() as EngineResponse;
  if (body.ok && body.sessionId) {
    currentSessionId = body.sessionId;
  } else if (!body.ok && (body.sessionExpired || isSessionErrorMessage(body.error))) {
    // Drop the stale session id so the next command can start a fresh game.
    currentSessionId = '';
  }
  return body;
}

// Fallback for older servers that do not send the structured `sessionExpired` flag.
// Only the first line is checked: engine errors append Python tracebacks that contain
// unrelated matches like `session.select(...)`, and dropping the id on such errors used
// to lock the whole match behind 「CABTセッションIDが必要です」.
function isSessionErrorMessage(error: string | undefined): boolean {
  const firstLine = (error ?? '').split('\n', 1)[0];
  return firstLine.includes('セッション') || firstLine.toLowerCase().includes('session expired');
}

export function hostedAvailableActionsScope(command: Command): AvailableActionsScope | undefined {
  if (command.availableActionsScope) {
    return command.availableActionsScope;
  }

  switch (command.type) {
    case 'playCard':
    case 'attack':
    case 'useAbility':
    case 'useStadium':
    case 'concede':
    case 'retreat':
    case 'resolvePrompt':
      return 'none';
    default:
      return undefined;
  }
}

function hostedAvailableActionsOptions(command: Command): { availableActionsScope?: AvailableActionsScope } {
  const availableActionsScope = hostedAvailableActionsScope(command);
  return availableActionsScope ? { availableActionsScope } : {};
}

// ---- 遠隔対戦ルーム ----

async function roomFetch(path: string, init?: RequestInit): Promise<any> {
  const response = await fetch(`/local-engine/rooms${path}`, {
    ...init,
    headers: { ...jsonHeaders(), ...(init?.headers ?? {}) },
  });
  return response.json();
}

export const roomApi = {
  create(deck: string[]) {
    return roomFetch('', { method: 'POST', body: JSON.stringify({ deck }) });
  },
  join(code: string, deck: string[]) {
    return roomFetch(`/${encodeURIComponent(code.trim().toUpperCase())}/join`, { method: 'POST', body: JSON.stringify({ deck }) });
  },
  state(code: string, since: number) {
    return roomFetch(`/${encodeURIComponent(code)}/state?since=${since}`, { method: 'GET' });
  },
  leave(code: string) {
    return roomFetch(`/${encodeURIComponent(code)}/leave`, { method: 'POST', body: '{}' });
  },
  command(code: string, type: string, payload?: unknown) {
    return roomFetch(`/${encodeURIComponent(code)}/command`, { method: 'POST', body: JSON.stringify({ type, payload }) }) as Promise<EngineResponse>;
  },
};

/** GameCommandApi that routes every command through an online room. */
export function createRoomGameApi(code: string, onRevision?: (revision: number) => void): GameCommandApi {
  const send = (type: string, payload?: unknown) =>
    roomApi.command(code, type, payload).then((body: EngineResponse & { revision?: number }) => {
      if (typeof body.revision === 'number') {
        onRevision?.(body.revision);
      }
      return body;
    });
  return {
    playCard: (playerIndex, handIndex, target) => send('playCard', { playerIndex, handIndex, target }),
    attack: (playerIndex, attack) => send('attack', { playerIndex, attack }),
    useAbility: (playerIndex, ability, target) => send('useAbility', { playerIndex, ability, target }),
    useStadium: (playerIndex) => send('useStadium', { playerIndex }),
    concede: (playerIndex) => send('concede', { playerIndex }),
    retreat: (playerIndex, to) => send('retreat', { playerIndex, to }),
    passTurn: (playerIndex) => send('passTurn', { playerIndex }),
    undo: () => Promise.resolve({ ok: false, error: 'オンライン対戦では指し直しは使えません。' }),
    resolvePrompt: (id, result) => send('resolvePrompt', { id, result }),
  };
}

export const localGameApi: GameCommandApi & {
  start(
    player1Deck: string[],
    player2Deck: string[],
    options?: StartOptions,
  ): Promise<EngineResponse>;
  saveReplay(): Promise<SaveReplayResponse>;
  state(): Promise<EngineResponse>;
} = {
  start(
    player1Deck: string[],
    player2Deck: string[],
    options: StartOptions = {},
  ) {
    const player1Control = options.player1Control ?? 'self';
    const player2Control = options.player2Control ?? 'agent';
    return send({
      type: 'startGame',
      payload: {
        player1: {
          name: 'Player 1',
          deck: player1Deck,
          control: player1Control,
          agentId: options.player1AgentId,
        },
        player2: {
          name: 'Player 2',
          deck: player2Deck,
          control: player2Control,
          agentId: options.player2AgentId,
        },
      },
    });
  },

  state() {
    return send({ type: 'state' });
  },

  async saveReplay() {
    const response = await fetch('/local-engine/save-replay', {
      method: 'POST',
      headers: jsonHeaders(),
      body: '{}',
    });
    return await response.json() as SaveReplayResponse;
  },

  playCard(playerIndex: number, handIndex: number, target: CardTarget) {
    return send({ type: 'playCard', payload: { playerIndex, handIndex, target } });
  },

  attack(playerIndex: number, attack: string) {
    return send({ type: 'attack', payload: { playerIndex, attack } });
  },

  useAbility(playerIndex: number, ability: string, target: CardTarget) {
    return send({ type: 'useAbility', payload: { playerIndex, ability, target } });
  },

  useStadium(playerIndex: number) {
    return send({ type: 'useStadium', payload: { playerIndex } });
  },

  concede(playerIndex: number) {
    return send({ type: 'concede', payload: { playerIndex } });
  },

  retreat(playerIndex: number, to: number) {
    return send({ type: 'retreat', payload: { playerIndex, to } });
  },

  passTurn(playerIndex: number) {
    return send({ type: 'passTurn', payload: { playerIndex } });
  },

  undo(count = 1) {
    return send({ type: 'undo', payload: { count } });
  },

  resolvePrompt(id: number, result: unknown) {
    return send({ type: 'resolvePrompt', payload: { id, result } });
  },
};
