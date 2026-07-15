# Codex操作席 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 共有URLで人間対Codexを開始し、このCodexタスクが公平なプレイヤー視点と `playbook.md` を使って1判断ずつ操作できる専用席を追加する。

**Architecture:** CABTは両席manualで開始し、アップロードAIを完全に無効化する。共有サーバーの `CodexMatchManager` が人間ブラウザとCodex接続コードを別認証し、`LocalEngineController` が現在のCABT `select` を局面ID付きの不透明な合法手トークンへ変換する。Codexには専用マスク済みビューだけを返し、操作理由を判断記録としてリプレイへ保存する。

**Tech Stack:** Svelte 5、TypeScript 6、Node HTTP、Python CABTネイティブブリッジ、Vitest、Hugging Face Space。

## Global Constraints

- `playbook.md` を毎判断前に参照し、対戦終了後に対戦ログと照合して追記する。
- Codexへ相手手札、相手サイド、自分のサイド実体、山札順を渡さない。
- 自分のサイド落ちは、初期デッキリストと正当に確認できた情報からCodex自身が推定する。
- アップロードAIの `main.py`、公式サンプルAI、CABT既定AIをCodex席で実行しない。
- 古い局面ID・二重送信・手番外操作は状態を変えず拒否する。
- 既存の人間対AI、人間対人間オンライン、リプレイ、ログ出力、投了を維持する。
- 対戦画面の既存レイアウトを変更しない。Codexの判断説明はこのCodexタスク上で行う。
- 実対局E2Eと全検証後に共有URLへ反映する。

---

## File Structure

- Track: `playbook.md` — 対局前方針と対局後の自己改善ログ。
- Create: `src/engine/viewMask.ts` — 人間ルーム用・Codex用の情報マスク。
- Create: `src/engine/viewMask.test.ts` — 非公開情報漏えい回帰テスト。
- Modify: `src/engine/rooms.ts` — 共通マスクの利用。
- Create: `src/engine/codexProtocol.ts` — API DTO、判断根拠、合法手型。
- Modify: `src/lib/cabt/demoEngine.ts` — 既存の日本語プロンプト・選択肢ラベル関数を再利用可能にexport。
- Modify: `src/engine/localEngine.ts` — 現在のCABT選択を不透明トークン化し、局面ID付きで適用。
- Modify: `src/engine/localEngine.test.ts` — Codex席AI不使用、合法手、stale判断のテスト。
- Create: `src/engine/codexMatches.ts` — Codex対戦のライフサイクル、認証、キュー、ログ保存。
- Create: `src/engine/codexMatches.test.ts` — 参加者・手番・情報マスク・同時操作テスト。
- Modify: `src/engine/server.ts` — ブラウザ用・Codex用HTTPルート。
- Modify: `src/lib/game/httpClient.ts` — Codex対戦ブラウザAPIとGameCommandApi。
- Modify: `src/lib/game/httpClient.test.ts` — URL・ヘッダー・コマンド経路テスト。
- Create: `src/lib/game/controlMode.ts` — 対戦席構成の純粋な検証関数。
- Create: `src/lib/game/controlMode.test.ts` — Codex席と既存AI席の組合せ回帰テスト。
- Modify: `src/lib/components/ImportScreen.svelte` — 「Codex」選択と開始条件。
- Modify: `src/App.svelte` — Codex対戦作成、接続コード表示、revisionポーリング、操作制限。
- Modify: `src/lib/components/GameStatus.svelte` — 既存領域内の「Codex操作待ち」表示。
- Modify: `src/lib/game/types.ts` — Codex判断記録付きリプレイメタデータ型。
- Modify: `src/engine/localEngine.ts` — `saveReplay(metadata)`。
- Create: `scripts/e2e-codex-match.mjs` — 人間クライアントとCodexクライアントの実対局E2E。

### Task 1: 共通情報マスクを抽出しCodex視点を固定する

**Files:**
- Create: `src/engine/viewMask.ts`
- Create: `src/engine/viewMask.test.ts`
- Modify: `src/engine/rooms.ts`

**Interfaces:**
- Produces: `maskViewForSeat(view: GameView, seat: number): GameView`
- Produces: `maskViewForCodex(view: GameView, seat: number): GameView`
- Produces: `maskTimelineEvent(event, opponent): ActionTimelineEvent`

- [ ] **Step 1: Codex視点から非公開情報が消える失敗テストを書く**

