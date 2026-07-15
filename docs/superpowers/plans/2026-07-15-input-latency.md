# 対戦操作レイテンシ改善 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 人間が行ったカード使用・選択・ボタン操作には650msの対戦再生待ちを適用せず、相手AI・オンライン相手・Codexの行動だけを従来どおり1手ずつ再生する。

**Architecture:** `EngineResponse` の各sequenceフレームへ `instant` / `animate` の再生指定を付与する。`LocalEngineController` は直接コマンド由来の最初の観測を `instant`、CABTの自動AI進行を `animate` として返し、人間同士の遠隔ルームではコマンド送信者への応答はその指定を維持、相手側のポーリング差分はすべて `animate` にする。`GameStore` は指定が `instant` のフレームを待機なしで適用し、既存のplaybackOnly確認は維持する。

**Tech Stack:** TypeScript 6、Svelte 5 runes、Vitest 4、Node HTTP、Python CABTブリッジ、Chrome CDPによる実ブラウザ計測。

## Global Constraints

- 対戦画面のレイアウトを変更しない。
- カード効果、CABT選択、プロンプトID、二重送信防止の挙動を変更しない。
- 相手AI・オンライン相手・Codexの行動は1手ずつ再生する。
- 投了は相手行動再生中でも使用できる既存仕様を維持する。
- テストをskip・削除して完了扱いにしない。
- 実装完了後は共有URLへ反映する。

---

## File Structure

- Modify: `src/lib/game/types.ts` — sequence再生メタデータの公開型。
- Modify: `src/state/game.svelte.ts` — フレーム単位の即時適用・アニメーション制御。
- Create: `src/state/game.test.ts` — instant/animate/playbackOnlyの待機回帰テスト。
- Modify: `src/engine/localEngine.ts` — 直接操作と自動AI観測を区別してメタデータ生成。
- Modify: `src/engine/localEngine.test.ts` — 直接操作がinstant、後続自動手がanimateになる境界テスト。
- Modify: `src/engine/rooms.ts` — コマンド送信者とポーリング受信者で再生指定を分離。
- Create: `src/engine/rooms.test.ts` — 遠隔対戦の再生指定回帰テスト。
- Modify: `src/App.svelte` — 遠隔・Codexポーリングの再生指定をGameStoreへ中継。
- Create: `scripts/e2e-input-latency.mjs` — 本番ビルドを実ブラウザで操作する計測スクリプト。

### Task 1: GameStoreでinstantフレームを待機なしにする

**Files:**
- Modify: `src/lib/game/types.ts`
- Modify: `src/state/game.svelte.ts`
- Create: `src/state/game.test.ts`

**Interfaces:**
- Produces: `export type SequencePlayback = 'instant' | 'animate'`
- Produces: `EngineOk.sequencePlayback?: SequencePlayback[]`
- Produces: `export class GameStore`
- Consumes: `viewSettingsStore.animateActions`, `viewSettingsStore.actionStepDelayMs`

- [ ] **Step 1: instantフレームがタイマーなしで確定する失敗テストを書く**

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { GameView } from '../lib/game/types';
import { GameStore } from './game.svelte';
import { viewSettingsStore } from './viewSettings.svelte';

const frame = (turn: number, playbackOnly = false): GameView => ({
  ready: true,
  phase: 3,
  phaseLabel: 'プレイヤーの番',
  turn,
  activePlayerIndex: 0,
  players: [],
  prompts: playbackOnly ? [{
    id: turn,
    className: 'ConfirmPrompt',
    type: 'confirm',
    playerId: 0,
    playerIndex: 0,
    supported: true,
    resultSchema: 'boolean',
    fields: { playbackOnly: true },
  }] : [],
  logs: [],
  events: [],
});

