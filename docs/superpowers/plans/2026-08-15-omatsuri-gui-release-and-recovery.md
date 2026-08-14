# おまつりおんどAI公開・GUI復旧 実装計画

> **For Codex:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** GUI対戦中の昆虫E例外と状態ずれを修正し、最新のおまつりおんどAIをGUI・GitHub・Kaggleへ同一ソースから安全に公開する。

**Architecture:** Pythonブリッジが保持する `Session.obs` はCABTネイティブ観測のままにし、表示専用の特性ログはレスポンス用コピーだけへ追加する。失敗レスポンスにも最新スナップショットを含め、TypeScript側は例外を投げる前にその状態を反映する。おまつりおんどAIは正本リポジトリの `stage_python_runtime` からGUI用ランタイムを生成し、同じ正本の `build_bundle` からKaggle提出物を作る。

**Tech Stack:** Python 3、CABT、TypeScript、Vitest、Vite、Git/GitHub CLI、Hugging Face CLI、Kaggle CLI

---

### Task 1: Pythonブリッジでネイティブ観測と表示ログを分離する

**Files:**
- Modify: `src/engine/cabt_bridge.py`
- Create: `scripts/test_cabt_bridge_regressions.py`

**Step 1: 失敗する回帰テストを書く**

`cg` を最小スタブ化して `cabt_bridge.py` を読み込み、以下を検証する。

```python
native = {"logs": [{"type": 1}], "turn": 4}
display = bridge.prepend_logs(native, [{"type": "ability"}])

self.assertEqual(native["logs"], [{"type": 1}])
self.assertEqual(display["logs"][0]["type"], "ability")
self.assertIsNot(display, native)
```

さらに `build_error_response` が存在し、アクティブセッションの `snapshot()` に含まれる `observation`、`undoCount`、`trueHands`、`truePrizes` を `ok: false` のレスポンスへ残すことを検証する。

**Step 2: REDを確認する**

Run: `python -B scripts/test_cabt_bridge_regressions.py`

Expected: `prepend_logs` が元辞書を破壊するためFAILし、`build_error_response` 不在のアサーションもFAILする。

**Step 3: 最小実装を行う**

`prepend_logs` を浅いコピーを返す純粋関数へ変更する。

```python
def prepend_logs(obs, logs):
    if not logs:
        return obs
    display = dict(obs)
    display["logs"] = list(logs) + list(obs.get("logs") or [])
    return display
```

`Session.select` と `Session.play_ai_turns` は `do_select()` のネイティブ戻り値を `self.obs` に保持したまま、`autoSteps` 用の表示コピーだけを返す。例外処理は次のヘルパーを通す。

```python
def build_error_response(session, exc):
    response = {"ok": False, "error": str(exc), "traceback": traceback.format_exc()}
    if session.active:
        try:
            snapshot = session.snapshot()
        except Exception:
            return response
        response.update({key: value for key, value in snapshot.items() if key != "ok"})
    return response
```

**Step 4: GREENを確認する**

Run: `python -B scripts/test_cabt_bridge_regressions.py`

Expected: 全テストPASS。

### Task 2: 昆虫Eの未知ログ耐性とGUIの失敗時同期を追加する

**Files:**
- Modify: `public/agents/konchu-e/memory.py`
- Modify: `src/engine/localEngine.ts`
- Modify: `src/engine/localEngine.test.ts`
- Modify: `src/lib/home/bundledAgents.test.ts`

**Step 1: 失敗するテストを書く**

`bundledAgents.test.ts` からPythonを起動し、`{"type": "ability"}` を含む公開ログを `AgentMemory.observe_public_opponent` に渡して例外が出ないことを要求する。`localEngine.test.ts` では `ok: false` かつ最新 `observation` を持つレスポンスを `applyBridgeResponse` に渡し、例外は投げても `engine.observation` が最新ターンへ更新されることを要求する。

**Step 2: REDを確認する**

Run: `npm test -- --run src/lib/home/bundledAgents.test.ts src/engine/localEngine.test.ts`

Expected: 昆虫Eは `int("ability")` で失敗し、ローカルエンジンは観測更新前にthrowするためFAIL。

**Step 3: 最小実装を行う**

昆虫Eは未知・非数値ログを無視する。