```ts
import { describe, expect, it } from 'vitest';
import type { GameView } from '../lib/game/types';
import { maskViewForCodex, maskViewForSeat } from './viewMask';

const view = (): GameView => ({
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
    active: { ownerIndex: index, slot: 'active', index: 0, target: { player: 2, slot: 1, index: 0 }, empty: true, cards: [], damage: 0, hp: 0, retreat: [], energy: [], tools: [], specialConditions: [] },
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
});

describe('view masks', () => {
  it('Codexには自分の手札だけを見せ、双方のサイド実体を隠す', () => {
    const masked = maskViewForCodex(view(), 1);
    expect(masked.players[1].hand[0].name).toBe('hand-1');
    expect(masked.players[0].hand[0].name).toBe('未公開');
    expect(masked.players[0].prizeContents).toBeUndefined();
    expect(masked.players[1].prizeContents).toBeUndefined();
  });

  it('既存ルームでは自分のサイド確認機能を維持する', () => {
    const masked = maskViewForSeat(view(), 1);
    expect(masked.players[1].prizeContents?.[0].name).toBe('prize-1');
    expect(masked.players[0].prizeContents).toBeUndefined();
  });
});
```

- [ ] **Step 2: 新規module未実装で失敗することを確認する**

Run: `npx vitest run src/engine/viewMask.test.ts`

Expected: module not foundでFAIL。

- [ ] **Step 3: rooms.tsのマスクを抽出しCodex用差分を追加する**

```ts
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

function maskPrompt(prompt: PromptView, seat: number): PromptView {
  if (prompt.playerIndex === seat || prompt.fields?.playbackOnly === true) return prompt;
  const { cardList: _cards, cards: _cards2, values: _values, prizes: _prizes, cabtSelect: _select, ...rest } = prompt.fields ?? {};
  return { ...prompt, fields: { ...rest, masked: true } };
}

export function maskTimelineEvent(event: ActionTimelineEvent, opponent: number): ActionTimelineEvent {
  if (event.playerIndex !== opponent) return event;
  const params = (event.params ?? {}) as Record<string, unknown>;
  const toHand = Number(params.toArea) === CabtAreaType.HAND;
  const isDraw = event.kind === 'Draw';
  if (!isDraw && !toHand) return event;
  const actor = `プレイヤー${opponent + 1}`;
  const message = isDraw ? `${actor}はカードを引いた。` : `${actor}はカードを手札に加えた。`;
  const { cardId: _cardId, serial: _serial, ...maskedParams } = params;
  return { ...event, message, params: maskedParams };
}

export function maskViewForCodex(view: GameView, seat: number): GameView {
  const masked = maskViewForSeat(view, seat);
  return {
    ...masked,
    players: masked.players.map((player) => ({ ...player, prizeContents: undefined })),
  };
}
```

`rooms.ts` はこのmoduleから `maskViewForSeat` をimportする。`PromptView`、`ActionTimelineEvent`、`CabtAreaType` のimportも `viewMask.ts` へ移す。

- [ ] **Step 4: 新規テストと既存テストを実行する**

Run: `npx vitest run src/engine/viewMask.test.ts src/engine/rooms.test.ts`

Expected: all tests passed。

- [ ] **Step 5: Task 1をコミットする**

```bash
git add src/engine/viewMask.ts src/engine/viewMask.test.ts src/engine/rooms.ts
git commit -m "refactor: 対戦ビューの情報マスクを共通化"
```

### Task 2: CABT合法手を局面ID付きトークンへ変換する

**Files:**
- Create: `src/engine/codexProtocol.ts`
- Modify: `src/lib/cabt/demoEngine.ts`
- Modify: `src/engine/localEngine.ts`
- Modify: `src/engine/localEngine.test.ts`

**Interfaces:**
- Produces: `CodexDecisionOption`, `CodexEngineDecision`, `CodexRationale`
- Produces: `LocalEngineController.currentCodexDecision(playerIndex): CodexEngineDecision | null`
- Produces: `LocalEngineController.applyCodexDecision(playerIndex, decisionId, tokens): Promise<EngineResponse>`
- Produces: `LocalEngineController.describeCodexDeck(cards): CodexDeckEntry[]`
- Produces: `LocalEngineController.currentCodexSearch(playerIndex): CodexSearchSnapshot | null`

- [ ] **Step 1: 合法手とstale拒否の失敗テストを書く**