describe('GameStore sequence playback', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    viewSettingsStore.animateActions = true;
    viewSettingsStore.actionStepDelayMs = 650;
  });

  afterEach(() => vi.useRealTimers());

  it('instantフレームは650ms待たずに最終ビューへ進む', async () => {
    const store = new GameStore();
    const applied = store.apply({
      ok: true,
      view: frame(2),
      sequence: [frame(1), frame(2)],
      sequencePlayback: ['instant', 'instant'],
    });

    await expect(applied).resolves.toMatchObject({ ok: true });
    expect(store.game?.turn).toBe(2);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('animateフレームは設定時間ごとに再生する', async () => {
    const store = new GameStore();
    const applied = store.apply({
      ok: true,
      view: frame(2),
      sequence: [frame(1), frame(2)],
      sequencePlayback: ['animate', 'animate'],
    });

    expect(store.game?.turn).toBe(1);
    await vi.advanceTimersByTimeAsync(650);
    expect(store.game?.turn).toBe(2);
    await vi.advanceTimersByTimeAsync(650);
    await expect(applied).resolves.toMatchObject({ ok: true });
  });

  it('playbackOnlyはinstant指定でも確認されるまで進めない', async () => {
    const store = new GameStore();
    const applied = store.apply({
      ok: true,
      view: frame(2),
      sequence: [frame(1, true), frame(2)],
      sequencePlayback: ['instant', 'instant'],
    });

    await Promise.resolve();
    expect(store.game?.turn).toBe(1);
    store.confirmPlaybackPrompt();
    await expect(applied).resolves.toMatchObject({ ok: true });
    expect(store.game?.turn).toBe(2);
  });
});
```

- [ ] **Step 2: 対象テストを実行し、型と挙動が未実装で失敗することを確認する**

Run: `npx vitest run src/state/game.test.ts`

Expected: `GameStore` がexportされていない、または `sequencePlayback` が未定義でFAIL。

- [ ] **Step 3: 公開型とGameStoreの最小実装を追加する**

`src/lib/game/types.ts`:

```ts
export type SequencePlayback = 'instant' | 'animate';

export type EngineOk = {
  ok: true;
  view: GameView;
  sequence?: GameView[];
  sequencePlayback?: SequencePlayback[];
  sessionId?: string;
  undoCount?: number;
};
```

`src/state/game.svelte.ts` の `class GameStore` 宣言へ `export` を付け、現行 `apply` メソッドを次で置き換える。

```ts
async apply(response: EngineResponse, generation = this.generation) {
  if (generation !== this.generation) return response;
  if (response.ok) {
    const sequence = response.sequence ?? [];
    const needsPlayback = sequence.some((view, index) =>
      hasPlaybackPrompt(view)
      || (viewSettingsStore.animateActions && (response.sequencePlayback?.[index] ?? 'animate') === 'animate'));
    if (sequence.length && (needsPlayback || response.sequencePlayback?.some((mode) => mode === 'instant'))) {
      this.playingSequence = needsPlayback;
      try {
        for (let index = 0; index < sequence.length; index += 1) {
          if (this.skipSequenceRequested) break;
          const view = sequence[index];
          const playback = response.sequencePlayback?.[index] ?? 'animate';
          this.game = view;
          this.error = '';
          if (hasPlaybackPrompt(view)) {
            this.resolvingPrompt = false;
            await this.waitForPlaybackConfirm();
            if (generation !== this.generation) return response;
          } else if (viewSettingsStore.animateActions && playback === 'animate') {
            await wait(clampedActionStepDelay());
            if (generation !== this.generation) return response;
          }
        }
      } finally {
        if (generation === this.generation) {
          this.playingSequence = false;
          this.skipSequenceRequested = false;
        }
      }
    }
    if (generation !== this.generation) return response;
    this.game = response.view;
    this.error = '';
    this.recordHistory(response.sequence, response.view);
    if (typeof response.undoCount === 'number') this.undoCount = response.undoCount;
    return response;
  }
  this.error = response.error;
  if (response.view) this.game = response.view;
  return response;
}
```

- [ ] **Step 4: 対象テストを実行し、3ケースが通ることを確認する**

Run: `npx vitest run src/state/game.test.ts`

Expected: 3 tests passed。

- [ ] **Step 5: Task 1をコミットする**

```bash
git add src/lib/game/types.ts src/state/game.svelte.ts src/state/game.test.ts
git commit -m "fix: 人間操作の即時再生に対応"
```

### Task 2: LocalEngineControllerで直接操作と自動AI操作を区別する

**Files:**
- Modify: `src/engine/localEngine.ts`
- Modify: `src/engine/localEngine.test.ts`

**Interfaces:**
- Consumes: `SequencePlayback`
- Produces: `EngineResponse.sequencePlayback`
- Internal: `applyBridgeResponse(response, directPlayback?: SequencePlayback): void`
- Internal: `pendingSequence: Array<{ view: GameView; playback: SequencePlayback }>`

- [ ] **Step 1: 直接操作の最初の観測だけinstantになる失敗テストを書く**

```ts
it('marks the direct human frame instant and later automatic frames animate', async () => {
  const engine = new LocalEngineController() as any;
  engine.sessionId = 'session';
  engine.playerControls = ['self', 'agent'];
  engine.observation = observation({ yourIndex: 0 });
  engine.bridge = {
    request: async () => ({
      ok: true,
      observation: observation({ yourIndex: 0 }),
      autoSteps: [
        observation({ yourIndex: 0 }),
        observation({ yourIndex: 1 }),
      ],
    }),
  };

  const response = await engine.applySelection([0]);

  expect(response.ok).toBe(true);
  if (!response.ok) return;
  expect(response.sequencePlayback).toEqual(['instant', 'animate']);
});
```

テスト用 `observation` helperの `select.option` には `{ type: CabtOptionType.END }` を1件入れ、`minCount=maxCount=1` とする。

- [ ] **Step 2: 対象テストが `sequencePlayback` 未生成で失敗することを確認する**

Run: `npx vitest run src/engine/localEngine.test.ts -t "direct human frame"`

Expected: expected `['instant', 'animate']`, received `undefined` でFAIL。

- [ ] **Step 3: pendingSequenceへ再生指定を保持する最小実装を追加する**

```ts
import type { ActionTimelineEvent, CardTarget, EngineResponse, GameView, LogView, SequencePlayback } from '../lib/game/types';

