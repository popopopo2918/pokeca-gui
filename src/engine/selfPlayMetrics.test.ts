import { describe, expect, it } from 'vitest';
import type { SelfPlayDecisionRecord } from './codexProtocol';
import { calculateSelfPlayMetrics } from './selfPlayMetrics';

function record(
  seat: 0 | 1,
  playerTurn: number,
  kind: SelfPlayDecisionRecord['selected'][number]['kind'],
  ownPrizesLeftBefore = 6,
  ownPrizesLeftAfter = ownPrizesLeftBefore,
): SelfPlayDecisionRecord {
  return {
    seat,
    playerTurn,
    revision: playerTurn,
    turn: playerTurn * 2,
    decisionId: `d-${seat}-${playerTurn}-${kind}`,
    tokens: ['token'],
    prompt: '操作を選んでください。',
    selected: [{ kind, label: kind }],
    ownPrizesLeftBefore,
    ownPrizesLeftAfter,
    rationale: {
      action: kind,
      goal: '勝利へ進める',
      evidence: '公開盤面と自分の手札',
      alternative: '別の合法手を見送る',
    },
    createdAt: '2026-07-15T00:00:00.000Z',
  };
}

describe('calculateSelfPlayMetrics', () => {
  it('全体ターンではなくフーディン席自身のターン数で初攻撃を数える', () => {
    const decisions = [
      record(0, 1, 'end'),
      record(1, 1, 'end'),
      record(0, 2, 'attack'),
    ];

    expect(calculateSelfPlayMetrics(decisions, 0, 0)).toMatchObject({
      firstAttackPlayerTurn: 2,
      attackedByTurn2: true,
      attackedByTurn3: true,
      winner: 0,
    });
  });

  it('自分のサイドが減った自席ターンをきぜつターンとして数える', () => {
    const decisions = [
      record(0, 1, 'end'),
      record(1, 1, 'end'),
      record(0, 2, 'attack'),
      record(0, 2, 'card', 6, 5),
      record(1, 2, 'attack'),
      record(0, 3, 'attack', 5, 5),
      record(0, 3, 'card', 5, 4),
    ];

    expect(calculateSelfPlayMetrics(decisions, 0, 0)).toMatchObject({
      firstKnockoutPlayerTurn: 2,
      knockedOutByTurn2: true,
      knockedOutByTurn3: true,
      knockoutTurns: [2, 3],
      consecutiveKnockoutRate: 1,
    });
  });

  it('攻撃もきぜつもない試合では到達フラグをfalseにする', () => {
    expect(calculateSelfPlayMetrics([record(0, 1, 'end')], 0, 1)).toEqual({
      attackedByTurn2: false,
      knockedOutByTurn2: false,
      attackedByTurn3: false,
      knockedOutByTurn3: false,
      knockoutTurns: [],
      winner: 1,
    });
  });
});