```ts
it('exposes only opaque tokens and rejects a stale Codex decision', async () => {
  const engine = new LocalEngineController() as any;
  engine.sessionId = 'session';
  engine.observationVersion = 7;
  engine.observation = observation({
    yourIndex: 1,
    select: selectData({
      minCount: 1,
      maxCount: 1,
      option: [{ type: CabtOptionType.END }],
    }),
  });

  const decision = engine.currentCodexDecision(1);
  expect(decision).toMatchObject({ playerIndex: 1, minCount: 1, maxCount: 1 });
  expect(decision.options[0]).toMatchObject({ token: 'd7-o0', kind: 'end', label: 'ターンエンド' });
  expect(decision.options[0]).not.toHaveProperty('index');

  await expect(engine.applyCodexDecision(1, 'd6', ['d6-o0']))
    .resolves.toMatchObject({ ok: false, error: '局面が更新されています。最新の合法手を取得してください。' });
});

it('does not expose a decision to the non-acting seat', () => {
  const engine = new LocalEngineController() as any;
  engine.observationVersion = 1;
  engine.observation = observation({ yourIndex: 1 });
  expect(engine.currentCodexDecision(0)).toBeNull();
});
```

- [ ] **Step 2: currentCodexDecision未実装で失敗することを確認する**

Run: `npx vitest run src/engine/localEngine.test.ts -t "Codex decision|non-acting"`

Expected: method not foundでFAIL。

- [ ] **Step 3: Protocol型と不透明トークン変換を実装する**

`src/engine/codexProtocol.ts`:

```ts
export type CodexDecisionKind = 'play' | 'attach' | 'evolve' | 'ability' | 'attack' | 'retreat' | 'end' | 'yes' | 'no' | 'number' | 'card' | 'other';

export type CodexDecisionOption = {
  token: string;
  kind: CodexDecisionKind;
  label: string;
  source?: string;
  target?: string;
};

export type CodexEngineDecision = {
  decisionId: string;
  playerIndex: number;
  prompt: string;
  minCount: number;
  maxCount: number;
  options: CodexDecisionOption[];
};

export type CodexDeckEntry = { id: number; name: string; count: number };

export type CodexSearchSnapshot = {
  decisionId: string;
  prompt: string;
  cards: Array<{ id: number; name: string }>;
};

export type CodexRationale = {
  action: string;
  goal: string;
  evidence: string;
  alternative: string;
};
```

`LocalEngineController` は `applyBridgeResponse` と `concede` で `observationVersion += 1` する。`decisionId` は `d${observationVersion}`、option tokenは `${decisionId}-o${optionIndex}` とする。ラベルは既存の日本語カード名・攻撃名・盤面所有者ラベルを使い、optionの生インデックスをDTOへ含めない。

`src/lib/cabt/demoEngine.ts` の既存 `optionLabel`、`optionOwnerLabel`、`cabtSelectMessage` をexportし、GUIとCodex APIが同一の日本語表現を使う。`codexOption` は次の対応表でkindを決める。

```ts
const CODEX_KIND_BY_OPTION: Record<number, CodexDecisionKind> = {
  [CabtOptionType.PLAY]: 'play',
  [CabtOptionType.ATTACH]: 'attach',
  [CabtOptionType.EVOLVE]: 'evolve',
  [CabtOptionType.ABILITY]: 'ability',
  [CabtOptionType.ATTACK]: 'attack',
  [CabtOptionType.RETREAT]: 'retreat',
  [CabtOptionType.END]: 'end',
  [CabtOptionType.YES]: 'yes',
  [CabtOptionType.NO]: 'no',
  [CabtOptionType.NUMBER]: 'number',
  [CabtOptionType.CARD]: 'card',
};

private codexOption(decisionId: string, option: CabtOption, index: number): CodexDecisionOption {
  return {
    token: `${decisionId}-o${index}`,
    kind: CODEX_KIND_BY_OPTION[option.type] ?? 'other',
    label: optionLabel(option, this.dataMaps, this.observation!, this.observation!.select?.context),
    target: optionOwnerLabel(option, this.observation!) ?? undefined,
  };
}
```

```ts
currentCodexDecision(playerIndex: number): CodexEngineDecision | null {
  const current = this.observation?.current;
  const select = this.observation?.select;
  if (!current || !select || current.result >= 0 || current.yourIndex !== playerIndex) return null;
  const decisionId = `d${this.observationVersion}`;
  return {
    decisionId,
    playerIndex,
    prompt: cabtSelectMessage(select, this.dataMaps, this.observation),
    minCount: select.minCount,
    maxCount: select.maxCount,
    options: select.option.map((option, index) => this.codexOption(decisionId, option, index)),
  };
}

async applyCodexDecision(playerIndex: number, decisionId: string, tokens: string[]): Promise<EngineResponse> {
  const current = this.currentCodexDecision(playerIndex);
  if (!current || current.decisionId !== decisionId) {
    return { ok: false, error: '局面が更新されています。最新の合法手を取得してください。', view: this.view() };
  }
  const prefix = `${decisionId}-o`;
  const indexes = tokens.map((token) => token.startsWith(prefix) ? Number(token.slice(prefix.length)) : NaN);
  if (indexes.some((index) => !Number.isInteger(index) || index < 0 || index >= current.options.length)) {
    return { ok: false, error: '合法手トークンが正しくありません。', view: this.view() };
  }
  if (new Set(indexes).size !== indexes.length || indexes.length < current.minCount || indexes.length > current.maxCount) {
    return { ok: false, error: `選択は${current.minCount}〜${current.maxCount}個にしてください。`, view: this.view() };
  }
  return this.applySelection(indexes);
}
```