```python
try:
    log_type = int(log.get("type", -1))
except (TypeError, ValueError):
    continue
```

TypeScript側は失敗レスポンスに観測があれば `trueHands`、`truePrizes`、`undoCount`、`observation`、`observationVersion` を同期してから従来どおり例外を投げる。成功時のタイムライン処理は変更しない。

**Step 4: GREENを確認する**

Run: `npm test -- --run src/lib/home/bundledAgents.test.ts src/engine/localEngine.test.ts`

Expected: 対象テストPASS。

### Task 3: サイド3枚時の3枚目選択を固定回帰テストにする

**Files:**
- Modify: `src/engine/localEngine.test.ts`

**Step 1: キャラクタリゼーションテストを書く**

サイド選択肢が3枚の観測を設定し、3枚目を選んだときブリッジへ送るリクエストが一度だけ次になることを検証する。

```typescript
expect(selectRequests).toEqual([
  { command: "select", selection: [2] },
]);
```

これはスクリーンショットの二次エラーを状態ずれの再発と区別するための固定テストであり、マッピング自体は変更しない。

**Step 2: テストを確認する**

Run: `npm test -- --run src/engine/localEngine.test.ts`

Expected: PASS。

### Task 4: 最新おまつりおんどAIをGUIへ正本から同期する

**Files:**
- Create: `scripts/sync_project_agents.py`
- Create: `scripts/test_sync_project_agents.py`
- Modify: `public/agents/agents.json`
- Create: `public/agents/omatsuri-ondo/**`
- Modify: `src/lib/home/bundledAgents.test.ts`
- Modify: `src/lib/game/agentDeck.test.ts`

**Step 1: 失敗する統合テストを書く**

マニフェストに固定デッキの `omatsuri-ondo` が存在し、`main.py` と60枚の `deck.csv` があり、GUI隔離環境でimportできることを要求する。同期スクリプトのテストは正本の `stage_python_runtime` を使用し、`cg`、テスト、探索・評価用ファイルを出力しないことを要求する。

**Step 2: REDを確認する**

Run: `npm test -- --run src/lib/home/bundledAgents.test.ts src/lib/game/agentDeck.test.ts`

Run: `python -B scripts/test_sync_project_agents.py`

Expected: エージェントと同期スクリプトが未配置のためFAIL。

**Step 3: 同期処理とマニフェストを実装する**

正本 `C:\dev\PTCG-AI-omatsuri-ondo\src\agent\omatsuri_ondo\build_bundle.py` の `stage_python_runtime(destination, top_level_main=True, include_deck=True)` を使って `public/agents/omatsuri-ondo` を生成する。マニフェストへ次を追加する。

```json
{
  "id": "omatsuri-ondo",
  "name": "おまつりおんどAI（カミッチュ）",
  "path": "public/agents/omatsuri-ondo/main.py",
  "deckUrl": "/agents/omatsuri-ondo/deck.csv",
  "fixedDeck": true
}
```

**Step 4: GREENと隔離importを確認する**

Run: `python -B scripts/test_sync_project_agents.py`

Run: `npm test -- --run src/lib/home/bundledAgents.test.ts src/lib/game/agentDeck.test.ts`

Expected: 全テストPASS。

### Task 5: GitHub用のクリーンなおまつりおんど公開ブランチを作る

**Files:**
- Create in `C:\dev\PTCG-AI-omatsuri-release`: `src/agent/common_strategy/**`
- Create in `C:\dev\PTCG-AI-omatsuri-release`: `src/agent/omatsuri_ondo/**`
- Create in `C:\dev\PTCG-AI-omatsuri-release`: `scripts/omatsuri_policy_compiler/**`
- Create in `C:\dev\PTCG-AI-omatsuri-release`: `scripts/build_omatsuri_policy.py`
- Create in `C:\dev\PTCG-AI-omatsuri-release`: related docs/tests

**Step 1: `origin/main` から専用worktreeを作る**

Run: `git fetch origin`

Run: `git worktree add -b codex/omatsuri-ondo-release C:\dev\PTCG-AI-omatsuri-release origin/main`

Expected: ユーザーの汚れたworktreeへ触れず、クリーンな公開ブランチができる。

**Step 2: 正本ブランチから必要パスだけを移植する**

