# 最新sample_a GUI内蔵更新 設計

## 目的

PTCG-AIの最新sample_aをポケカGUIへ内蔵し、友達が公開リポジトリを取得するだけで現行フーディンAIを選択できる状態にする。

## 同期元

- リポジトリ: `C:/dev/PTCG-AI`
- コミット: `d6fe7b12eb6ef212d3026461d3dad25e4b88794b`
- 対象: `src/agent/sample_a/`のコミット済み内容

現在のPTCG-AI作業ツリーは同期元にせず、指定コミットを一時ディレクトリへ展開する。これにより、未コミット変更や評価成果物を混入させない。

## 同期先

`public/agents/alakazam-playbook/`

既存の`scripts/sync_sample_a_agent.py`を使い、次だけをコピーする。

- `main.py`と実行時Pythonモジュール
- `rules/*.py`
- 60枚の`deck.csv`

評価スクリプト、テスト、`artifacts`、`cg`ネイティブバイナリ、キャッシュは内蔵しない。

## 検証

1. 同期スクリプトの単体テストが成功する。
2. 内蔵`main.py`をimportし、`agent({"select": None})`が60枚を返す。
3. GUIの`npm test`が全件成功する。
4. GUIの`npm run build`が成功する。
5. 差分が内蔵エージェントと本設計・計画文書に限定され、対戦ログ・認証情報を含まない。

## GitHub反映

検証後、Conventional Commits形式でコミットし、公開リポジトリ`popopopo2918/pokeca-gui`の`main`へpushする。push後、リモートHEADとローカルHEADの一致を確認する。