初期デッキは任意入力のまま保持せず、`resolveDeck` で60枚の数値IDへ正規化してから種類ごとに集約する。

```ts
describeCodexDeck(cards: unknown[]): CodexDeckEntry[] {
  const ids = resolveDeck(cards, 'Codexのデッキ');
  const counts = new Map<number, number>();
  for (const id of ids) counts.set(id, (counts.get(id) ?? 0) + 1);
  return [...counts.entries()].map(([id, count]) => ({
    id,
    name: JA_NAME_BY_ID.get(id) ?? `カード${id}`,
    count,
  }));
}

currentCodexSearch(playerIndex: number): CodexSearchSnapshot | null {
  const decision = this.currentCodexDecision(playerIndex);
  const select = this.observation?.select;
  if (!decision || !select) return null;
  const deckOptions = select.option.filter((option) =>
    option.area === CabtAreaType.DECK && Number.isInteger(option.cardId));
  if (!deckOptions.length) return null;
  return {
    decisionId: decision.decisionId,
    prompt: decision.prompt,
    cards: deckOptions.map((option) => ({
      id: Number(option.cardId),
      name: JA_NAME_BY_ID.get(Number(option.cardId)) ?? `カード${Number(option.cardId)}`,
    })),
  };
}
```

- [ ] **Step 4: stale、手番外、選択数、重複、範囲外token、デッキ正規化、デッキ確認情報のテストを通す**

Run: `npx vitest run src/engine/localEngine.test.ts`

Expected: all tests passed。

- [ ] **Step 5: Task 2をコミットする**

```bash
git add src/engine/codexProtocol.ts src/lib/cabt/demoEngine.ts src/engine/localEngine.ts src/engine/localEngine.test.ts
git commit -m "feat: Codex向け合法手プロトコルを追加"
```

### Task 3: Codex対戦のライフサイクルと公平な状態APIを実装する

**Files:**
- Create: `src/engine/codexMatches.ts`
- Create: `src/engine/codexMatches.test.ts`

**Interfaces:**
- Produces: `createCodexMatch(clientId, body)`
- Produces: `codexBrowserState(clientId, matchId, since)`
- Produces: `codexBrowserCommand(clientId, matchId, command)`
- Produces: `codexAgentState(connectionCode)`
- Produces: `codexAgentDecision(connectionCode, body)`
- Produces: `codexMatchSummary(connectionCode)`
- Produces: `leaveCodexMatch(clientId, matchId)`

- [ ] **Step 1: AI不使用・情報マスク・手番制限の失敗テストを書く**

`LocalEngineController` をfactory injectionできるよう、manager constructorへ `controllerFactory` を受ける。テストfakeは開始payload、現在ビュー、Codex decision適用回数を記録する。

```ts
it('starts both CABT seats manual and returns a fair Codex view', async () => {
  const fake = createFakeController();
  const manager = new CodexMatchManager(() => fake as never);
  const created = await manager.create('human-client', {
    decks: [Array(60).fill(1), Array(60).fill(2)],
    codexSeat: 1,
  });

  expect(fake.startedWith.player1.control).toBe('self');
  expect(fake.startedWith.player2.control).toBe('self');
  const agent = manager.agentState(created.connectionCode!);
  expect(agent.status).toBe('decision');
  expect(agent.view.players[0].hand[0].name).toBe('未公開');
  expect(agent.view.players[1].hand[0].name).not.toBe('未公開');
  expect(agent.view.players[0].prizeContents).toBeUndefined();
  expect(agent.view.players[1].prizeContents).toBeUndefined();
  expect(agent.ownDeck).toEqual([{ id: 2, name: 'テストカード2', count: 60 }]);
  expect(manager.browserState('human-client', created.matchId!, 0).codexConnected).toBe(true);
});

it('rejects human commands during the Codex turn', async () => {
  const { manager, created } = await startedMatch({ actingSeat: 1, codexSeat: 1 });
  await expect(manager.browserCommand('human-client', created.matchId!, { type: 'passTurn' }))
    .resolves.toMatchObject({ ok: false, error: 'Codexの操作待ちです。' });
});

it('serializes duplicate Codex decisions and applies only one', async () => {
  const { manager, created, fake } = await startedMatch({ actingSeat: 1, codexSeat: 1 });
  const body = { decisionId: 'd1', tokens: ['d1-o0'], rationale: rationale() };
  const [first, second] = await Promise.all([
    manager.agentDecision(created.connectionCode!, body),
    manager.agentDecision(created.connectionCode!, body),
  ]);
  expect([first.ok, second.ok].filter(Boolean)).toHaveLength(1);
  expect(fake.appliedDecisions).toHaveLength(1);
});

it('remembers only deck cards exposed by a legitimate Codex search prompt', async () => {
  const { manager, created, fake } = await startedMatch({ actingSeat: 1, codexSeat: 1 });
  fake.searchSnapshot = {
    decisionId: 'd1',
    prompt: '山札からポケモンを選んでください。',
    cards: [{ id: 101, name: 'ケーシィ' }, { id: 102, name: 'ユンゲラー' }],
  };
  const agent = manager.agentState(created.connectionCode!);
  expect(agent.knowledge.searches).toEqual([fake.searchSnapshot]);
  expect(agent).not.toHaveProperty('prizeContents');
});
```

