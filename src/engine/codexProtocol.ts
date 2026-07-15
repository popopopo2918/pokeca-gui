export type CodexDecisionKind =
  | 'play'
  | 'attach'
  | 'evolve'
  | 'ability'
  | 'attack'
  | 'retreat'
  | 'end'
  | 'yes'
  | 'no'
  | 'number'
  | 'card'
  | 'other';

export type CodexDecisionOption = {
  token: string;
  kind: CodexDecisionKind;
  label: string;
  source?: string;
  target?: string;
};

export type CodexEngineDecision = {
  decisionId: string;
  playerIndex: number;
  prompt: string;
  minCount: number;
  maxCount: number;
  options: CodexDecisionOption[];
};

export type CodexDeckEntry = {
  id: number;
  name: string;
  count: number;
};

export type CodexSearchSnapshot = {
  decisionId: string;
  prompt: string;
  cards: Array<{ id: number; name: string }>;
};

export type CodexRationale = {
  action: string;
  goal: string;
  evidence: string;
  alternative: string;
};
