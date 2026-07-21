# 昆虫E GUI内蔵・GitHub公開設計

## 目的

Kaggle提出ID `54879069` の「昆虫E」を、既存の「フーディンAI（現行sample_a）」を残したままCABT Viewerへ独立した対戦AIとして追加する。同じ実装をPTCG-AIの共有ブランチへ公開し、GUIのローカル版・GitHub版・共有URL版で同一の昆虫Eを利用できるようにする。

## 採用方式

昆虫Eは `public/agents/konchu-e/` に自己完結した実行時スナップショットとして内蔵する。GUIから別リポジトリを実行時に取得せず、Hugging Face上でもネットワーク依存なしで起動できる構成とする。

既存の `public/agents/alakazam-playbook/` は変更・置換せず、比較用AIとして維持する。

## PTCG-AI側

- `src/agent/fudein_ai_2/` の現行ランタイムを昆虫Eの正本とする。
- ランタイム、固定60枚デッキ、回帰テストを `kawanoooooo` ブランチへコミットする。
- リプレイ、評価DB、一時ファイル、認証情報、キャッシュはコミットしない。
- 全Pythonテスト、Kaggle入口テスト、compileallを通してからpushする。

## GUI側

- `public/agents/konchu-e/` へ昆虫Eの実行時依存だけを同期する。
- `public/agents/agents.json` に次を追加する。
  - ID: `konchu-e`
  - 表示名: `昆虫E`
  - 固定デッキ: 有効
  - 説明: Kaggle提出版のフーディンAIであることを明記
- 昆虫E選択時は同梱の `deck.csv` 60枚を自動使用する。
- 旧sample_aの登録・ファイル・選択動作は維持する。

## 同期対象

GUIへ含めるのは次の実行時ファイルだけとする。

- `main.py`, `deck.csv`, `__init__.py`
- `cards.py`, `catalog.py`, `environment_profiles.py`
- `memory.py`, `model.py`, `policy.py`, `proposals.py`
- `rule_manifest.py`, `strategy_config.py`
- `rules/`
- `data/top200_environment_2026-07-18.json`

`tests/`, `artifacts/`, `cg/`, `__pycache__/`, `.pytest_cache/`, 研究用CLIはGUIへ含めない。GUIサーバーが用意するCABT `cg` を従来どおり利用する。

## 検証

- PTCG-AI: 全unittest、Kaggle入口pytest、compileall、ローカル1試合。
- GUI: manifest登録、固定60枚デッキ、`main.py`読込、旧sample_a共存をテストする。
- GUI全体: Vitest、TypeScript型検査、Vite build。
- 配布前: 共有URL上のagents manifestと昆虫Eのdeck/runtime取得を確認する。

## 公開順序

1. PTCG-AIの昆虫Eを `kawanoooooo` へpushする。
2. そのコミット内容をGUIの独立スナップショットへ同期する。
3. GUIを `personal/main` へpushする。
4. Hugging Face共有URLへデプロイし、稼働確認する。

この順序により、GUIスナップショットの出典となるGitHubコミットを先に確定する。

## エラー時

- Python読込、デッキ60枚、GUIテストのいずれかが失敗した場合はpush・デプロイしない。
- Hugging Faceデプロイだけが失敗した場合、GitHubの正常なコミットは保持し、デプロイ原因を切り分ける。
- 未関連のゲームログや研究成果物は修正・削除しない。