- [ ] **Step 2: module未実装で失敗することを確認する**

Run: `npx vitest run src/engine/codexMatches.test.ts`

Expected: module not foundでFAIL。

- [ ] **Step 3: managerの最小実装を追加する**

```ts
import { randomBytes } from 'node:crypto';

type CodexMatch = {
  id: string;
  connectionCode: string;
  humanClientId: string;
  codexSeat: 0 | 1;
  decks: [unknown[], unknown[]];
  ownDeck: CodexDeckEntry[];
  controller: LocalEngineController;
  sessionId: string;
  revision: number;
  frames: Array<{ rev: number; view: GameView }>;
  queue: Promise<unknown>;
  decisions: CodexDecisionRecord[];
  searchedCards: CodexSearchSnapshot[];
  connectedAt?: number;
  lastUsed: number;
  saved: boolean;
};

const connectionCode = () => randomBytes(12).toString('base64url');
const matchId = () => randomBytes(8).toString('hex');
```

作成時は60枚×2、`codexSeat` 0/1を検証し、`describeCodexDeck` を両デッキに実行してカードID解決と60枚検証を済ませる。両player payloadを `control: 'self'` で `LocalEngineController.handle({type:'startGame'})` へ渡し、アップロードAIのパスやagent IDは渡さない。`ownDeck` はCodex側の `describeCodexDeck` 集約結果を保持する。

Agent stateは最初の取得時に `connectedAt = Date.now()` を設定し、`maskViewForCodex` を通したview、`ownDeck`、`currentCodexDecision`、`knowledge.searches` を返す。`currentCodexSearch` が返したsnapshotだけを `decisionId` 単位で重複なく `searchedCards` へ追加する。実際のサイド、山札順、相手手札をknowledgeへ追加しない。Browser stateには接続コードを再送せず `codexConnected: Boolean(connectedAt)` だけを返す。

Browser commandとAgent decisionは同じqueueへ直列化し、処理直前にもacting seatとdecisionIdを再確認する。判断適用後はcontrollerのsequence/viewをrevision frameへ追加し、ブラウザポーリングへ渡す。

接続コードはレスポンス以外へ書き出さず、60分idleでcontrollerをcloseする。最大8対戦とし、既存room/controller上限と同等にメモリを制限する。

- [ ] **Step 4: managerテストをすべて通す**

Run: `npx vitest run src/engine/codexMatches.test.ts`

Expected: all tests passed。

- [ ] **Step 5: Task 3をコミットする**

```bash
git add src/engine/codexMatches.ts src/engine/codexMatches.test.ts
git commit -m "feat: Codex対戦セッション管理を追加"
```

### Task 4: ブラウザ用・Codex用HTTPルートを追加する

**Files:**
- Modify: `src/engine/server.ts`
- Modify: `src/lib/game/httpClient.ts`
- Modify: `src/lib/game/httpClient.test.ts`

**Interfaces:**
- Browser routes: `/local-engine/codex-matches/:id/{state,command,leave,save-replay}`
- Agent routes: `/local-engine/codex-agent/{state,decision,summary}`
- Header: `x-cabt-codex-code`
- Produces: `codexMatchApi`, `createCodexHumanGameApi`

- [ ] **Step 1: ブラウザHTTPクライアントが専用URLと既存client IDヘッダーを使う失敗テストを書く**

`global.fetch = vi.fn()` でレスポンスを返し、次を検証する。

