import { describe, expect, it } from 'vitest';
import type { GameView } from '../lib/game/types';
import { maskViewForCodex, maskViewForSeat } from './viewMask';

function gameView(): GameView {
  const slot = (ownerIndex: number) => ({
    ownerIndex,
    slot: 'active' as const,
    index: 0,
    target: { player: 2, slot: 1, index: 0 },
    empty: true,
    cards: [],
    damage: 0,
    hp: 0,
    retreat: [],
    energy: [],
    tools: [],
    specialConditions: [],
  });
  return {
    ready: true,
    phase: 3,
    phaseLabel: 'プレイヤーの番',
    turn: 1,
    activePlayerIndex: 1,
    players: [0, 1].map((index) => ({
      index,
      id: index,
      name: `P${index + 1}`,
      hand: [{ name: `hand-${index}`, fullName: `hand-${index}` }],
      deckCount: 46,
      discard: [],
      lostZone: [],
      stadium: [],
      playZone: [],
      prizesLeft: 6,
      prizeContents: [{ name: `prize-${index}`, fullName: `prize-${index}` }],
      active: slot(index),
      bench: [],
      playableCardIds: [],
    })),
    prompts: [{
      id: 9,
      className: 'ChooseCardsPrompt',
      type: 'cabt-select',
      playerId: 1,
      playerIndex: 1,
      supported: true,
      resultSchema: 'cardIndexes',
      fields: { cards: [{ name: 'secret' }], cabtSelect: { option: [{}] } },
    }],
    logs: [],
    actionTimeline: [],
    events: [],
  };
}

describe('view masks', () => {
  it('Codexには自分の手札だけを見せ、双方のサイド実体を隠す', () => {
    const masked = maskViewForCodex(gameView(), 1);
    expect(masked.players[1].hand[0].name).toBe('hand-1');
    expect(masked.players[0].hand[0].name).toBe('未公開');
    expect(masked.players[0].prizeContents).toBeUndefined();
    expect(masked.players[1].prizeContents).toBeUndefined();
  });

  it('既存ルームでは自分のサイド確認機能を維持する', () => {
    const masked = maskViewForSeat(gameView(), 1);
    expect(masked.players[1].prizeContents?.[0].name).toBe('prize-1');
    expect(masked.players[0].prizeContents).toBeUndefined();
  });

  it('相手側の選択肢と手札に加えたカード名を隠す', () => {
    const source = gameView();
    source.prompts[0].playerIndex = 0;
    source.actionTimeline = [{
      id: 1,
      playerIndex: 0,
      kind: 'Draw',
      message: '相手がケーシィを引いた。',
      params: { cardId: 101, serial: 44 },
    }];

    const masked = maskViewForCodex(source, 1);
    expect(masked.prompts[0].fields).toEqual({ masked: true });
    expect(masked.actionTimeline?.[0].message).toBe('プレイヤー1はカードを引いた。');
    expect(masked.actionTimeline?.[0].params).not.toHaveProperty('cardId');
  });
});
