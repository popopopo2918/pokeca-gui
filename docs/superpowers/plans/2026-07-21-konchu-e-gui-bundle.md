# 昆虫E GUI内蔵・GitHub公開 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kaggle提出版「昆虫E」をPTCG-AIの共有ブランチへ公開し、既存sample_aと共存する固定デッキAIとしてCABT Viewerと共有URLへ追加する。

**Architecture:** `C:/dev/PTCG-AI/src/agent/fudein_ai_2` を昆虫Eの正本とし、GitHubへ先にpushする。GUIには実行時依存だけを `public/agents/konchu-e` へ自己完結スナップショットとして同期し、manifestの固定デッキAIとして登録する。GUI実行時にGitHubへアクセスしない。

**Tech Stack:** Python 3.12、unittest、pytest、Svelte 5、TypeScript、Vitest、Vite、Node.js、Git、Hugging Face Spaces

## Global Constraints

- 既存の `public/agents/alakazam-playbook` と「フーディンAI（現行sample_a）」を変更・削除しない。
- PTCG-AIのリプレイ、評価DB、一時ファイル、認証情報、キャッシュをコミットしない。
- GUIの `public/game-logs/` と既存の未追跡ログを変更・コミットしない。
- 昆虫Eは固定60枚デッキを自動使用する。
- Python読込、デッキ枚数、全テスト、型検査、buildのいずれかが失敗した場合はpush・デプロイしない。
- `git push --force` と履歴改変を行わない。

---

### Task 1: PTCG-AIの昆虫Eを共有ブランチへ公開

**Files:**
- Modify: `C:/dev/PTCG-AI/src/agent/fudein_ai_2/*.py`
- Modify: `C:/dev/PTCG-AI/src/agent/fudein_ai_2/rules/*.py`
- Modify: `C:/dev/PTCG-AI/src/agent/fudein_ai_2/tests/*.py`
- Include: `C:/dev/PTCG-AI/src/agent/fudein_ai_2/deck.csv`
- Include: `C:/dev/PTCG-AI/src/agent/fudein_ai_2/data/top200_environment_2026-07-18.json`

**Interfaces:**
- Consumes: Kaggle提出ID `54879069` で検証済みの現行 `fudein_ai_2` ワークツリー。
- Produces: `origin/kawanoooooo` 上の昆虫E正本コミットと、その40桁commit SHA。

- [ ] **Step 1: 正本のデッキ契約と入口テストを再実行する**

Run:

```powershell
Set-Location C:/dev/PTCG-AI/src/agent/fudein_ai_2
python -m pytest tests/test_kaggle_entrypoint.py -q
python -m unittest discover -s tests -q
python -m compileall -q .
```

Expected: Kaggle入口4件成功、全unittest成功、コンパイルエラー0。

- [ ] **Step 2: ローカルCABT対戦で起動境界を検証する**

Run:

```powershell
Set-Location C:/dev/PTCG-AI
python src/local-match.py fudein_ai_2 sample_b --match-size 1 --seed 0 --time-limits 60 --output-off
```

Expected: 終了コード0。`agent_error`、`simulation_error`なし。

- [ ] **Step 3: 昆虫Eディレクトリだけをstageする**

Run:

```powershell
Set-Location C:/dev/PTCG-AI
git add -- src/agent/fudein_ai_2
git diff --cached --check
git diff --cached --name-only
```

Expected: stage対象は `src/agent/fudein_ai_2/` 配下だけ。`artifacts/`、`tmp/`、認証情報を含まない。

- [ ] **Step 4: 昆虫Eをコミットする**

Run:

```powershell
git commit -m "feat: 昆虫Eの戦術改善を追加"
$sourceCommit = git rev-parse HEAD
$sourceCommit
```

Expected: Conventional Commits形式でコミット成功し、40桁SHAを取得する。

- [ ] **Step 5: kawanooooooへfast-forward pushする**

Run:

```powershell
git merge-base --is-ancestor origin/kawanoooooo HEAD
if ($LASTEXITCODE -ne 0) { throw 'origin/kawanooooooへfast-forwardできません' }
git push origin HEAD:kawanoooooo
```