`codex/omatsuri-ondo-agent` の対象パスだけを新worktreeへ復元し、`fudein_ai_2` やsample_aを含めない。差分一覧と機密ファイル不在を確認する。

**Step 3: 正本テストとバンドル検証を行う**

Run: `python -m pytest src/agent/omatsuri_ondo scripts/omatsuri_policy_compiler -q`

Run: `python scripts/build_omatsuri_policy.py --check`

Expected: PASS。

**Step 4: コミット・push・PR作成**

Run: `git commit -m "feat: おまつりおんどAIを公開"`

Run: `git push -u origin codex/omatsuri-ondo-release`

Run: `gh pr create --repo mocococococo/PTCG-AI --base main --head codex/omatsuri-ondo-release --title "feat: おまつりおんどAIを公開" --body "おまつりおんど固定方策AI、共通戦略、方策コンパイラ、テストをmain向けに追加します。"`

Expected: GitHub上でレビュー可能なPR URLが返る。

### Task 6: GUIを検証・pushし、公開Spaceへ反映する

**Files:**
- Modify in `C:\dev\pokeca-ai\cabt-viewer-omatsuri-release`: 上記GUIファイル
- Update deployment source under `C:\dev\pokeca-ai\hf-space` without reading credential files

**Step 1: 全GUI検証を行う**

Run: `npm test`

Run: `npx tsc -p tsconfig.json --noEmit`

Run: `npm run build`

Run: `python -B scripts/test_cabt_bridge_regressions.py`

Run: `python -B scripts/test_sync_project_agents.py`

Expected: すべてPASS。

**Step 2: コミット・pushする**

Run: `git commit -m "fix: GUI対戦の状態同期を直しおまつりおんどAIを追加"`

Run: `git push -u personal codex/omatsuri-gui-release`

PRまたはfast-forward可能性を確認し、履歴改変やforce pushを使わず `personal/main` へ反映する。

**Step 3: Hugging Face Spaceへデプロイする**

既存のビルドスクリプトを検査し、認証ファイルの内容を表示せず `HF_TOKEN_PATH` 経由で既存Docker Space `kahtgf/pokeca-cabt` を更新する。

**Step 4: 公開URLをスモーク確認する**

Run: `python C:\dev\pokeca-ai\scripts\verify_hf.py`

Expected: `https://kahtgf-pokeca-cabt.hf.space` が稼働し、manifestに `omatsuri-ondo`、配布 `memory.py` に未知ログ耐性が存在する。

### Task 7: 同一正本からKaggle提出物を作り、終端状態まで監視する

**Files:**
- Create under a unique timestamped directory: Kaggle staging bundle and `.tar.gz`

**Step 1: 正本ビルダーで提出物を作る**

`C:\dev\PTCG-AI-omatsuri-ondo\src\agent\omatsuri_ondo\build_bundle.py` の `build_bundle(output)` を使い、既存成果物を削除せずタイムスタンプ付きディレクトリへ生成する。

**Step 2: 内容とimportを検証する**

`main.py`、`deck.csv`、ランタイム、Kaggle用 `cg` が揃い、キャッシュ・秘密情報・不要な評価物がないことを確認する。隔離ディレクトリから `main.py` をimportし、deckが60枚であることを確認する。

**Step 3: 圧縮して実提出する**

Run: `kaggle competitions submit -c pokemon-tcg-ai-battle -f $archive -m "omatsuri_ondo fixed-policy agent"`

Expected: Submission IDまたは受付メッセージが返る。

**Step 4: 終端状態まで監視する**

Run: `kaggle competitions submissions -c pokemon-tcg-ai-battle -v`

`complete` なら戦績・スコアを記録する。`error` ならエラー詳細を取得し、パッケージを修正して再提出する。pendingのまま完了扱いにしない。

### Task 8: 最終証跡をまとめる

**Files:**
- No file changes expected

**Step 1: 各worktreeの状態を確認する**

GUIとPTCG-AI公開worktreeで `git status --short --branch`、リモートブランチ、PR、公開URLを確認する。

**Step 2: 成果を報告する**

修正原因、テスト結果、GUIリポジトリ/PR、PTCG-AI PR、公開Space、Kaggle提出ファイル名・状態を日本語で簡潔にまとめる。
