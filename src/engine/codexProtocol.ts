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

export type CodexDecisionRecord = {
  revision: number;
  turn: number;
  decisionId: string;
  tokens: string[];
  rationale: CodexRationale;
  createdAt: string;
};

export type SelfPlayDecisionRecord = CodexDecisionRecord & {
  seat: 0 | 1;
  playerTurn: number;
  prompt: string;
  selected: Array<Pick<CodexDecisionOption, 'kind' | 'label' | 'source' | 'target'>>;
  ownPrizesLeftBefore: number;
  ownPrizesLeftAfter: number;
};

export type SelfPlayMetrics = {
  firstAttackPlayerTurn?: number;
  firstKnockoutPlayerTurn?: number;
  attackedByTurn2: boolean;
  knockedOutByTurn2: boolean;
  attackedByTurn3: boolean;
  knockedOutByTurn3: boolean;
  knockoutTurns: number[];
  consecutiveKnockoutRate?: number;
  winner?: number;
};

export function sanitizeCodexRationale(value: unknown): CodexRationale | null {
  if (!value || typeof value !== 'object') return null;
  const source = value as Record<string, unknown>;
  const keys = ['action', 'goal', 'evidence', 'alternative'] as const;
  const fields = Object.fromEntries(
    keys.map((key) => [key, String(source[key] ?? '').trim().slice(0, 500)]),
  ) as Record<(typeof keys)[number], string>;
  if (keys.some((key) => !fields[key])) return null;
  return fields;
}