```ts
it('creates a Codex match without putting credentials in the URL', async () => {
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ ok: true, matchId: 'm1', connectionCode: 'secret-code' })));
  await codexMatchApi.create([Array(60).fill('1'), Array(60).fill('2')], 1);
  const [url, init] = vi.mocked(fetch).mock.calls[0];
  expect(url).toBe('/local-engine/codex-matches');
  expect((init?.headers as Record<string, string>)['x-cabt-client']).toBeTruthy();
  expect(String(url)).not.toContain('secret-code');
});
```

- [ ] **Step 2: client API未実装で失敗することを確認する**

Run: `npx vitest run src/lib/game/httpClient.test.ts -t "Codex match"`

Expected: `codexMatchApi` 未定義でFAIL。

- [ ] **Step 3: server routesとbrowser APIを実装する**

```ts
async function codexMatchFetch(path: string, init?: RequestInit): Promise<any> {
  const response = await fetch(`/local-engine/codex-matches${path}`, {
    ...init,
    headers: { ...jsonHeaders(), ...(init?.headers ?? {}) },
  });
  return response.json();
}

export const codexMatchApi = {
  create(decks: [string[], string[]], codexSeat: 0 | 1) {
    return codexMatchFetch('', { method: 'POST', body: JSON.stringify({ decks, codexSeat }) });
  },
  state(matchId: string, since: number) {
    return codexMatchFetch(`/${encodeURIComponent(matchId)}/state?since=${since}`);
  },
  command(matchId: string, type: string, payload?: unknown) {
    return codexMatchFetch(`/${encodeURIComponent(matchId)}/command`, { method: 'POST', body: JSON.stringify({ type, payload }) });
  },
  leave(matchId: string) {
    return codexMatchFetch(`/${encodeURIComponent(matchId)}/leave`, { method: 'POST', body: '{}' });
  },
};
```

`server.ts` は `/local-engine/codex-agent/*` だけで `x-cabt-codex-code` を読み、値をログへ出さずmanagerへ渡す。Agent stateはGET、decisionはPOST、summaryはGET。不正・期限切れコードは404、stale・手番外は409、token・rationale形式エラーは400、成功は200とする。接続コードはURL、リプレイ、通常ログへ含めない。

- [ ] **Step 4: HTTPテストとserver TypeScript型検査を通す**

Run: `npx vitest run src/lib/game/httpClient.test.ts src/engine/codexMatches.test.ts && npx tsc -p tsconfig.build.json`

Expected: exit 0。

- [ ] **Step 5: Task 4をコミットする**

```bash
git add src/engine/server.ts src/lib/game/httpClient.ts src/lib/game/httpClient.test.ts
git commit -m "feat: Codex対戦APIを公開"
```

### Task 5: 対戦設定にCodex席を追加して共有GUIを同期する

**Files:**
- Create: `src/lib/game/controlMode.ts`
- Create: `src/lib/game/controlMode.test.ts`
- Modify: `src/lib/game/httpClient.ts`
- Modify: `src/lib/components/ImportScreen.svelte`
- Modify: `src/App.svelte`
- Modify: `src/lib/components/GameStatus.svelte`

**Interfaces:**
- `PlayerControl = 'self' | 'agent' | 'codex'`
- `CodexMatchClientState = { matchId: string; connectionCode: string; humanSeat: number; codexSeat: number }`
- Browser poll interval: 500ms while match active.

- [ ] **Step 1: PlayerControlと開始条件の失敗テストを書く**

`src/lib/game/controlMode.test.ts` で `['self','codex']` と `['codex','self']` を許可し、`['codex','codex']` と `['agent','codex']` を拒否するテストを書く。`src/lib/game/controlMode.ts` へ次の純粋関数を置き、`httpClient.ts` は型をimportしてre-exportする。

```ts
export type PlayerControl = 'self' | 'agent' | 'codex';

export function validateControls(controls: [PlayerControl, PlayerControl]): string | null {
  const codexCount = controls.filter((control) => control === 'codex').length;
  if (codexCount > 1) return 'Codexは片方のプレイヤーだけに設定してください。';
  if (codexCount === 1 && controls.some((control) => control === 'agent')) {
    return 'Codex対戦のもう一方は「自分」にしてください。';
  }
  return null;
}
```

- [ ] **Step 2: 純粋関数テストが未実装で失敗することを確認する**

Run: `npx vitest run src/lib/game/controlMode.test.ts`

Expected: FAIL。

- [ ] **Step 3: ImportScreenへCodexタブを追加する**

両playerのcontrol tabsへ次を追加する。

```svelte
<button
  type="button"
  role="tab"
  aria-selected={playerControl === 'codex'}
  class:active={playerControl === 'codex'}
  disabled={busy}
  onclick={() => setPlayerControl(playerIndex, 'codex')}
>Codex</button>
```

