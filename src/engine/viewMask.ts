import { CabtAreaType } from '../lib/cabt/types';
import type { ActionTimelineEvent, GameView, PromptView } from '../lib/game/types';

const HIDDEN_CARD = { name: '未公開', fullName: '相手の手札（未公開）' };

export function maskViewForSeat(view: GameView, seat: number): GameView {
  const opponent = 1 - seat;
  return {
    ...view,
    players: view.players.map((player, index) => (
      index === opponent
        ? { ...player, hand: player.hand.map(() => ({ ...HIDDEN_CARD })), prizeContents: undefined }
        : player
    )),
    prompts: view.prompts.map((prompt) => maskPrompt(prompt, seat)),
    actionTimeline: view.actionTimeline?.map((event) => maskTimelineEvent(event, opponent)),
  };
}

export function maskViewForCodex(view: GameView, seat: number): GameView {
  const masked = maskViewForSeat(view, seat);
  return {
    ...masked,
    players: masked.players.map((player) => ({ ...player, prizeContents: undefined })),
  };
}

function maskPrompt(prompt: PromptView, seat: number): PromptView {
  if (prompt.playerIndex === seat || prompt.fields?.playbackOnly === true) {
    return prompt;
  }
  const { cardList: _cards, cards: _cards2, values: _values, prizes: _prizes, cabtSelect: _select, ...rest } = prompt.fields ?? {};
  return { ...prompt, fields: { ...rest, masked: true } };
}

export function maskTimelineEvent(event: ActionTimelineEvent, opponent: number): ActionTimelineEvent {
  if (event.playerIndex !== opponent) {
    return event;
  }
  const params = (event.params ?? {}) as Record<string, unknown>;
  const toHand = Number(params.toArea) === CabtAreaType.HAND;
  const isDraw = event.kind === 'Draw';
  if (!isDraw && !toHand) {
    return event;
  }
  const actor = `プレイヤー${opponent + 1}`;
  const message = isDraw ? `${actor}はカードを引いた。` : `${actor}はカードを手札に加えた。`;
  const { cardId: _cardId, serial: _serial, ...maskedParams } = params;
  return { ...event, message, params: maskedParams };
}
