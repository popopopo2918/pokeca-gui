import { describe, expect, it } from 'vitest';
import { CabtAreaType, CabtLogType } from './types';
import { cabtLogsToTimeline, formatCabtLog } from './logFormat';

describe('CABT log formatting', () => {
  it('describes attack, deterministic discard, damage, and prize events', () => {
    expect(formatCabtLog({
      type: CabtLogType.ATTACK,
      playerIndex: 0,
      cardId: 723,
      attackId: 1046,
    })).toBe('プレイヤー1は「メガユキノオーex」で「アバランチハンマー」を使った。');

    expect(formatCabtLog({
      type: CabtLogType.MOVE_CARD,
      playerIndex: 0,
      cardId: 3,
      fromArea: CabtAreaType.DECK,
      toArea: CabtAreaType.DISCARD,
    })).toBe('プレイヤー1は山札から「基本【水】エネルギー」をトラッシュした。');

    expect(formatCabtLog({
      type: CabtLogType.HP_CHANGE,
      playerIndex: 1,
      cardId: 722,
      value: -200,
    })).toBe('プレイヤー2の「ユキカブリ」は200ダメージを受けた。');

    expect(formatCabtLog({
      type: CabtLogType.MOVE_CARD_REVERSE,
      playerIndex: 0,
      fromArea: CabtAreaType.PRIZE,
      toArea: CabtAreaType.HAND,
    })).toBe('プレイヤー1は裏向きのカードをサイドから手札へ移動した。');
  });

  it('records ability use and distinguishes placing a Pokémon from using a trainer', () => {
    // Synthetic ability log injected by the engine bridge (type: 'ability').
    expect(formatCabtLog({ type: 'ability', playerIndex: 0, cardId: 743 }))
      .toBe('プレイヤー1の「フーディン」が特性を使った。');
    // Playing a Pokémon = putting it into play.
    expect(formatCabtLog({ type: CabtLogType.PLAY, playerIndex: 0, cardId: 743 }))
      .toBe('プレイヤー1は「フーディン」を出した。');
    // Playing a trainer/item = using it.
    expect(formatCabtLog({ type: CabtLogType.PLAY, playerIndex: 1, cardId: 1152 }))
      .toBe('プレイヤー2は「ポケパッド」を使った。');
  });

  it('tags ability timeline events with the ability kind', () => {
    const result = cabtLogsToTimeline([{ type: 'ability', playerIndex: 0, cardId: 743 }]);
    expect(result.events[0]).toEqual(
      expect.objectContaining({ kind: 'ability', message: 'プレイヤー1の「フーディン」が特性を使った。' }),
    );
  });

  it('assigns stable ids when converting log batches to timeline events', () => {
    const result = cabtLogsToTimeline([
      { type: CabtLogType.TURN_START, playerIndex: 1 },
      { type: CabtLogType.TURN_END, playerIndex: 1 },
    ], { nextId: 7 });

    expect(result.nextId).toBe(9);
    expect(result.events).toEqual([
      expect.objectContaining({ id: 7, message: 'プレイヤー2の番が始まった。', kind: 'TurnStart' }),
      expect.objectContaining({ id: 8, message: 'プレイヤー2は番を終えた。', kind: 'TurnEnd' }),
    ]);
  });
});