Expected: forceなしで `origin/kawanoooooo` が昆虫Eコミットへ進む。

---

### Task 2: GUIへ昆虫Eを独立AIとして内蔵

**Files:**
- Create: `public/agents/konchu-e/`
- Modify: `public/agents/agents.json`
- Modify: `src/lib/home/bundledAgents.test.ts`
- Test: `src/lib/game/agentDeck.test.ts`

**Interfaces:**
- Consumes: Task 1の `C:/dev/PTCG-AI/src/agent/fudein_ai_2` とcommit SHA。
- Produces: manifest ID `konchu-e`、`/agents/konchu-e/deck.csv`、`public/agents/konchu-e/main.py`。

- [ ] **Step 1: manifest共存の失敗テストを追加する**

Add to `src/lib/home/bundledAgents.test.ts`:

```ts
describe('bundled Konchu E agent', () => {
  it('coexists with sample_a and registers a fixed sixty-card deck', () => {
    const konchuE = manifest.agents.find((agent) => agent.id === 'konchu-e');
    const sampleA = manifest.agents.find(
      (agent) => agent.id === 'alakazam-playbook',
    );

    expect(konchuE).toMatchObject({
      id: 'konchu-e',
      name: '昆虫E',
      path: 'public/agents/konchu-e/main.py',
      deckUrl: '/agents/konchu-e/deck.csv',
      fixedDeck: true,
    });
    expect(sampleA).toBeDefined();
  });
});
```

- [ ] **Step 2: テストが未登録で失敗することを確認する**

Run:

```powershell
Set-Location C:/dev/pokeca-ai/cabt-viewer
npx vitest run src/lib/home/bundledAgents.test.ts
```

Expected: `konchu-e` が未登録のためFAIL。

- [ ] **Step 3: 実行時スナップショットを同期する**

Run:

```powershell
$source = 'C:/dev/PTCG-AI/src/agent/fudein_ai_2'
$target = 'C:/dev/pokeca-ai/cabt-viewer/public/agents/konchu-e'
New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item "$source/main.py","$source/deck.csv","$source/__init__.py","$source/cards.py","$source/catalog.py","$source/environment_profiles.py","$source/memory.py","$source/model.py","$source/policy.py","$source/proposals.py","$source/rule_manifest.py","$source/strategy_config.py" -Destination $target -Force
Copy-Item "$source/rules" -Destination $target -Recurse -Force
Copy-Item "$source/data" -Destination $target -Recurse -Force
```

Expected: `tests/`、`artifacts/`、`cg/`、キャッシュを含まず、実行時ファイルだけが存在する。

- [ ] **Step 4: manifestへ昆虫Eを登録する**

Add to `public/agents/agents.json` without modifying the existing sample_a row:

```json
{
  "id": "konchu-e",
  "name": "昆虫E",
  "description": "Kaggle提出版のフーディンAI。2～3ターン目の攻撃開始と連続KO、公開情報に基づく妨害・後続準備を重視します。",
  "path": "public/agents/konchu-e/main.py",
  "deckUrl": "/agents/konchu-e/deck.csv",
  "fixedDeck": true
}
```

- [ ] **Step 5: Python読込と60枚デッキのテストを追加する**

Extend `bundledAgents.test.ts` so the new test runs:

```ts
const mainPath = path.join(root, 'public', 'agents', 'konchu-e', 'main.py');
const python = process.env.PYTHON || 'python';
const program = [
  'import importlib.util, json, pathlib, sys',
  'path = pathlib.Path(sys.argv[1]).resolve()',
  'spec = importlib.util.spec_from_file_location("cabt_bundled_konchu_e", path)',
  'module = importlib.util.module_from_spec(spec)',
  'spec.loader.exec_module(module)',
  'print(json.dumps({"deckSize": len(module.agent({"select": None}))}))',
].join('; ');
const result = spawnSync(python, ['-B', '-c', program, mainPath], {
  encoding: 'utf8',
});
expect(result.status, result.stderr).toBe(0);
expect(JSON.parse(result.stdout)).toEqual({ deckSize: 60 });
```