Codex選択時はAI selectを表示しない。開始ボタンはcontrol構成エラーまたはagent未選択時だけdisableする。デッキ選択は既存のまま両席に表示する。

- [ ] **Step 4: AppへCodex対戦作成・ポーリングを追加する**

`startGame` はCodex席がある場合だけ `localGameApi.start` を使わず `codexMatchApi.create` を呼ぶ。成功後は `commandApi` を `createCodexHumanGameApi(matchId)` に切り替え、人間席を手前へ固定し、500ms intervalでrevision差分を `gameSessionStore.applyExternal` へ渡す。

対戦開始後も接続コードを確認できるよう、`GameStatus.svelte` の既存status領域へ次のoptional propsを追加する。新しいパネルや盤面領域は作らない。

```ts
codexConnectionCode?: string;
codexConnected?: boolean;
onCopyCodexCode?: () => void;
```

同コンポーネントの現在の状態表示の末尾へ、`codexConnectionCode` がある時だけ次を出す。

```svelte
<span class="codex-connection" aria-live="polite">
  Codex: {codexConnected ? '接続済み' : '接続待ち'}
  <button type="button" onclick={onCopyCodexCode}>コードをコピー</button>
</span>
```

`App.svelte` は作成直後の `connectionCode` をローカルstateにだけ保持し、`navigator.clipboard.writeText(codexMatch.connectionCode)` を上のcallbackへ渡す。ポーリングの `codexConnected` をpropsへ反映する。待機中の補助文は「コードをコピーしてCodexタスクへ送ってください。」とする。

Codex手番では既存の盤面操作を `isSelfControlled` で拒否し、既存の相手操作待ち表示を「Codexの操作待ち…」へ切り替える。投了とメニューへ戻る操作は維持する。

- [ ] **Step 5: 対象テスト、型検査、buildを実行する**

Run: `npx vitest run src/lib/game/controlMode.test.ts src/lib/game/httpClient.test.ts && npx tsc -p tsconfig.build.json && npm run build`

Expected: exit 0。

- [ ] **Step 6: Task 5をコミットする**

```bash
git add src/lib/game/controlMode.ts src/lib/game/controlMode.test.ts src/lib/game/httpClient.ts src/lib/components/ImportScreen.svelte src/App.svelte src/lib/components/GameStatus.svelte
git commit -m "feat: 共有GUIにCodex操作席を追加"
```

### Task 6: 判断根拠と対戦後サマリーを完全版ログへ保存する

**Files:**
- Modify: `src/lib/game/types.ts`
- Modify: `src/engine/localEngine.ts`
- Modify: `src/engine/codexMatches.ts`
- Modify: `src/engine/codexMatches.test.ts`
- Track: `playbook.md`

**Interfaces:**
- `saveReplay(metadata?: Record<string, unknown>): SaveReplayResponse`
- `CodexDecisionRecord = { revision, turn, decisionId, tokens, rationale, createdAt }`
- Agent summary returns `{ result, replayFile, decisions, publicTimeline }`

- [ ] **Step 1: rationaleの保存と長さ制限の失敗テストを書く**

```ts
it('stores sanitized rationale and includes it in the final replay metadata', async () => {
  const { manager, created, fake } = await startedMatch({ actingSeat: 1, codexSeat: 1 });
  await manager.agentDecision(created.connectionCode!, {
    decisionId: 'd1',
    tokens: ['d1-o0'],
    rationale: {
      action: 'ノコッチをベンチに出す',
      goal: '次の番のにげあしドローを準備する',
      evidence: 'ベンチに空きがあり、手札にノココッチがある',
      alternative: '4体目のケーシィはプレイブック上限を超えるため見送る',
    },
  });
  fake.finish(1);
  await manager.flushFinished(created.matchId!);
  expect(fake.savedMetadata.codexDecisions[0].rationale.goal).toContain('にげあしドロー');
  expect(manager.summary(created.connectionCode!).decisions).toHaveLength(1);
});
```

- [ ] **Step 2: metadata未対応で失敗することを確認する**

Run: `npx vitest run src/engine/codexMatches.test.ts -t "rationale"`

Expected: saved metadataがundefinedでFAIL。

- [ ] **Step 3: replay metadataとsummaryを実装する**

`saveReplay(metadata = {})` は既存replay objectへ次を追加する。

```ts
const replay = {
  visualize: this.replayFrames,
  environment: {
    id,
    title: name,
    info: {
      TeamNames: this.replayPlayerLabels,
      ...metadata,
    },
  },
};
```

