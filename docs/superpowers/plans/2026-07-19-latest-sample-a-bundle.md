# 最新sample_a GUI内蔵更新 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PTCG-AIコミット`d6fe7b1`のsample_aをGUIへ内蔵し、公開`pokeca-gui/main`へpushする。

**Architecture:** Gitアーカイブで固定コミットのsample_aだけを一時領域へ展開し、既存同期スクリプトの環境変数オーバーライド経由で内蔵先を原子的に置換する。GUIの未コミット対戦ログは同期・コミット対象にしない。

**Tech Stack:** Git、Python 3.12、unittest、Node.js、Vitest、Vite、GitHub CLI

## Global Constraints

- 同期元は`d6fe7b12eb6ef212d3026461d3dad25e4b88794b`へ固定する。
- `artifacts`、テスト、`cg`、キャッシュ、未コミット変更を内蔵しない。
- 既存の対戦ログ変更をステージしない。
- 検証成功後だけ`personal/main`へpushする。

---

### Task 1: 固定コミットからsample_aを同期

**Files:**
- Modify: `public/agents/alakazam-playbook/**`

**Interfaces:**
- Consumes: `C:/dev/PTCG-AI`のコミット`d6fe7b1`、`scripts/sync_sample_a_agent.py`。
- Produces: 最新sample_aの実行時ファイルと60枚デッキだけを含む内蔵エージェント。

- [ ] **Step 1:** `git -C C:\dev\PTCG-AI archive --format=zip -o $env:TEMP\sample-a-d6fe7b1.zip d6fe7b1 src/agent/sample_a`を実行する。
- [ ] **Step 2:** 一時ディレクトリへ展開し、`main.py`、`deck.csv`、必須ルールファイルの存在を確認する。
- [ ] **Step 3:** `CABT_SAMPLE_A_SOURCE_DIR`を展開先`src/agent/sample_a`へ設定し、`python scripts/sync_sample_a_agent.py`を実行する。
- [ ] **Step 4:** `python scripts/test_sync_sample_a_agent.py`を実行し、4テスト成功を確認する。

### Task 2: GUI統合を検証してコミット

**Files:**
- Verify: `public/agents/alakazam-playbook/**`
- Preserve unstaged: `public/game-logs/**`、`scripts/__pycache__/**`

**Interfaces:**
- Consumes: Task 1の内蔵エージェント。
- Produces: テスト・ビルド済みのGUIコミット。

- [ ] **Step 1:** `npm test`を実行し、31ファイル・全テスト成功を確認する。
- [ ] **Step 2:** `npm run build`を実行し、終了コード0を確認する。
- [ ] **Step 3:** `git diff -- public/agents/alakazam-playbook`で同期差分だけを確認する。
- [ ] **Step 4:** `git add public/agents/alakazam-playbook`後、対戦ログ・キャッシュがステージされていないことを確認する。
- [ ] **Step 5:** `git diff --cached --check`後、`git commit -m "feat: 最新sample_aをGUIへ内蔵"`を実行する。

### Task 3: 公開リポジトリへpush

**Files:**
- Push: `main` → `popopopo2918/pokeca-gui:main`

**Interfaces:**
- Consumes: Task 2の検証済みコミット。
- Produces: 友達が取得できる最新公開GUI。

- [ ] **Step 1:** `git push personal main`を実行する。
- [ ] **Step 2:** `git ls-remote personal refs/heads/main`と`git rev-parse HEAD`が一致することを確認する。
- [ ] **Step 3:** `gh repo view popopopo2918/pokeca-gui`でvisibility=`PUBLIC`を確認する。