- [ ] **Step 6: 固定デッキ選択契約へ昆虫Eを追加する**

Add to the fixture in `src/lib/game/agentDeck.test.ts`:

```ts
{
  id: 'konchu-e',
  name: '昆虫E',
  deckUrl: '/agents/konchu-e/deck.csv',
  fixedDeck: true,
},
```

Add assertion:

```ts
expect(fixedAgentDeckSource('agent', 'konchu-e', agents)).toBe('konchu-e');
```

- [ ] **Step 7: GUI対象テストを通す**

Run:

```powershell
npx vitest run src/lib/home/bundledAgents.test.ts src/lib/game/agentDeck.test.ts
```

Expected: manifest、Python読込、60枚デッキ、sample_a共存、固定デッキ契約がすべてPASS。

- [ ] **Step 8: GUI統合をコミットする**

Run:

```powershell
git add -- public/agents/konchu-e public/agents/agents.json src/lib/home/bundledAgents.test.ts src/lib/game/agentDeck.test.ts
git diff --cached --check
git commit -m "feat: 昆虫Eを対戦AIへ追加"
```

Expected: ゲームログを含めず、昆虫E関連ファイルだけがコミットされる。

---

### Task 3: GUIを検証・GitHub公開・共有URLへデプロイ

**Files:**
- Verify: `package.json`
- Use: `scripts/deploy_hf.sh`
- Preserve: `public/game-logs/`

**Interfaces:**
- Consumes: Task 2のGUIコミット。
- Produces: `personal/main` のGitHubコミットと `https://kahtgf-pokeca-cabt.hf.space/` の昆虫E。

- [ ] **Step 1: GUI全体検証を実行する**

Run:

```powershell
Set-Location C:/dev/pokeca-ai/cabt-viewer
npx vitest run
npx tsc -p tsconfig.build.json
npm run build
```

Expected: 全Vitest成功、型エラー0、Vite build成功。

- [ ] **Step 2: コミット前レビューを行う**

Inspect:

```powershell
git diff personal/main..HEAD --stat
git status --short
```

Expected: 昆虫E、承認済み仕様・計画だけが新規コミット。`public/game-logs/` は未コミットのまま。

- [ ] **Step 3: GUIをGitHubへpushする**

Run:

```powershell
git push personal main
```

Expected: `personal/main` が現在のGUIコミットへfast-forwardする。

- [ ] **Step 4: Hugging Face共有URLへデプロイする**

Run:

```powershell
& 'C:/Program Files/Git/bin/bash.exe' ../scripts/deploy_hf.sh
```

Expected: Hugging Face Spaceへのpush成功。トークン内容は表示しない。

- [ ] **Step 5: 共有URLのmanifestと昆虫Eファイルを確認する**

Run:

```powershell
$manifest = Invoke-RestMethod 'https://kahtgf-pokeca-cabt.hf.space/agents/agents.json'
$agent = $manifest.agents | Where-Object { $_.id -eq 'konchu-e' }
if (-not $agent -or -not $agent.fixedDeck) { throw '共有版に昆虫Eがありません' }
$deck = (Invoke-WebRequest 'https://kahtgf-pokeca-cabt.hf.space/agents/konchu-e/deck.csv').Content -split "`n" | Where-Object { $_.Trim() }
if ($deck.Count -ne 60) { throw "昆虫Eのデッキ枚数が$($deck.Count)です" }
$agent | ConvertTo-Json -Compress
```

Expected: `id=konchu-e`、`fixedDeck=true`、deck.csvが60行。

- [ ] **Step 6: 最終状態を報告する**

Report:

```powershell
$sourceCommit = git -C C:/dev/PTCG-AI rev-parse HEAD
$guiCommit = git rev-parse HEAD
"PTCG-AI source commit: $sourceCommit"
"PTCG-AI branch: kawanoooooo"
"GUI commit: $guiCommit"
"GUI branch: personal/main"
"Shared URL: https://kahtgf-pokeca-cabt.hf.space/"
"Verification: Python tests / Vitest / tsc / build / live manifest / 60-card deck"
```

Expected: GitHub両リポジトリと共有URLの3箇所が同じ昆虫Eを指す。
