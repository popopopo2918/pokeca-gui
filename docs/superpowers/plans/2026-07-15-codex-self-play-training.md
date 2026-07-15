# Codex自己対戦学習 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 二つの公平で独立したCodex操作席が、ゲーム開始から終了まで全選択を判断・記録できる自己対戦基盤を作り、第1戦の全手と学習結果を提示する。

**Architecture:** 通常GUI用の `CodexMatchManager` は変更せず、同じ `LocalEngineController` と `maskViewForCodex` を使う自己対戦専用管理クラスを追加する。各席は別のランダム接続コードで認証し、調整役は別の管理コードで終了後サマリーだけを取得する。試合後のメトリクスは保存済み判断記録と公開タイムラインから純粋関数で算出する。

**Tech Stack:** TypeScript 6、Node.js 24、CABT native bridge、Vitest 4、既存HTTPサーバー

## Global Constraints

- ゲーム開始から終了まで、プレイヤーが選ぶ全合法手はCodexが一手ずつ送信する。
- アップロード済みAIを起動・参照しない。
- 各席は相手の手札、サイド内容、山札順、非公開選択肢を取得しない。
- 通常GUI、通信対戦、既存Codex対戦のレイアウトと挙動を変更しない。
- 生成した学習ログは共有デプロイへ混入させない。
- `public/game-logs/logs.json` と既存の未追跡リプレイは編集・stageしない。
- テスト、typecheck、build、native E2Eが成功するまで完了扱いにしない。

---

### Task 1: 共通判断記録とメトリクス

**Files:**
- Modify: `src/engine/codexProtocol.ts`
- Create: `src/engine/selfPlayMetrics.ts`
- Test: `src/engine/selfPlayMetrics.test.ts`

**Interfaces:**
- Produces: `SelfPlayDecisionRecord`, `SelfPlayMetrics`, `calculateSelfPlayMetrics(view, decisions, alakazamSeat)`
- Consumes: `GameView`, `CodexDecisionRecord`,合法手の `kind`

- [ ] **Step 1: 失敗するメトリクステストを書く**

```ts
it('counts Alakazam player turns independently from global turns', () => {
  const decisions = [
    decision(0, 1, 'end'),
    decision(1, 1, 'end'),
    decision(0, 2, 'attack'),
  ];
  expect(calculateSelfPlayMetrics(finishedView(), decisions, 0)).toMatchObject({
    firstAttackPlayerTurn: 2,
    attackedByTurn2: true,
  });
});
```

- [ ] **Step 2: テストが未実装で失敗することを確認する**

Run: `npx vitest run src/engine/selfPlayMetrics.test.ts`

Expected: `Cannot find module './selfPlayMetrics'`

- [ ] **Step 3: 判断記録型と純粋関数を実装する**

```ts
export type SelfPlayDecisionRecord = CodexDecisionRecord & {
  seat: 0 | 1;
  playerTurn: number;
  prompt: string;
  selected: Array<Pick<CodexDecisionOption, 'kind' | 'label' | 'source' | 'target'>>;
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
```

攻撃は `selected.kind === 'attack'`、きぜつはフーディン席の攻撃決定から次のフーディン席決定までに増えた相手の取得済みサイド数または公開タイムラインのきぜつイベントで判定する。データ不足時は推測せず `undefined` にする。

- [ ] **Step 4: メトリクステストを通す**

Run: `npx vitest run src/engine/selfPlayMetrics.test.ts`

Expected: all tests pass

- [ ] **Step 5: コミットする**

```powershell
git add -- src/engine/codexProtocol.ts src/engine/selfPlayMetrics.ts src/engine/selfPlayMetrics.test.ts
git commit -m "feat: Codex自己対戦の判断指標を追加"
```

### Task 2: 二席自己対戦セッション

**Files:**
- Create: `src/engine/codexSelfPlay.ts`
- Test: `src/engine/codexSelfPlay.test.ts`
- Modify: `src/engine/codexMatches.ts`

**Interfaces:**
- Produces: `CodexSelfPlayManager.create`, `seatState`, `seatDecision`, `progress`, `summary`, `closeAll`, `prune`
- Consumes: `LocalEngineController.currentCodexDecision`, `applyCodexDecision`, `describeCodexDeck`, `currentCodexSearch`, `saveReplay`, `maskViewForCodex`

- [ ] **Step 1: 公平性と直列化の失敗テストを書く**

