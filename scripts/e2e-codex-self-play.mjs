import fs from 'node:fs';

const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:8197';
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

async function api(path, init = {}, headers = {}) {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...headers, ...(init.headers ?? {}) },
  });
  const body = await response.json();
  return { status: response.status, body };
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function tokensFor(decision) {
  const end = decision.options.find((option) => option.kind === 'end');
  if (end && decision.minCount <= 1) return [end.token];
  return decision.options.slice(0, decision.minCount).map((option) => option.token);
}

const deck = sampleDeck();
const created = await api('/local-engine/codex-self-play', {
  method: 'POST',
  body: JSON.stringify({
    decks: [deck, deck],
    names: ['フーディンE2E', '対戦相手E2E'],
    alakazamSeat: 0,
  }),
});
assert(created.status === 200 && created.body.ok, `自己対戦を開始できません: ${JSON.stringify(created.body)}`);
const { matchId, coordinatorCode, seatCodes } = created.body;
assert(seatCodes[0] !== seatCodes[1], '二席へ同じ接続コードが発行されました。');
assert(coordinatorCode !== seatCodes[0] && coordinatorCode !== seatCodes[1], '管理コードが席コードと重複しました。');

const counts = [0, 0];
let staleError = '';
for (let step = 0; step < 120 && counts.some((count) => count < 1); step += 1) {
  let progressed = false;
  for (const seat of [0, 1]) {
    const headers = { 'x-cabt-self-play-seat': seatCodes[seat] };
    const state = await api('/local-engine/codex-self-play/seat-state', { method: 'GET' }, headers);
    assert(state.status === 200 && state.body.ok, `席${seat}のstate失敗: ${JSON.stringify(state.body)}`);
    assert(state.body.view.players[1 - seat].hand.every((card) => card.name === '未公開'), `席${seat}へ相手手札が漏れています。`);
    assert(state.body.view.players.every((player) => player.prizeContents === undefined), `席${seat}へサイド内容が漏れています。`);
    if (state.body.status !== 'decision') continue;
    const decision = state.body.decision;
    const payload = {
      decisionId: decision.decisionId,
      tokens: tokensFor(decision),
      rationale: {
        action: decision.prompt,
        goal: '自己対戦E2Eで合法手を進める',
        evidence: 'この席へ提示された合法手と公開情報だけを使用',
        alternative: '非公開情報を使う選択は行わない',
      },
    };
    const applied = await api('/local-engine/codex-self-play/seat-decision', {
      method: 'POST',
      body: JSON.stringify(payload),
    }, headers);
    assert(applied.status === 200 && applied.body.ok, `席${seat}の判断失敗: ${JSON.stringify(applied.body)}`);
    counts[seat] += 1;
    progressed = true;
    if (!staleError) {
      const stale = await api('/local-engine/codex-self-play/seat-decision', {
        method: 'POST',
        body: JSON.stringify(payload),
      }, headers);
      assert(stale.status === 409 && !stale.body.ok, '重複判断が拒否されませんでした。');
      assert(stale.body.revision === applied.body.revision, '重複判断でrevisionが進みました。');
      staleError = stale.body.error;
    }
    break;
  }
  if (!progressed) await new Promise((resolve) => setTimeout(resolve, 20));
}
assert(counts.every((count) => count >= 1), `両席の判断を確認できませんでした: ${counts.join(',')}`);

const concede = await api('/local-engine/codex-self-play/seat-concede', {
  method: 'POST',
  body: JSON.stringify({
    rationale: {
      action: '投了',
      goal: 'E2Eの終了保存を検証する',
      evidence: '両席の合法手送信を確認済み',
      alternative: '実戦は勝敗確定まで継続する',
    },
  }),
}, { 'x-cabt-self-play-seat': seatCodes[1] });
assert(concede.status === 200 && concede.body.ok, `投了失敗: ${JSON.stringify(concede.body)}`);

const summary = await api('/local-engine/codex-self-play/summary', { method: 'GET' }, {
  'x-cabt-self-play-coordinator': coordinatorCode,
});
assert(summary.status === 200 && summary.body.status === 'finished', `summary失敗: ${JSON.stringify(summary.body)}`);
assert(summary.body.replayFile, '自己対戦リプレイが保存されていません。');
assert(summary.body.decisions.length >= 3, '両席判断と投了が保存されていません。');
const serialized = JSON.stringify(summary.body);
assert(!serialized.includes(coordinatorCode) && seatCodes.every((code) => !serialized.includes(code)), 'サマリーへ認証コードが漏れています。');

process.stdout.write(`${JSON.stringify({
  matchId,
  seat0Decisions: counts[0],
  seat1Decisions: counts[1],
  replayFile: summary.body.replayFile,
  staleError,
})}\n`);
