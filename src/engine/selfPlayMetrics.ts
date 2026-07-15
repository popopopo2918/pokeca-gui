import type { SelfPlayDecisionRecord, SelfPlayMetrics } from './codexProtocol';

export function calculateSelfPlayMetrics(
  decisions: SelfPlayDecisionRecord[],
  alakazamSeat: 0 | 1,
  winner?: number,
): SelfPlayMetrics {
  const own = decisions.filter((decision) => decision.seat === alakazamSeat);
  const attackTurns = own
    .filter((decision) => decision.selected.some((option) => option.kind === 'attack'))
    .map((decision) => decision.playerTurn);
  const knockoutTurns = [...new Set(own
    .filter((decision) => decision.ownPrizesLeftAfter < decision.ownPrizesLeftBefore)
    .map((decision) => decision.playerTurn))]
    .sort((a, b) => a - b);
  const firstAttackPlayerTurn = attackTurns.length ? Math.min(...attackTurns) : undefined;
  const firstKnockoutPlayerTurn = knockoutTurns[0];
  const lastPlayerTurn = own.reduce((max, decision) => Math.max(max, decision.playerTurn), 0);
  const knockoutWindow = firstKnockoutPlayerTurn === undefined
    ? 0
    : Math.max(1, lastPlayerTurn - firstKnockoutPlayerTurn + 1);

  return {
    ...(firstAttackPlayerTurn === undefined ? {} : { firstAttackPlayerTurn }),
    ...(firstKnockoutPlayerTurn === undefined ? {} : { firstKnockoutPlayerTurn }),
    attackedByTurn2: firstAttackPlayerTurn !== undefined && firstAttackPlayerTurn <= 2,
    knockedOutByTurn2: firstKnockoutPlayerTurn !== undefined && firstKnockoutPlayerTurn <= 2,
    attackedByTurn3: firstAttackPlayerTurn !== undefined && firstAttackPlayerTurn <= 3,
    knockedOutByTurn3: firstKnockoutPlayerTurn !== undefined && firstKnockoutPlayerTurn <= 3,
    knockoutTurns,
    ...(knockoutWindow ? { consecutiveKnockoutRate: knockoutTurns.length / knockoutWindow } : {}),
    ...(winner === undefined ? {} : { winner }),
  };
}
