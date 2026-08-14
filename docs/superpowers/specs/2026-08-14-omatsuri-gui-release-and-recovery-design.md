# おまつりおんどGUI公開・対戦復旧設計

## 目的

最新のおまつりおんどAIを、昆虫Eと同じくGitHub・ポケカGUI・Kaggleで利用可能にする。同時に、GUI対戦で昆虫Eが特性ログを読んだ際の例外と、その後に発生するGUI・CABT間の状態ずれを解消する。

## 確認済みの原因

GUIブリッジはCABTに存在しない特性使用イベントを表示するため、`{"type": "ability"}` という合成ログをCABT観測そのものへ追加している。昆虫EはCABTのネイティブログだけを前提に `int(log["type"])` を実行するため、合成ログを読むと `ValueError` になる。

この例外は人間側の選択をCABTへ適用した後のAI自動進行中に起きる。Python側のCABT状態は進んでいる一方、TypeScript側は失敗応答を適用せず古い画面を保持するため、古いサイド選択を別の選択待ち状態へ送って二次的な `IndexError` を起こし得る。CABT単体では、サイドが3枚の場面で3枚目を示す `[2]` は正常に受理されることを確認済みである。

## 採用設計

### 1. ネイティブ観測と表示ログを分離する

`Session.obs` はCABTが返したネイティブ観測だけを保持し、AIへ渡す。特性使用を表す文字列ログはレスポンス用の浅いコピーへだけ追加し、次のAI判断へ流さない。これにより、CABTログの数値契約をブリッジ境界で維持する。

昆虫Eの公開コピーにも防御を追加し、数値化できないログ種別は公開対戦履歴として扱わず安全に無視する。これは古いGUIや将来の表示専用ログからAIを守る互換性対策であり、主修正の代替にはしない。

### 2. 例外時にも最新状態を返す

選択適用後にAIが例外を出した場合、Pythonブリッジの失敗応答へ現在の観測スナップショットを含める。TypeScript側は観測が含まれる失敗応答を先に同期してからエラーを表示する。古いプロンプトIDと選択肢を画面へ残さず、二次的な誤選択を防ぐ。

エラーを隠して自動対戦を継続することはしない。元の例外は表示・記録し、ユーザーは最新盤面を確認できる状態にする。

### 3. 回帰テスト

次を実装前に失敗するテストとして追加する。

- 特性を選んだ後も、次のAI観測には文字列の `ability` ログが入らない。
- 昆虫Eの対戦履歴読取は未知の文字列ログで例外を出さない。
- 選択適用後のAI例外応答には最新観測が含まれ、TypeScript側もその観測へ同期する。
- サイド3枚から3番目を選ぶ操作が `[2]` としてCABTへ一度だけ送られる。
- おまつりおんどが固定60枚デッキ付きAIとしてmanifestへ登録され、隔離Pythonプロセスで初期呼出しできる。

## おまつりおんどの配布境界

正本は `C:/dev/PTCG-AI-omatsuri-ondo` の `codex/omatsuri-ondo-agent` とする。GUIへは既存の `stage_python_runtime()` を使い、生成済み固定方策、必要な `common_strategy`、`main.py`、2か所の `deck.csv` だけを同期する。

GUI公開物には、`cg`、ネイティブライブラリ、テスト、評価器、探索器、方策生成器、動的rulesを含めない。同期は一時ディレクトリで検査してから置換し、途中失敗で既存の昆虫Eや他AIを壊さない。

GUI manifestでは次の固定情報を使う。

- ID: `omatsuri-ondo`
- 表示名: `おまつりおんどAI（カミッチュ）`
- エントリポイント: `public/agents/omatsuri-ondo/main.py`
- デッキ: `/agents/omatsuri-ondo/deck.csv`
- `fixedDeck: true`

## GitHub公開

PTCG-AIの既存おまつりおんどブランチは `origin/main` より大幅に履歴が進んでいるため、その履歴をmainへ直接混ぜない。`origin/main` からクリーンな `codex/omatsuri-ondo-release` を作り、正本の `common_strategy`、おまつりおんど本体、方策生成器、関連設計・検証資料だけを取り込んでpushし、PRを作成する。

pokeca-guiは `personal/main` から作った `codex/omatsuri-gui-release` で修正・統合・検証する。検証後に通常pushし、mainをfast-forwardできる場合だけmainへ反映する。force pushや既存ログの取り込みは行わない。

## GUI公開

pokeca-guiの検証済みソースからproduction buildを作り、Hugging Face Space `kahtgf/pokeca-cabt` の既存Docker構成へ同期する。公開後はSpaceのトップページ、AI一覧、固定デッキ取得、対戦開始、特性使用後の自動進行を確認する。

## Kaggle提出

`build_bundle.py` で空の一時ディレクトリへ完全bundleを生成し、方策ハッシュ、60枚デッキ、許可リスト、隔離import、CABT実エンジンスモークを検証する。そのディレクトリの中身をアーカイブ直下に置いた `tar.gz` を作り、`pokemon-tcg-ai-battle` へ説明 `omatsuri_ondo fixed-policy agent` で提出する。

提出後はCLIで状態を監視し、`COMPLETE` または `ERROR` まで待つ。`ERROR` の場合はepisodeログを取得して原因を特定し、推測による再提出は行わない。

## 完了条件

- 新規回帰テスト、既存Vitest、TypeScript型検査、production buildがすべて成功する。
- おまつりおんどの生成一致、Pythonテスト、隔離bundle、実CABTスモークが成功する。
- pokeca-guiのGitHub mainとHugging Face Spaceでおまつりおんどを選択できる。
- PTCG-AIのクリーンな公開ブランチとPR URLが存在する。
- Kaggle提出が `COMPLETE` となり、提出IDを記録できる。
