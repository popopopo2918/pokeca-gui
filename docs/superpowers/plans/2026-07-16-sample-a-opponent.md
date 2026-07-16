# 現行フーディンAI対戦席 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `C:\dev\PTCG-AI\src\agent\sample_a` の現行ルールベースを、専用60枚デッキと組み合わせた通常の内蔵AI「フーディンAI（現行sample_a）」としてローカルGUIと共有URLへ追加する。

**Architecture:** 設計上の正本はPTCG-AI側に置いたまま、実行時ファイルだけをCABT Viewerの `public/agents/alakazam-playbook` へ検証付きで同期する。既存の `LocalEngineController` と `cabt_bridge.py` の自動AI経路を利用し、Viewer側では戦略を再実装しない。メニューでは `fixedDeck` メタデータを持つAIだけ専用デッキを強制し、対戦画面・カード処理・通信対戦には変更を加えない。

**Tech Stack:** Python 3.11同期スクリプト、TypeScript 6、Svelte 5、Vitest 4、Node.js 20、CABT Pythonブリッジ、Hugging Face Spaces

## Global Constraints

- 表示名は `フーディンAI（現行sample_a）`、エージェントIDは `alakazam-playbook` とする。
- 正本は `C:\dev\PTCG-AI\src\agent\sample_a`、上書き環境変数は `CABT_SAMPLE_A_SOURCE_DIR` とする。
- `cg/`、ネイティブDLL/SO、`tests/`、`artifacts/`、`evaluate.py`、`opponent_decks.py`、`__pycache__/`、対戦ログは同期しない。
- 専用デッキは同期された `deck.csv` の60枚に固定する。
- Viewer側にAI判断規則を複製せず、同期した `sample_a` の `agent(obs_dict)` を呼ぶ。
- 対戦画面のレイアウト、カード効果、オーバーレイ、手札表示、ログ表示、Codex操作席、通信対戦を変更しない。
- `public/game-logs/logs.json` と未追跡の `public/game-logs/local-*.json` はユーザー成果物としてステージ・編集・削除しない。
- CABTネイティブファイルは `CABT_SAMPLE_SUBMISSION_DIR` から供給し、リポジトリへ追加しない。

---

## File Structure

- Create: `scripts/sync_sample_a_agent.py` — 正本の検証、許可ファイルの列挙、配布スナップショットの置換を担当する。
- Create: `scripts/test_sync_sample_a_agent.py` — 同期対象、除外対象、60枚検証、失敗時の既存出力保護を検証する。
- Modify: `package.json` — 同期と同期テストの再現可能なコマンドを追加する。
- Create: `public/agents/alakazam-playbook/**` — 同期された実行時スナップショット。
- Modify: `public/agents/agents.json` — 内蔵AIの表示名、実行ファイル、専用デッキ、固定属性を登録する。
- Modify: `src/lib/home/catalog.ts` — `AgentOption.fixedDeck` を定義する。
- Create: `src/lib/home/bundledAgents.test.ts` — マニフェスト、ファイル、60枚デッキ、Python importを一体で検証する。
- Modify: `src/engine/localEngine.test.ts` — 新AI IDが新しい `main.py` へ解決されることを検証する。
- Create: `src/lib/game/agentDeck.ts` — 固定デッキAIの選択状態を純粋関数で判定する。
- Create: `src/lib/game/agentDeck.test.ts` — 人間席、通常AI、固定AIの境界を検証する。
- Modify: `src/App.svelte` — 固定AI選択時に専用デッキソースを復元・維持する。
- Modify: `src/lib/components/ImportScreen.svelte` — 固定AIのデッキ選択欄だけを無効化する。
- Create: `scripts/e2e-alakazam-agent.mjs` — 実CABTサーバーへ人間対フーディンAIの開始要求を送り、自動AI経路を確認する。
- Modify: `C:\dev\pokeca-ai\scripts\deploy_hf.sh` — Space用ビルドコンテキスト作成前に同期を必須実行する。