type PendingSequenceFrame = { view: GameView; playback: SequencePlayback };

private pendingSequence: PendingSequenceFrame[] = [];

private applyBridgeResponse(response: BridgeResponse, directPlayback: SequencePlayback = 'animate'): void {
  if (!response.ok) {
    throw new Error(response.traceback ? `${response.error}\n${response.traceback}` : (response.error ?? 'CABTエンジンでエラーが発生しました。'));
  }
  if (response.cards && response.attacks) {
    this.dataMaps = {
      cardData: Object.fromEntries(response.cards.map((card) => [card.cardId, enrichCardData(card)])),
      attacks: Object.fromEntries(response.attacks.map((attack) => [attack.attackId, attack])),
    };
  }
  this.trueHands = response.trueHands ?? null;
  this.truePrizes = response.truePrizes ?? null;
  this.pendingSequence = [...this.pendingSequence, ...this.appendTimeline(response, directPlayback)];
  this.recordReplayFrames(response);
  this.observation = this.withKnownHands(response.observation ?? null);
  if (typeof response.undoCount === 'number') {
    this.undoCount = response.undoCount;
  }
}

private appendTimeline(response: BridgeResponse, directPlayback: SequencePlayback): PendingSequenceFrame[] {
  const observations = response.autoSteps?.length ? response.autoSteps : response.observation ? [response.observation] : [];
  const sequence: PendingSequenceFrame[] = [];
  for (let observationIndex = 0; observationIndex < observations.length; observationIndex += 1) {
    const observation = observations[observationIndex];
    const playback = observationIndex === 0 ? directPlayback : 'animate';
    const logs = observation.logs ?? [];
    if (logs.length) {
      const result = cabtLogsToTimeline(logs, { nextId: this.timelineId });
      this.timelineId = result.nextId;
      this.actionTimeline = [...this.actionTimeline, ...result.events].slice(-5000);
    }
    const hydratedObservation = this.withKnownHands(observation);
    if (!hydratedObservation) {
      continue;
    }
    const view = cabtObservationToGameView(hydratedObservation, this.logs, this.dataMaps, this.actionTimeline);
    const revealPrompt = this.revealPromptForLogs(logs, view);
    if (revealPrompt) {
      sequence.push({ view: { ...view, prompts: [revealPrompt] }, playback });
    }
    if (!this.isAgentDecisionView(hydratedObservation, view)) {
      sequence.push({ view, playback });
    }
  }
  return sequence;
}

