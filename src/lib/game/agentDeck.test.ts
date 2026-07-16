import { describe, expect, it } from 'vitest';
import { fixedAgentDeckSource } from './agentDeck';

const agents = [
  {
    id: 'normal',
    name: '通常AI',
    deckUrl: '/agents/normal/deck.csv',
  },
  {
    id: 'alakazam-playbook',
    name: 'フーディンAI（現行sample_a）',
    deckUrl: '/agents/alakazam-playbook/deck.csv',
    fixedDeck: true,
  },
];

describe('fixedAgentDeckSource', () => {
  it('returns the paired source only for a fixed agent-controlled seat', () => {
    expect(fixedAgentDeckSource('agent', 'alakazam-playbook', agents)).toBe(
      'alakazam-playbook',
    );
    expect(fixedAgentDeckSource('agent', 'normal', agents)).toBeNull();
    expect(fixedAgentDeckSource('self', 'alakazam-playbook', agents)).toBeNull();
    expect(fixedAgentDeckSource('agent', 'missing', agents)).toBeNull();
  });
});
