import fs from 'node:fs';

const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:8095';
const CLIENT_ID = `e2e-alakazam-${Date.now()}`;
const deck = fs
  .readFileSync(
    new URL('../public/agents/alakazam-playbook/deck.csv', import.meta.url),
    'utf8',
  )
  .split(/\r?\n/u)
  .map((row) => row.trim())
  .filter(Boolean);

if (deck.length !== 60) {
  throw new Error(`フーディンAIデッキが60枚ではありません: ${deck.length}`);
}

const results = [];
for (const agentSeat of [0, 1]) {
  const humanSeat = 1 - agentSeat;
  const players = [0, 1].map((seat) =>
    seat === agentSeat
      ? {
          name: 'フーディンAI（現行sample_a）',
          deck,
          control: 'agent',
          agentId: 'alakazam-playbook',
        }
      : { name: '人間', deck, control: 'self' },
  );
  const response = await fetch(`${BASE}/local-engine`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-cabt-client': `${CLIENT_ID}-${agentSeat}`,
    },
    body: JSON.stringify({
      type: 'startGame',
      payload: { player1: players[0], player2: players[1] },
    }),
  });
  const body = await response.json();
  if (!response.ok || !body.ok) {
    throw new Error(`seat ${agentSeat} 対戦開始失敗: ${JSON.stringify(body)}`);
  }
  if (!body.sessionId) {
    throw new Error(`seat ${agentSeat}: CABTセッションIDが返りませんでした。`);
  }
  if (!Array.isArray(body.view?.players) || body.view.players.length !== 2) {
    throw new Error(`seat ${agentSeat}: 2人分の対戦画面が返りませんでした。`);
  }
  if (!Array.isArray(body.sequence)) {
    throw new Error(
      `seat ${agentSeat}: AI自動処理を含むsequenceが返りませんでした。`,
    );
  }
  const interactivePrompts = (body.view.prompts ?? []).filter(
    (prompt) => prompt.fields?.playbackOnly !== true,
  );
  if (
    interactivePrompts.some((prompt) => prompt.playerIndex !== humanSeat)
  ) {
    throw new Error(
      `seat ${agentSeat}: AI側の未処理プロンプトがGUIへ残っています。`,
    );
  }
  results.push({
    agentSeat,
    sessionId: body.sessionId,
    frames: body.sequence.length,
    activePlayerIndex: body.view.activePlayerIndex,
  });
}

process.stdout.write(`${JSON.stringify(results)}\n`);