private viewResponse(): EngineResponse {
  const pending = this.pendingSequence;
  this.pendingSequence = [];
  return {
    ok: true,
    view: this.view(),
    sequence: pending.length ? pending.map((frame) => frame.view) : undefined,
    sequencePlayback: pending.length ? pending.map((frame) => frame.playback) : undefined,
    sessionId: this.sessionId || undefined,
    undoCount: this.undoCount,
  };
}
```

上のコメント部分には現行 `appendTimeline` のログ変換処理を移動し、`logs` と `hydratedObservation` を現在と同じ順番で定義する。別途同じ観測を再変換したり、`withKnownHands` を二重実行したりしない。

5箇所の呼出しを次の指定へ置き換える。

- `start` と `undo`: `this.applyBridgeResponse(response, 'instant')`
- `applySelection`: `this.applyBridgeResponse(response, 'instant')`
- `applyRepeatedSingleSelections` 内の各bridge応答: `this.applyBridgeResponse(response, 'instant')`
- `applyPendingRetreatTarget` の自動確定応答: `this.applyBridgeResponse(response, 'instant')`

これらはすべてGUIから確定済みの直接入力である。アップロードAIの判断はbridgeが同じresponseの2件目以降の `autoSteps` として返すため、`appendTimeline` が2件目以降を必ず `animate` にする。

- [ ] **Step 4: 対象テストとLocalEngine全テストを実行する**

Run: `npx vitest run src/engine/localEngine.test.ts`

Expected: all tests passed。

- [ ] **Step 5: Task 2をコミットする**

```bash
git add src/engine/localEngine.ts src/engine/localEngine.test.ts
git commit -m "fix: 操作者に応じて対戦フレームの再生を分離"
```

### Task 3: 遠隔ルームの送信者と受信者で再生指定を分ける

**Files:**
- Modify: `src/engine/rooms.ts`
- Create: `src/engine/rooms.test.ts`
- Modify: `src/App.svelte`

**Interfaces:**
- RoomFrame becomes `{ rev: number; view: GameView }`; stored remote frames are returned with `animate`.
- `roomCommand` preserves controller `sequencePlayback` for the command sender.
- `roomState` returns `sequencePlayback: sequence.map(() => 'animate')` for polled opponent frames.

- [ ] **Step 1: ポーリング差分がanimateになる失敗テストを書く**

```ts
import { describe, expect, it } from 'vitest';
import { __test } from './rooms';

describe('room playback metadata', () => {
  it('marks every remotely polled frame animate', () => {
    expect(__test.remotePlayback(3)).toEqual(['animate', 'animate', 'animate']);
  });

  it('preserves sender playback metadata', () => {
    expect(__test.senderPlayback(['instant', 'animate'], 2)).toEqual(['instant', 'animate']);
    expect(__test.senderPlayback(undefined, 2)).toEqual(['animate', 'animate']);
  });
});
```

- [ ] **Step 2: 対象テストがhelper未実装で失敗することを確認する**

Run: `npx vitest run src/engine/rooms.test.ts`

Expected: `__test` がexportされておらずFAIL。

- [ ] **Step 3: 再生指定helperとレスポンス組み立てを実装する**

```ts
import type { SequencePlayback } from '../lib/game/types';

function remotePlayback(count: number): SequencePlayback[] {
  return Array.from({ length: count }, () => 'animate');
}

function senderPlayback(playback: SequencePlayback[] | undefined, count: number): SequencePlayback[] {
  return Array.from({ length: count }, (_unused, index) => playback?.[index] ?? 'animate');
}