Rationale各項目は文字列化し、前後空白を除き、各500文字までに制限する。接続コードはmetadataへ含めない。決着時の自動保存に `codexDecisions` を渡し、summary APIは同じ記録と公開timeline、結果、リプレイファイル名を返す。

- [ ] **Step 4: `playbook.md` を追跡対象へ加える**

内容は変更せず `git add playbook.md` する。以後、各対戦終了後にこのCodexタスクがログを確認し、`反省ログ` 末尾へ追記する。

- [ ] **Step 5: 対象テストを実行する**

Run: `npx vitest run src/engine/codexMatches.test.ts src/engine/localEngine.test.ts`

Expected: all tests passed。

- [ ] **Step 6: Task 6をコミットする**

```bash
git add playbook.md src/lib/game/types.ts src/engine/localEngine.ts src/engine/codexMatches.ts src/engine/codexMatches.test.ts
git commit -m "feat: Codexの判断記録と対局後学習基盤を追加"
```

### Task 7: 共有版相当の実対局E2Eを追加する

**Files:**
- Create: `scripts/e2e-codex-match.mjs`

**Interfaces:**
- Consumes: `http://127.0.0.1:8196`
- Produces: one browser human client, one Codex agent HTTP client, completed replay summary.

- [ ] **Step 1: Codex接続から決着までの失敗E2Eを書く**

```js
// 1. POST /local-engine/codex-matches with two valid 60-card decks and codexSeat=1
// 2. Assert browser response contains matchId/connectionCode but no opponent hidden cards
// 3. GET /local-engine/codex-agent/state with x-cabt-codex-code
// 4. Assert both prizeContents absent and human hand masked
// 5. Loop: if status=decision, choose legal tokens within min/max and POST one decision with rationale
// 6. If waiting-human, send exactly one legal human command through browser route
// 7. Concede from the human seat after both sides have completed at least one decision
// 8. GET summary and assert one complete replay file plus Codex rationale records
// 9. Reuse the first decisionId and assert 409/stale without a revision increase
```

- [ ] **Step 2: API/UI未完成状態では失敗することを確認する**

Run: `node scripts/e2e-codex-match.mjs`

Expected: route not foundまたはassertion failure。

- [ ] **Step 3: 完成実装でE2Eを実行する**

Run: `node scripts/e2e-codex-match.mjs`

Expected: exit 0、human/Codex各1判断以上、stale拒否、summary/replay保存成功。

- [ ] **Step 4: Task 7をコミットする**

```bash
git add scripts/e2e-codex-match.mjs
git commit -m "test: Codex対戦の実対局E2Eを追加"
```

### Task 8: 全検証・共有URLデプロイ・初回対局準備

**Files:**
- No production file changes expected unless verification finds a defect.

- [ ] **Step 1: 全Vitestを実行する**

Run: `npx vitest run`

Expected: all tests passed, 0 failed。

- [ ] **Step 2: TypeScript型検査を実行する**

Run: `npx tsc -p tsconfig.build.json`

Expected: exit 0。

- [ ] **Step 3: 本番ビルドを実行する**

Run: `npm run build`

Expected: exit 0。

- [ ] **Step 4: 2本の実ブラウザE2Eを実行する**

Run: `node scripts/e2e-input-latency.mjs && node scripts/e2e-codex-match.mjs`

Expected: both exit 0。入力遅延閾値、非公開情報マスク、stale拒否、リプレイ保存を確認。

- [ ] **Step 5: 変更範囲をレビューする**

Run: `git diff 3c64f3e..HEAD --check && git diff 3c64f3e..HEAD --stat`

Expected: whitespace errorsなし。カードデータ、CABTカード効果、対戦レイアウトの意図しない変更なし。`public/game-logs` のユーザーファイルをコミットしていない。

- [ ] **Step 6: 共有URLへデプロイする**

Run: `& 'C:\Program Files\Git\bin\bash.exe' ../scripts/deploy_hf.sh`

Expected: Hugging Face Space push成功。接続コードや認証情報を出力・コミットしない。

- [ ] **Step 7: Spaceのbuild完了後に共有URLのhealthと画面を確認する**

Run: shared URLのトップページと `/local-engine/codex-matches` を実際に利用し、Codex選択、対戦作成、接続コード表示を確認する。

Expected: https://kahtgf-pokeca-cabt.hf.space でCodex席が選べる。

- [ ] **Step 8: ユーザーへ初回対局を案内する**

人間が共有URLで「自分 vs Codex」を開始し、表示された接続コードをこのタスクへ送る。受領後、このCodexタスクは `playbook.md` を再読し、agent stateをポーリングして1手ずつ操作・説明する。決着後はsummaryと完全ログを読み、`playbook.md` を更新してコミットする。
