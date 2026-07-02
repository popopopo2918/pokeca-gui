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
  } else if (!body.ok && (body.error.includes('session') || body.error.includes('セッション'))) {
    // Drop the stale session id so the next command can start a fresh game. The engine reports
    // session problems in Japanese ("セッション"); the English check stays for older responses.
    currentSessionId = '';
  }
  return body;
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

  resolvePrompt(id: number, result: unknown) {
    return send({ type: 'resolvePrompt', payload: { id, result } });
  },
};
