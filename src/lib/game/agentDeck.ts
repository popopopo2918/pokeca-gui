import type { AgentOption } from '../home/catalog';
import type { PlayerControl } from './httpClient';

export function fixedAgentDeckSource(
  control: PlayerControl,
  agentId: string,
  agents: readonly AgentOption[],
): string | null {
  if (control !== 'agent') return null;
  const agent = agents.find((candidate) => candidate.id === agentId);
  return agent?.fixedDeck === true && !!agent.deckUrl ? agent.id : null;
}