```ts
it('issues distinct codes and masks hidden information for both seats', async () => {
  const created = await manager.create({ decks, names: ['フーディン', '対戦相手'] });
  expect(created.seatCodes[0]).not.toBe(created.seatCodes[1]);
  expect(manager.seatState(created.seatCodes[0]).view.players[1].hand[0].name).toBe('未公開');
  expect(manager.seatState(created.seatCodes[1]).view.players[0].hand[0].name).toBe('未公開');
  expect(manager.seatState(created.seatCodes[0]).view.players[0].prizeContents).toBeUndefined();
});

it('applies one of duplicate decisions and returns the same revision', async () => {
  const body = { decisionId: 'd1', tokens: ['d1-o0'], rationale: rationale() };
  const [a, b] = await Promise.all([manager.seatDecision(code, body), manager.seatDecision(code, body)]);
  expect([a.ok, b.ok].filter(Boolean)).toHaveLength(1);
  expect(a.revision).toBe(b.revision);
});
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `npx vitest run src/engine/codexSelfPlay.test.ts`

Expected: `CodexSelfPlayManager` is missing

- [ ] **Step 3: 判断理由の正規化を既存管理クラスからexportする**

`codexMatches.ts` の500文字制限・空文字拒否を `export function sanitizeCodexRationale` とし、通常Codex対戦と自己対戦で共用する。通常対戦の応答を変えない。

- [ ] **Step 4: 自己対戦管理クラスを実装する**

```ts
type SelfPlayMatch = {
  id: string;
  coordinatorCode: string;
  seatCodes: [string, string];
  controller: Controller;
  decks: [unknown[], unknown[]];
  ownDecks: [CodexDeckEntry[], CodexDeckEntry[]];
  revision: number;
  queue: Promise<unknown>;
  decisions: SelfPlayDecisionRecord[];
  searchedCards: [CodexSearchSnapshot[], CodexSearchSnapshot[]];
  playerTurns: [number, number];
  observedActiveSeat?: 0 | 1;
  lastUsed: number;
  saved: boolean;
};
```

`startGame` は両席とも `control: 'self'` にする。`seatState` はコードから席を決め、`maskViewForCodex` を必ず通す。`seatDecision` は現在の合法手ラベルを送信前に保存し、成功後だけ判断記録へ追加する。席手番の開始を観測した時だけ `playerTurns[seat]` を増やす。

- [ ] **Step 5: 終了保存と管理コード制約をテストする**

`summary` は未終了なら409相当、誤った管理コードならnot found、終了後なら接続コードを含まない全判断・公開タイムライン・リプレイ・メトリクスを返すことを確認する。

- [ ] **Step 6: 自己対戦管理テストと既存管理テストを通す**

Run: `npx vitest run src/engine/codexSelfPlay.test.ts src/engine/codexMatches.test.ts src/engine/viewMask.test.ts`

Expected: all tests pass

- [ ] **Step 7: コミットする**

```powershell
git add -- src/engine/codexMatches.ts src/engine/codexSelfPlay.ts src/engine/codexSelfPlay.test.ts
git commit -m "feat: 二席のCodex自己対戦セッションを追加"
```

### Task 3: 自己対戦HTTP API

**Files:**
- Create: `src/engine/codexSelfPlayRoutes.ts`
- Test: `src/engine/codexSelfPlayRoutes.test.ts`
- Modify: `src/engine/server.ts`

**Interfaces:**
- Produces: `handleCodexSelfPlayRoute(request, manager)`
- Consumes: Task 2の `CodexSelfPlayManager`

- [ ] **Step 1: 各経路と認証ヘッダーの失敗テストを書く**

```ts
expect(await route('GET', '/local-engine/codex-self-play/seat-state', {
  seatCode: 'seat-a',
})).toEqual(expect.objectContaining({ handled: true, status: 200 }));