---

### Task 1: 検証付きsample_a同期パイプライン

**Files:**
- Create: `scripts/test_sync_sample_a_agent.py`
- Create: `scripts/sync_sample_a_agent.py`
- Modify: `package.json`
- Create: `public/agents/alakazam-playbook/**`

**Interfaces:**
- Consumes: `CABT_SAMPLE_A_SOURCE_DIR` またはCABT Viewerから見た `../../PTCG-AI/src/agent/sample_a`。
- Produces: `resolve_source(viewer_root: Path, environ: Mapping[str, str]) -> Path`、`validate_source(source: Path) -> tuple[Path, ...]`、`sync_agent(source: Path, destination: Path) -> tuple[Path, ...]`。

- [ ] **Step 1: 同期契約の失敗テストを書く**

`scripts/test_sync_sample_a_agent.py` を次の内容で作成する。

```python
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sync_sample_a_agent import (
    REQUIRED_RULE_FILES,
    TOP_LEVEL_FILES,
    resolve_source,
    sync_agent,
)


class SyncSampleAAgentTest(unittest.TestCase):
    def make_source(self, root: Path, deck_size: int = 60) -> Path:
        source = root / "sample_a"
        source.mkdir()
        for name in TOP_LEVEL_FILES:
            target = source / name
            if name == "deck.csv":
                target.write_text("\n".join(str(700 + index) for index in range(deck_size)) + "\n", encoding="utf-8")
            else:
                target.write_text(f"# {name}\n", encoding="utf-8")
        rules = source / "rules"
        rules.mkdir()
        for name in REQUIRED_RULE_FILES:
            (rules / name).write_text(f"# rules/{name}\n", encoding="utf-8")
        (source / "evaluate.py").write_text("raise RuntimeError('excluded')\n", encoding="utf-8")
        (source / "artifacts").mkdir()
        (source / "artifacts" / "report.json").write_text("{}\n", encoding="utf-8")
        (source / "cg").mkdir()
        (source / "cg" / "cg.dll").write_bytes(b"native-binary")
        (rules / "__pycache__").mkdir()
        return source

    def test_resolve_source_uses_explicit_environment_override(self) -> None:
        viewer = Path("C:/viewer")
        expected = Path("C:/agent-source").resolve()
        self.assertEqual(resolve_source(viewer, {"CABT_SAMPLE_A_SOURCE_DIR": str(expected)}), expected)

    def test_sync_copies_only_runtime_python_and_sixty_card_deck(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            source = self.make_source(root)
            destination = root / "public" / "agents" / "alakazam-playbook"
            copied = sync_agent(source, destination)

            self.assertEqual(len((destination / "deck.csv").read_text(encoding="utf-8").splitlines()), 60)
            self.assertTrue((destination / "main.py").is_file())
            self.assertTrue((destination / "rules" / "attack.py").is_file())
            self.assertFalse((destination / "evaluate.py").exists())
            self.assertFalse((destination / "artifacts").exists())
            self.assertFalse((destination / "cg").exists())
            self.assertFalse((destination / "rules" / "__pycache__").exists())
            self.assertEqual(copied, tuple(sorted(path.relative_to(destination) for path in destination.rglob("*") if path.is_file())))

    def test_missing_runtime_file_is_reported_before_destination_changes(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            source = self.make_source(root)
            (source / "policy.py").unlink()
            destination = root / "public" / "agents" / "alakazam-playbook"
            destination.mkdir(parents=True)
            marker = destination / "keep.txt"
            marker.write_text("existing\n", encoding="utf-8")

            with self.assertRaisesRegex(FileNotFoundError, "policy.py"):
                sync_agent(source, destination)

            self.assertEqual(marker.read_text(encoding="utf-8"), "existing\n")

    def test_invalid_deck_does_not_replace_existing_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            source = self.make_source(root, deck_size=59)
            destination = root / "public" / "agents" / "alakazam-playbook"
            destination.mkdir(parents=True)
            marker = destination / "keep.txt"
            marker.write_text("existing\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "60枚"):
                sync_agent(source, destination)

            self.assertEqual(marker.read_text(encoding="utf-8"), "existing\n")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: テストが未実装で失敗することを確認する**

Run: `python scripts/test_sync_sample_a_agent.py`

Expected: `ModuleNotFoundError: No module named 'sync_sample_a_agent'`

- [ ] **Step 3: 許可リスト・60枚検証・置換保護を実装する**

`scripts/sync_sample_a_agent.py` を次の内容で作成する。

```python
from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path


