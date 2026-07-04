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

describe('japaneseCardMoves', () => {
  it('excludes the Terastal rule box from attacks (Dragapult ex regression)', async () => {
    const { japaneseCardMoves } = await import('./logFormat');
    const moves = japaneseCardMoves(121);
    expect(moves.terastal?.name).toBe('テラスタル');
    expect(moves.attacks.map((a) => a.name)).toEqual(['ジェットヘッド', 'ファントムダイブ']);
    expect(moves.attacks[1]?.damage).toBe('200');
  });

  it('aligns JA attack lists with EN attacks for every Pokemon card (all Terastal cards included)', async () => {
    const { japaneseCardMoves } = await import('./logFormat');
    const cardRows = (await import('./cardData.generated.json')).default as Array<{
      id: number; attacks?: number[]; cardType?: number;
    }>;
    const jaRows = (await import('../cards/cardsJa.generated.json')).default as Record<
      string, { moves?: unknown[] }
    >;
    let terastalCount = 0;
    for (const card of cardRows) {
      if (card.cardType !== 0) continue;
      const ja = jaRows[String(card.id)];
      if (!ja?.moves?.length) continue;
      const moves = japaneseCardMoves(card.id);
      if (moves.terastal) terastalCount += 1;
      // ここがズレると「テラスタルがワザ扱い・実ワザ欠落」が再発する
      expect(moves.attacks.length, `card ${card.id}`).toBe(card.attacks?.length ?? 0);
    }
    expect(terastalCount).toBeGreaterThanOrEqual(30);
  });
});