expect(await route('GET', '/local-engine/codex-self-play/summary', {
  coordinatorCode: 'coordinator',
})).toEqual(expect.objectContaining({ handled: true }));
```

- [ ] **Step 2: 未実装失敗を確認する**

Run: `npx vitest run src/engine/codexSelfPlayRoutes.test.ts`

Expected: module missing

- [ ] **Step 3: 純粋な経路ハンドラーを実装する**

席コードは `x-cabt-self-play-seat`、管理コードは `x-cabt-self-play-coordinator` からだけ読む。URL、レスポンス、サーバーログへコードを含めない。入力不正は400、古い局面は409、不明コードは404とする。

- [ ] **Step 4: serverへ通常controller作成より前に配線する**

`CodexSelfPlayManager` はサーバー単位で一つだけ作成し、shutdown時に `closeAll()` を呼ぶ。自己対戦APIへのアクセスで通常クライアントcontrollerを余分に作らない。

- [ ] **Step 5: 経路テスト・型検査を通す**

Run: `npx vitest run src/engine/codexSelfPlayRoutes.test.ts && npx tsc -p tsconfig.build.json`

Expected: exit 0

- [ ] **Step 6: コミットする**

```powershell
git add -- src/engine/codexSelfPlayRoutes.ts src/engine/codexSelfPlayRoutes.test.ts src/engine/server.ts
git commit -m "feat: Codex自己対戦APIを追加"
```

### Task 4: Native E2Eと学習ログ分離

**Files:**
- Create: `scripts/e2e-codex-self-play.mjs`
- Modify: `.gitignore`

**Interfaces:**
- Produces: 実サーバー上の自己対戦作成・両席決定・終了・サマリー検証
- Consumes: Task 3のHTTP API

- [ ] **Step 1: 学習成果物をignoreする**

`.gitignore` に `/training-results/` を追加し、公開ログやデプロイ入力へ混ぜない。

- [ ] **Step 2: E2Eを書く**

E2Eは二席コードが異なること、両席の相手手札が未公開であること、両席のサイド内容がないこと、各席が最低一手送ること、重複送信が一回だけ適用されること、最後に片方が投了して全判断付きサマリーを取得できることを確認する。

- [ ] **Step 3: nativeサーバーでE2Eを通す**

Run:

```powershell
$env:LOCAL_ENGINE_PORT='8197'
$env:CABT_ENGINE_MODE='native'
$env:PYTHON='python'
$env:CABT_SAMPLE_SUBMISSION_DIR='C:/dev/pokeca-ai/sample_submission'
npx tsx src/engine/server.ts
node scripts/e2e-codex-self-play.mjs
```

Expected: JSON summary with `seat0Decisions >= 1`, `seat1Decisions >= 1`, no hidden-data leak

- [ ] **Step 4: コミットする**

```powershell
git add -- .gitignore scripts/e2e-codex-self-play.mjs
git commit -m "test: Codex自己対戦のnative E2Eを追加"
```

### Task 5: 第1戦を全手動で実施する

**Files:**
- Modify after match: `playbook.md`
- Generate ignored: `training-results/<match-id>.json`

**Interfaces:**
- Consumes: 自己対戦API、既存フーディンプリセット、既存対戦相手プリセット
- Produces: 全手記録、試合メトリクス、playbook差分

- [ ] **Step 1: フーディンと最初の対戦相手でセッションを作る**

先攻・後攻はエンジンの選択肢を一方のCodexが判断する。都合の悪い初手でもリセットしない。

- [ ] **Step 2: 二つの独立操作席を開始する**

各席には自分の接続コードだけを渡す。各席は `playbook.md` を最初から読み、`seat-state` をポーリングし、自分の決定がある時だけ一手を送る。合法手が一つでも理由4項目を記録する。

- [ ] **Step 3: 終了まで一手ずつ継続する**

調整役は60秒以上無通信にせず進行を監視する。勝敗確定まで戦略的投了をさせない。技術エラー時だけ中断し、戦績から除外する。

- [ ] **Step 4: 全手記録と指標を検証する**

開始時選択を含む全エンジン決定に判断記録が一件対応すること、最初の攻撃・きぜつの自席ターン番号がリプレイと一致することを確認する。

- [ ] **Step 5: playbookを更新して読み直す**

試合別ログには結果、良かった判断、悪かった判断、次戦で検証する修正を追記する。単発仮説は集約ルールへ即昇格させない。更新後にファイルを最初から読み直す。

- [ ] **Step 6: ユーザーへ第1戦を提示する**

初期配置から終了まで、各手を「席の自ターン番号 / 局面 / 選択 / 目的 / 根拠 / 見送った案」で時系列表示する。最後に先攻後攻、初攻撃、初きぜつ、連続きぜつ、勝敗、playbook変更点を示す。

### Task 6: 全体検証

**Files:**
- Verify all modified source and tests

- [ ] **Step 1: 全テストを通す**

Run: `npx vitest run`

Expected: 0 failures, no skipped failing tests

- [ ] **Step 2: 型検査と本番ビルドを通す**

Run: `npx tsc -p tsconfig.build.json` and `npm run build`

Expected: exit 0

- [ ] **Step 3: native E2Eを再実行する**

Run: `node scripts/e2e-codex-self-play.mjs`

Expected: exit 0 and no hidden-data leak

- [ ] **Step 4: 差分と生成ログ混入を確認する**

Run: `git diff --check; git status --short`

Expected: `public/game-logs/logs.json` と既存リプレイ以外に意図しない変更がなく、`training-results/` が表示されない

