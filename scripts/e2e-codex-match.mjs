import fs from 'node:fs';

const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:8196';
const CLIENT_ID = `e2e-codex-${Date.now()}`;
const rows = JSON.parse(fs.readFileSync(new URL('../src/lib/cabt/cardData.generated.json', import.meta.url), 'utf8'));

const deckSpec = [
  ['MEG', '56', 3], ['MEG', '55', 4], ['MEG', '54', 4], ['TEF', '129', 3],
  ['JTG', '120', 3], ['SCR', '118', 1], ['SFA', '40', 1], ['DRI', '10', 1],
  ['ASC', '39', 1], ['SFA', '38', 1], ['TEF', '144', 4], ['POR', '81', 4],
  ['SVI', '191', 4], ['DRI', '168', 1], ['TWM', '148', 2], ['BLK', '79', 3],
  ['WHT', '84', 3], ['PFL', '87', 3], ['PAL', '172', 3], ['TWM', '155', 1],
  ['PFL', '85', 4], ['SSP', '191', 1], ['POR', '87', 3], ['SVE', '5', 2],
];

function sampleDeck() {
  const cards = [];
  for (const [set, setNumber, count] of deckSpec) {
    const row = rows.find((card) => card.set === set && String(card.setNumber) === setNumber);
    if (!row) throw new Error(`E2Eデッキのカードが見つかりません: ${set} ${setNumber}`);
    for (let index = 0; index < count; index += 1) cards.push(String(row.id));
  }
  if (cards.length !== 60) throw new Error(`E2Eデッキが60枚ではありません: ${cards.length}`);
  return cards;
}

async function api(path, init = {}, connectionCode = '') {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'x-cabt-client': CLIENT_ID,
      ...(connectionCode ? { 'x-cabt-codex-code': connectionCode } : {}),
      ...(init.headers ?? {}),
    },
  });
  const body = await response.json();
  return { status: response.status, body };
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function agentTokens(decision) {
  const end = decision.options.find((option) => option.kind === 'end');
  if (end && decision.minCount <= 1) return [end.token];
  return decision.options.slice(0, decision.minCount).map((option) => option.token);
}

function humanResult(prompt) {
  const select = prompt.fields?.cabtSelect;
  const options = Array.isArray(select?.option) ? select.option : [];
  const endIndex = options.findIndex((option) => Number(option.type) === 14);
  if (endIndex >= 0 && Number(select.minCount) <= 1) return [endIndex];
  const min = Math.max(0, Number(select?.minCount ?? 1));
  return Array.from({ length: min }, (_unused, index) => index);
}

const deck = sampleDeck();
const created = await api('/local-engine/codex-matches', {
  method: 'POST',
  body: JSON.stringify({ decks: [deck, deck], codexSeat: 1 }),
});
assert(created.status === 200 && created.body.ok, `Codex対戦を開始できません: ${JSON.stringify(created.body)}`);
const { matchId, connectionCode, humanSeat, codexSeat } = created.body;
assert(created.body.view.players[codexSeat].hand.every((card) => card.name === '未公開'), 'ブラウザへCodex手札が漏れています。');
assert(created.body.view.players[codexSeat].prizeContents === undefined, 'ブラウザへCodexサイドが漏れています。');

let humanDecisions = 0;
let codexDecisions = 0;
let staleBody;
let revision = created.body.revision ?? 0;

for (let step = 0; step < 120 && (humanDecisions < 1 || codexDecisions < 1); step += 1) {
  const agent = await api('/local-engine/codex-agent/state', { method: 'GET' }, connectionCode);
  assert(agent.status === 200 && agent.body.ok, `Agent state失敗: ${JSON.stringify(agent.body)}`);
  assert(agent.body.view.players[humanSeat].hand.every((card) => card.name === '未公開'), 'Codexへ相手手札が漏れています。');
  assert(agent.body.view.players.every((player) => player.prizeContents === undefined), 'Codexへサイド実体が漏れています。');

  if (agent.body.status === 'decision') {
    const decision = agent.body.decision;
    const payload = {
      decisionId: decision.decisionId,
      tokens: agentTokens(decision),
      rationale: {
        action: decision.prompt,
        goal: 'E2Eで合法手の同期を確認する',
        evidence: 'APIが返した現在の合法手だけを使用',
        alternative: '非公開情報を使う選択は行わない',
      },
    };
    const applied = await api('/local-engine/codex-agent/decision', {
      method: 'POST',
      body: JSON.stringify(payload),
    }, connectionCode);
    assert(applied.status === 200 && applied.body.ok, `Codex判断失敗: ${JSON.stringify(applied.body)}`);
    codexDecisions += 1;
    if (!staleBody) {
      const beforeStaleRevision = applied.body.revision;
      const stale = await api('/local-engine/codex-agent/decision', {
        method: 'POST',
        body: JSON.stringify(payload),
      }, connectionCode);
      assert(stale.status === 409 && !stale.body.ok, '同じCodex判断の再送が拒否されませんでした。');
      assert(stale.body.revision === beforeStaleRevision, 'stale判断でrevisionが進みました。');
      staleBody = stale.body;
    }
  } else if (agent.body.status === 'waiting-human') {
    const state = await api(`/local-engine/codex-matches/${encodeURIComponent(matchId)}/state?since=${revision}`, { method: 'GET' });
    assert(state.status === 200 && state.body.ok, `Browser state失敗: ${JSON.stringify(state.body)}`);
    revision = state.body.revision;
    const prompt = state.body.view.prompts.find((item) => item.playerIndex === humanSeat && item.fields?.playbackOnly !== true);
    const command = prompt
      ? { type: 'resolvePrompt', payload: { id: prompt.id, result: humanResult(prompt) } }
      : { type: 'passTurn', payload: { playerIndex: humanSeat } };
    const applied = await api(`/local-engine/codex-matches/${encodeURIComponent(matchId)}/command`, {
      method: 'POST',
      body: JSON.stringify(command),
    });
    assert(applied.status === 200 && applied.body.ok, `人間操作失敗: ${JSON.stringify(applied.body)}`);
    revision = applied.body.revision;
    humanDecisions += 1;
  } else {
    throw new Error(`決着前に予期しない状態です: ${agent.body.status}`);
  }
}

assert(humanDecisions >= 1 && codexDecisions >= 1, '両席の判断を1回以上確認できませんでした。');
const conceded = await api(`/local-engine/codex-matches/${encodeURIComponent(matchId)}/command`, {
  method: 'POST',
  body: JSON.stringify({ type: 'concede', payload: { playerIndex: humanSeat } }),
});
assert(conceded.status === 200 && conceded.body.ok, `投了失敗: ${JSON.stringify(conceded.body)}`);

const summary = await api('/local-engine/codex-agent/summary', { method: 'GET' }, connectionCode);
assert(summary.status === 200 && summary.body.status === 'finished', `summary失敗: ${JSON.stringify(summary.body)}`);
assert(summary.body.replayFile, '完全版リプレイが保存されていません。');
assert(summary.body.decisions.length >= 1, 'Codex判断理由が保存されていません。');

process.stdout.write(`${JSON.stringify({ matchId, humanDecisions, codexDecisions, replayFile: summary.body.replayFile, staleError: staleBody?.error })}\n`);