export const __test = { remotePlayback, senderPlayback };
```

`roomState` の返却値へ `sequencePlayback: sequence.length ? remotePlayback(sequence.length) : undefined` を追加する。`roomCommand` はマスク後の `sequence` 長に対して `senderPlayback(response.sequencePlayback, sequence.length)` を返す。

`App.svelte` のオンラインポーリングは再生指定を落とさず中継する。

```ts
await gameSessionStore.applyExternal({
  ok: true,
  view: state.view,
  sequence: state.sequence,
  sequencePlayback: state.sequencePlayback,
});
```

Codexポーリングも同じ形で `sequencePlayback` を渡す。

- [ ] **Step 4: 対象テストとHTTPクライアントテストを実行する**

Run: `npx vitest run src/engine/rooms.test.ts src/lib/game/httpClient.test.ts`

Expected: all tests passed。

- [ ] **Step 5: Task 3をコミットする**

```bash
git add src/engine/rooms.ts src/engine/rooms.test.ts src/App.svelte
git commit -m "fix: 遠隔相手の行動だけを再生対象にする"
```

### Task 4: 実ブラウザでクリックから次選択までを回帰計測する

**Files:**
- Create: `scripts/e2e-input-latency.mjs`

**Interfaces:**
- Consumes: production build at `http://127.0.0.1:8196`
- Produces: exit 0 and JSON summary containing `cardUseToPromptMs`

- [ ] **Step 1: 旧実装では650ms入力待ちを検出するE2Eスクリプトを書く**

スクリプトはChrome CDPへ接続し、次を実行する。

```js
const LIMIT_MS = 300;
// 1. 対戦開始をクリック
// 2. 先攻を選択し、開始ポケモンを確定
// 3. 「なかよしポフィン」を選び、game-board-planeへ使用
// 4. 次のSelectableCardをクリックして選択状態になるまでperformance.now()で計測
if (cardUseToPromptMs > LIMIT_MS) {
  throw new Error(`カード使用後の入力待ちが長すぎます: ${cardUseToPromptMs}ms`);
}
console.log(JSON.stringify({ cardUseToPromptMs, limitMs: LIMIT_MS }));
```

固定デッキとCABT乱数に依存しすぎないよう、手札の最初の「使用後に選択プロンプトを開くグッズ」をカード名から探し、見つからない場合はテスト用プリセットを選び直す。CDP操作は座標クリックとDOM状態の両方を確認する。

- [ ] **Step 2: 修正前コミットに対してスクリプトが閾値超過で失敗することを確認する**

Run: `node scripts/e2e-input-latency.mjs`

Expected: `カード使用後の入力待ちが長すぎます` で非0終了。

- [ ] **Step 3: 現在の修正済み実装で同じスクリプトを再実行する**

Run: `node scripts/e2e-input-latency.mjs`

Expected: exit 0、`cardUseToPromptMs <= 300`。ローカルCABT/Chrome起動時間は計測区間へ含めない。

- [ ] **Step 4: Task 4をコミットする**

```bash
git add scripts/e2e-input-latency.mjs
git commit -m "test: 対戦操作レイテンシの実ブラウザ回帰を追加"
```

### Task 5: レイテンシ改善の全体検証

**Files:**
- No production file changes expected.

- [ ] **Step 1: 全ユニットテストを実行する**

Run: `npx vitest run`

Expected: all tests passed, 0 failed, 0 skipped due to this change。

- [ ] **Step 2: TypeScript型検査を実行する**

Run: `npx tsc -p tsconfig.build.json`

Expected: exit 0。

- [ ] **Step 3: 本番ビルドを実行する**

Run: `npm run build`

Expected: exit 0。

- [ ] **Step 4: ネイティブCABT実ブラウザE2Eを再実行する**

Run: `node scripts/e2e-input-latency.mjs`

Expected: exit 0 and `cardUseToPromptMs <= 300`。

- [ ] **Step 5: 差分をレビューする**

Run: `git diff HEAD~4 --check && git diff HEAD~4 --stat`

Expected: whitespace errorsなし。対戦レイアウト・カードデータ・カード効果の差分なし。