VIEWER_ROOT = Path(__file__).resolve().parents[1]
DESTINATION = VIEWER_ROOT / "public" / "agents" / "alakazam-playbook"
TOP_LEVEL_FILES = (
    "main.py",
    "cards.py",
    "catalog.py",
    "memory.py",
    "model.py",
    "policy.py",
    "proposals.py",
    "rule_manifest.py",
    "strategy_config.py",
    "deck.csv",
)
REQUIRED_RULE_FILES = (
    "__init__.py",
    "attack.py",
    "development.py",
    "draw_engine.py",
    "evolution.py",
    "fallback.py",
    "poke_pad.py",
    "prompts.py",
    "protection.py",
    "recovery.py",
    "search.py",
    "setup.py",
    "telepath.py",
)


def resolve_source(viewer_root: Path, environ: Mapping[str, str]) -> Path:
    override = environ.get("CABT_SAMPLE_A_SOURCE_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (viewer_root / ".." / ".." / "PTCG-AI" / "src" / "agent" / "sample_a").resolve()


def validate_source(source: Path) -> tuple[Path, ...]:
    required = [source / name for name in TOP_LEVEL_FILES]
    required.extend(source / "rules" / name for name in REQUIRED_RULE_FILES)
    missing = [path for path in required if not path.is_file()]
    if missing:
        rendered = "\n".join(f"- {path}" for path in missing)
        raise FileNotFoundError(f"sample_aの必須ファイルがありません:\n{rendered}")

    deck_rows = [line.strip() for line in (source / "deck.csv").read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(deck_rows) != 60:
        raise ValueError(f"sample_a/deck.csvは60枚である必要があります: {len(deck_rows)}枚")
    invalid = [row for row in deck_rows if not row.isdecimal() or int(row) <= 0]
    if invalid:
        raise ValueError(f"sample_a/deck.csvに不正なカードIDがあります: {invalid[0]}")

    runtime_files = [source / name for name in TOP_LEVEL_FILES]
    runtime_files.extend(sorted((source / "rules").glob("*.py")))
    return tuple(runtime_files)


def sync_agent(source: Path, destination: Path) -> tuple[Path, ...]:
    source = source.resolve()
    runtime_files = validate_source(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup = destination.with_name(f".{destination.name}.backup")

    with tempfile.TemporaryDirectory(prefix=f".{destination.name}.", dir=destination.parent) as work:
        staged = Path(work) / destination.name
        staged.mkdir()
        for source_file in runtime_files:
            relative = source_file.relative_to(source)
            target = staged / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target)

        if backup.exists():
            shutil.rmtree(backup)
        if destination.exists():
            os.replace(destination, backup)
        try:
            os.replace(staged, destination)
        except Exception:
            if backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise
        if backup.exists():
            shutil.rmtree(backup)

    return tuple(sorted(path.relative_to(destination) for path in destination.rglob("*") if path.is_file()))


def main() -> None:
    source = resolve_source(VIEWER_ROOT, os.environ)
    copied = sync_agent(source, DESTINATION)
    print(f"sample_a同期完了: {source} -> {DESTINATION} ({len(copied)} files)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: package.jsonへ同期コマンドを追加する**

`package.json` の `scripts` に次の2項目を追加する。

```json
"sync:sample-a": "python scripts/sync_sample_a_agent.py",
"test:sample-a-sync": "python scripts/test_sync_sample_a_agent.py"
```

- [ ] **Step 5: 同期テストを通し、正本から配布スナップショットを生成する**

Run: `npm run test:sample-a-sync`

Expected: `Ran 4 tests` と `OK`

Run: `npm run sync:sample-a`

Expected: `sample_a同期完了:` と、コピーされたファイル数が表示される。

Run: `Get-ChildItem -Recurse -File public\agents\alakazam-playbook | Select-Object -ExpandProperty FullName`

Expected: Global Constraintsで許可したPythonファイルと `deck.csv` だけが表示される。

- [ ] **Step 6: 同期パイプラインとスナップショットをコミットする**

```powershell
git add -- package.json scripts/sync_sample_a_agent.py scripts/test_sync_sample_a_agent.py public/agents/alakazam-playbook
git commit -m "chore: 現行フーディンAIの同期を追加"
```

---

### Task 2: 内蔵AI登録と実行ファイル整合性

**Files:**
- Create: `src/lib/home/bundledAgents.test.ts`
- Modify: `src/lib/home/catalog.ts`
- Modify: `public/agents/agents.json`
- Modify: `src/engine/localEngine.test.ts`

**Interfaces:**
- Consumes: Task 1の `public/agents/alakazam-playbook/main.py` と `deck.csv`。
- Produces: `AgentOption.fixedDeck?: boolean` と、マニフェストID `alakazam-playbook`。

- [ ] **Step 1: マニフェスト・60枚・Python importの失敗テストを書く**

`src/lib/home/bundledAgents.test.ts` を次の内容で作成する。

```ts
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

type ManifestAgent = {
  id: string;
  name: string;
  path?: string;
  deckUrl?: string;
  fixedDeck?: boolean;
};

const root = process.cwd();
const manifest = JSON.parse(
  fs.readFileSync(path.join(root, 'public', 'agents', 'agents.json'), 'utf8'),
) as { agents: ManifestAgent[] };

describe('bundled alakazam-playbook agent', () => {
  it('registers the runtime and fixed sixty-card deck', () => {
    const agent = manifest.agents.find((candidate) => candidate.id === 'alakazam-playbook');
    expect(agent).toMatchObject({
      id: 'alakazam-playbook',
      name: 'フーディンAI（現行sample_a）',
      path: 'public/agents/alakazam-playbook/main.py',
      deckUrl: '/agents/alakazam-playbook/deck.csv',
      fixedDeck: true,
    });
    const deck = fs.readFileSync(path.join(root, 'public', 'agents', 'alakazam-playbook', 'deck.csv'), 'utf8')
      .split(/\r?\n/u)
      .map((row) => row.trim())
      .filter(Boolean);
    expect(deck).toHaveLength(60);
  });

  it('imports main.py and returns its sixty-card deck without bundled cg binaries', () => {
    const mainPath = path.join(root, 'public', 'agents', 'alakazam-playbook', 'main.py');
    const python = process.env.PYTHON || 'python';
    const program = [
      'import importlib.util, json, pathlib, sys',
      'path = pathlib.Path(sys.argv[1]).resolve()',
      'spec = importlib.util.spec_from_file_location("cabt_bundled_alakazam", path)',
      'module = importlib.util.module_from_spec(spec)',
      'spec.loader.exec_module(module)',
      'print(json.dumps({"deckSize": len(module.agent({"select": None}))}))',
    ].join('; ');
    const result = spawnSync(python, ['-c', program, mainPath], { encoding: 'utf8' });
    expect(result.status, result.stderr).toBe(0);
    expect(JSON.parse(result.stdout)).toEqual({ deckSize: 60 });
    expect(fs.existsSync(path.join(root, 'public', 'agents', 'alakazam-playbook', 'cg'))).toBe(false);
  });
});
```

- [ ] **Step 2: 新AI未登録によりテストが失敗することを確認する**

Run: `npx vitest run src/lib/home/bundledAgents.test.ts`

Expected: `agent` が `undefined` のため `registers the runtime and fixed sixty-card deck` がFAILする。

- [ ] **Step 3: AgentOptionとagents.jsonへ固定デッキAIを登録する**

`src/lib/home/catalog.ts` の `AgentOption` に次を追加する。

```ts
fixedDeck?: boolean;
```

`public/agents/agents.json` の `agents` 配列へ次を追加する。

```json
{
  "id": "alakazam-playbook",
  "name": "フーディンAI（現行sample_a）",
  "description": "現行playbookをルールベースへ落とし込んだフーディンAI。専用60枚デッキで自動操作します。",
  "path": "public/agents/alakazam-playbook/main.py",
  "deckUrl": "/agents/alakazam-playbook/deck.csv",
  "fixedDeck": true
}
```

- [ ] **Step 4: LocalEngineのパス解決テストへ新AIを追加する**

`src/engine/localEngine.test.ts` の `wires agent-controlled players to their selected agent paths` を次の期待値になるよう更新する。

```ts
const res = await engine.start({
  player1: { deck: Array(60).fill(1), control: 'agent', agentId: 'alakazam-playbook' },
  player2: { deck: Array(60).fill(2), control: 'agent', agentId: 'mega-lucario-ex' },
});

expect(res.ok).toBe(true);
expect(bridgePayload?.agentControlled).toEqual([true, true]);
expect(bridgePayload?.agentPaths).toEqual([
  'public/agents/alakazam-playbook/main.py',
  'public/agents/mega-lucario-ex/main.py',
]);
```

- [ ] **Step 5: 登録・import・パス解決テストを通す**

Run: `npx vitest run src/lib/home/bundledAgents.test.ts src/engine/localEngine.test.ts`

Expected: 両テストファイルがPASSし、Pythonスモークテストの終了コードが0になる。

- [ ] **Step 6: 内蔵AI登録をコミットする**

```powershell
git add -- public/agents/agents.json src/lib/home/catalog.ts src/lib/home/bundledAgents.test.ts src/engine/localEngine.test.ts
git commit -m "feat: 現行フーディンAIを内蔵"
```

---

### Task 3: 現行フーディンAIだけ専用デッキへ固定

**Files:**
- Create: `src/lib/game/agentDeck.ts`
- Create: `src/lib/game/agentDeck.test.ts`
- Modify: `src/App.svelte`
- Modify: `src/lib/components/ImportScreen.svelte`

**Interfaces:**
- Consumes: `AgentOption.fixedDeck`、`PlayerControl`、現在のAI ID。
- Produces: `fixedAgentDeckSource(control: PlayerControl, agentId: string, agents: readonly AgentOption[]) -> string | null` と、`ImportScreen` の `player1DeckSourceLocked` / `player2DeckSourceLocked` props。

- [ ] **Step 1: 固定判定の失敗テストを書く**

`src/lib/game/agentDeck.test.ts` を次の内容で作成する。

```ts
import { describe, expect, it } from 'vitest';
import { fixedAgentDeckSource } from './agentDeck';

const agents = [
  { id: 'normal', name: '通常AI', deckUrl: '/agents/normal/deck.csv' },
  { id: 'alakazam-playbook', name: 'フーディンAI（現行sample_a）', deckUrl: '/agents/alakazam-playbook/deck.csv', fixedDeck: true },
];

describe('fixedAgentDeckSource', () => {
  it('returns the paired source only for a fixed agent-controlled seat', () => {
    expect(fixedAgentDeckSource('agent', 'alakazam-playbook', agents)).toBe('alakazam-playbook');
    expect(fixedAgentDeckSource('agent', 'normal', agents)).toBeNull();
    expect(fixedAgentDeckSource('self', 'alakazam-playbook', agents)).toBeNull();
    expect(fixedAgentDeckSource('agent', 'missing', agents)).toBeNull();
  });
});
```

- [ ] **Step 2: ヘルパー未実装で失敗することを確認する**

Run: `npx vitest run src/lib/game/agentDeck.test.ts`

Expected: `Cannot find module './agentDeck'`

- [ ] **Step 3: 固定デッキ判定を最小実装する**

`src/lib/game/agentDeck.ts` を次の内容で作成する。

```ts
import type { AgentOption } from '../home/catalog';
import type { PlayerControl } from './httpClient';

export function fixedAgentDeckSource(
  control: PlayerControl,
  agentId: string,
  agents: readonly AgentOption[],
): string | null {
  if (control !== 'agent') return null;
  const agent = agents.find((candidate) => candidate.id === agentId);
  return agent?.fixedDeck === true && !!agent.deckUrl ? agent.id : null;
}
```

- [ ] **Step 4: Appで固定ソースを復元し続ける**

`src/App.svelte` へ次のimportとderived値を追加する。

```ts
import { fixedAgentDeckSource } from './lib/game/agentDeck';

let player1FixedDeckSource = $derived(fixedAgentDeckSource(player1Control, player1AgentId, agents));
let player2FixedDeckSource = $derived(fixedAgentDeckSource(player2Control, player2AgentId, agents));
```

既存の2つのペアデッキ `$effect` を、通常AIは初回だけ、固定AIは常時専用ソースへ戻す次の形にする。

```ts
$effect(() => {
  const paired = selectedPlayer1Agent?.deckUrl ? selectedPlayer1Agent.id : null;
  if (player1Control !== 'agent' || !paired) return;
  if (lastPairedAgent1 !== paired || (player1FixedDeckSource && player1DeckSource !== player1FixedDeckSource)) {
    lastPairedAgent1 = paired;
    player1DeckSource = paired;
  }
});
$effect(() => {
  const paired = selectedPlayer2Agent?.deckUrl ? selectedPlayer2Agent.id : null;
  if (player2Control !== 'agent' || !paired) return;
  if (lastPairedAgent2 !== paired || (player2FixedDeckSource && player2DeckSource !== player2FixedDeckSource)) {
    lastPairedAgent2 = paired;
    player2DeckSource = paired;
  }
});
```

`ImportScreen` 呼び出しへ次を渡す。

```svelte
player1DeckSourceLocked={player1FixedDeckSource !== null}
player2DeckSourceLocked={player2FixedDeckSource !== null}
```

- [ ] **Step 5: メニューの固定AIデッキ選択だけ無効化する**

`src/lib/components/ImportScreen.svelte` の `Props`、分割代入、2つのデッキselectを次の契約へ更新する。

```ts
player1DeckSourceLocked?: boolean;
player2DeckSourceLocked?: boolean;
```

```ts
player1DeckSourceLocked = false,
player2DeckSourceLocked = false,
```

```svelte
<select id="p1-deck" value={player1DeckSource} disabled={busy || player1DeckSourceLocked}
  title={player1DeckSourceLocked ? 'このAIは専用デッキを使用します' : undefined}
  onchange={(event) => {
    player1DeckSource = event.currentTarget.value;
    onDeckSourceChange(0, event.currentTarget.value);
  }}>
```

```svelte
<select id="p2-deck" value={player2DeckSource} disabled={busy || player2DeckSourceLocked}
  title={player2DeckSourceLocked ? 'このAIは専用デッキを使用します' : undefined}
  onchange={(event) => {
    player2DeckSource = event.currentTarget.value;
    onDeckSourceChange(1, event.currentTarget.value);
  }}>
```

- [ ] **Step 6: 固定判定・型検査・本番ビルドを通す**

Run: `npx vitest run src/lib/game/agentDeck.test.ts src/lib/home/bundledAgents.test.ts`

Expected: 全テストPASS。

Run: `npx tsc -p tsconfig.build.json`

Expected: 終了コード0、型エラーなし。

Run: `npm run build`

Expected: Vite本番ビルド完了。

- [ ] **Step 7: 専用デッキ固定をコミットする**

```powershell
git add -- src/lib/game/agentDeck.ts src/lib/game/agentDeck.test.ts src/App.svelte src/lib/components/ImportScreen.svelte
git commit -m "feat: フーディンAIを専用デッキに固定"
```

---

### Task 4: 実CABT自動操作とデプロイ同期の確認

**Files:**
- Create: `scripts/e2e-alakazam-agent.mjs`
- Modify: `C:\dev\pokeca-ai\scripts\deploy_hf.sh`

**Interfaces:**
- Consumes: `POST /local-engine`、ヘッダー `x-cabt-client`、`public/agents/alakazam-playbook/deck.csv`。
- Produces: 実CABTで人間対AIが開始できることを示すE2E終了コードと、デプロイ前同期の強制実行。

- [ ] **Step 1: 人間対フーディンAIのE2Eスクリプトを書く**

`scripts/e2e-alakazam-agent.mjs` を次の内容で作成する。

```js
import fs from 'node:fs';

const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:8095';
const CLIENT_ID = `e2e-alakazam-${Date.now()}`;
const deck = fs.readFileSync(new URL('../public/agents/alakazam-playbook/deck.csv', import.meta.url), 'utf8')
  .split(/\r?\n/u)
  .map((row) => row.trim())
  .filter(Boolean);

if (deck.length !== 60) throw new Error(`フーディンAIデッキが60枚ではありません: ${deck.length}`);

const results = [];
for (const agentSeat of [0, 1]) {
  const humanSeat = 1 - agentSeat;
  const players = [0, 1].map((seat) => seat === agentSeat
    ? { name: 'フーディンAI（現行sample_a）', deck, control: 'agent', agentId: 'alakazam-playbook' }
    : { name: '人間', deck, control: 'self' });
  const response = await fetch(`${BASE}/local-engine`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-cabt-client': `${CLIENT_ID}-${agentSeat}` },
    body: JSON.stringify({ type: 'startGame', payload: { player1: players[0], player2: players[1] } }),
  });
  const body = await response.json();
  if (!response.ok || !body.ok) throw new Error(`seat ${agentSeat} 対戦開始失敗: ${JSON.stringify(body)}`);
  if (!body.sessionId) throw new Error(`seat ${agentSeat}: CABTセッションIDが返りませんでした。`);
  if (!Array.isArray(body.view?.players) || body.view.players.length !== 2) throw new Error(`seat ${agentSeat}: 2人分の対戦画面が返りませんでした。`);
  if (!Array.isArray(body.sequence)) throw new Error(`seat ${agentSeat}: AI自動処理を含むsequenceが返りませんでした。`);
  const interactivePrompts = (body.view.prompts ?? []).filter((prompt) => prompt.fields?.playbackOnly !== true);
  if (interactivePrompts.some((prompt) => prompt.playerIndex !== humanSeat)) {
    throw new Error(`seat ${agentSeat}: AI側の未処理プロンプトがGUIへ残っています。`);
  }
  results.push({ agentSeat, sessionId: body.sessionId, frames: body.sequence.length, activePlayerIndex: body.view.activePlayerIndex });
}

process.stdout.write(`${JSON.stringify(results)}\n`);
```

- [ ] **Step 2: デプロイ前に同期を強制する**

`C:\dev\pokeca-ai\scripts\deploy_hf.sh` の `echo "=== ビルドコンテキストを組み立て中 ==="` より前へ次を追加する。

```bash
echo "=== 現行フーディンAIを同期中 ==="
python "$SRC/cabt-viewer/scripts/sync_sample_a_agent.py"
```

これにより同期元不足、必須ファイル不足、60枚不一致では `set -e` によりデプロイを開始しない。

- [ ] **Step 3: 実CABTサーバーでE2Eを実行する**

ローカルエンジンを別プロセスで次の環境により起動する。

```powershell
$env:CABT_ENGINE_MODE='native'
$env:PYTHON='python'
$env:CABT_SAMPLE_SUBMISSION_DIR='C:\dev\pokeca-ai\sample_submission'
$env:LOCAL_ENGINE_PORT='8095'
npm run dev:engine
```

別ターミナルで実行する。

Run: `node scripts/e2e-alakazam-agent.mjs`

Expected: AIがプレイヤー1・2のどちらでも `sessionId`、`frames`、`activePlayerIndex` を含むJSONが出力され、AI側の未処理プロンプトを残さず終了コード0。

- [ ] **Step 4: 配布コンテキストにも同期済みAIが入ることを確認する**

Run: `python ..\scripts\build_hf_space.py`

Expected: `=== assembled C:\dev\pokeca-ai\hf-space ===`

Run: `Test-Path '..\hf-space\cabt-viewer\public\agents\alakazam-playbook\main.py'; (Get-Content '..\hf-space\cabt-viewer\public\agents\alakazam-playbook\deck.csv' | Where-Object { $_.Trim() }).Count`

Expected: `True` と `60`

- [ ] **Step 5: E2Eとデプロイ同期変更を記録する**

`deploy_hf.sh` はCABT Viewerリポジトリ外なので、Viewer側ではE2Eだけをコミットする。

```powershell
git add -- scripts/e2e-alakazam-agent.mjs
git commit -m "test: フーディンAI対戦開始を検証"
```

---

### Task 5: 全体回帰検証と共有URL反映

**Files:**
- Verify only: CABT Viewerの全変更
- Preserve: `public/game-logs/logs.json`、`public/game-logs/local-*.json`

**Interfaces:**
- Consumes: Task 1〜4のコミットと `C:\dev\pokeca-ai\scripts\deploy_hf.sh`。
- Produces: 全テスト・型検査・本番ビルド・共有URLの動作確認結果。

- [ ] **Step 1: 同期が再現可能で差分を生まないことを確認する**

Run: `npm run test:sample-a-sync`

Expected: `Ran 4 tests` と `OK`

Run: `npm run sync:sample-a`

Expected: 同期成功。

Run: `git diff --exit-code -- public/agents/alakazam-playbook`

Expected: 終了コード0。

- [ ] **Step 2: 全Vitest・型検査・本番ビルドを通す**

Run: `npm test`

Expected: 全テストPASS。失敗テスト、skip追加、削除なし。

Run: `npx tsc -p tsconfig.build.json`

Expected: 終了コード0。

Run: `npm run build`

Expected: 終了コード0。

- [ ] **Step 3: 差分とユーザーログ保護を確認する**

Run: `git diff --check`

Expected: 出力なし。

Run: `git status --short`

Expected: 実装対象がすべてコミット済みで、既存の `public/game-logs/logs.json` と `public/game-logs/local-*.json` だけがユーザー変更として残る。

- [ ] **Step 4: 共有URLへデプロイする**

Run from `C:\dev\pokeca-ai\cabt-viewer`: `& 'C:\Program Files\Git\bin\bash.exe' '..\scripts\deploy_hf.sh'`

Expected: 同期成功、Space push成功、ストレージ掃除完了または掃除のみ警告、HF側Dockerビルド開始。

- [ ] **Step 5: 共有版の配布ファイルと画面を確認する**

Run: `Invoke-RestMethod 'https://kahtgf-pokeca-cabt.hf.space/agents/agents.json' | ConvertTo-Json -Depth 6`

Expected: `alakazam-playbook`、`フーディンAI（現行sample_a）`、`fixedDeck: true` を含む。

Run: `(Invoke-WebRequest 'https://kahtgf-pokeca-cabt.hf.space/agents/alakazam-playbook/deck.csv').Content -split "`n" | Where-Object { $_.Trim() } | Measure-Object | Select-Object -ExpandProperty Count`

Expected: `60`

共有版のメニューでプレイヤー2を `AI`、AIを `フーディンAI（現行sample_a）` にすると専用デッキが選ばれ、デッキ選択が無効になり、`対戦開始` 後は人間の選択だけがGUIへ表示されることを確認する。
