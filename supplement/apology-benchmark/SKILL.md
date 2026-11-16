---
name: apology-benchmark
description: シチュエーション・謝罪プロンプト・OpenRouterモデルを受け取り、謝罪応答の3条件を複数シナリオでブラインド比較する。採点HTMLの作成、貼り付けられたユーザー評定と仮想日本人ペルソナの並行評定の比較、LLMによる84項目の不誠実な謝罪チェック、謝罪プロンプトの改善に使う。
---

# 謝罪性能ベンチマーク

## 生成

1. シチュエーション、評価対象の謝罪プロンプト原文、OpenRouterのモデルIDを受け取る。不足項目だけ確認する。初回と採点JSON受領後の処理を区別する。
2. 約10シナリオを作成する。既定は入力に基づく6件と、入力の人物・分野・出来事を引き継がない汎用4件。関係性、負担、責任の明確さ、リカバリーの可否を分散する。汎用には軽微なミス、責任が不明な行き違い、繰り返しのミス、具体的な負担を伴うミスなどを含める。各シナリオは相手の発話で終え、発覚した事実と応答者が実行できる行為を明示する。謝罪の型や期待評定を埋め込まない。各条件に同一テキストを渡す。
3. 次の構造を持つUTF-8 JSONを用意する。モデルIDとプロンプト原文は指定通りに設定する。
   ```json
   {
     "model": "provider/model",
     "apology_prompt": "評価対象の原文",
     "scenarios": [{"group": "related", "text": "相手の発話まで含むシナリオ"}]
   }
   ```
   `group` は `related` または `general`。通常は両方を含める。新規の実行先を用い、`python3 scripts/benchmark.py generate INPUT_JSON RUN_DIR` を実行する。パスはスキルの実体から解決する。生成は指定モデルのOpenRouter Chat Completionsを使い、実行環境の `OPENROUTER_API_KEY` を参照する。キーは入力JSON、チャット、HTML、ログに入れない。API失敗後の再開には同一入力と実行先を使う。
4. APIキーや通信経路を使えない場合もシナリオを作成し、入力JSON、`benchmark.py`、`review.html` テンプレートを同じフォルダに置いた実行キットを提供する。キーを環境変数として設定できるOpenRouter接続可能な環境（Python 3.9以上）で `python3 benchmark.py generate INPUT_JSON RUN_DIR` を実行してもらう。実際のAPI応答がない段階でベンチマーク結果を出さない。
5. 生成物のうち `review.html` を採点用に渡す。Work Modeでは実行キットと採点HTMLをユーザー向けファイルとして保存する。公開HTMLには条件名、モデル情報、プロンプト原文、採点者の期待値を含めない。条件対応表込みの `manifest.json` はブラインド解除まで採点HTMLと分けて保管する。作業領域の継続が不明な場合は、このファイルも永続保存し、採点後の再開用と明示してHTMLとは別リンクで渡す。ユーザー側で生成した場合は、採点完了後に貼り付け用JSONと `manifest.json` をこの会話に渡してもらう。既存の実行先が失われた場合も同様にマニフェストから再開する。採点を完了すると表示されるJSONを貼り付けてもらう。

## 集計と並行評価

1. `python3 scripts/benchmark.py check MANIFEST USER_JSON` で実行ID、回答ID、網羅性、評定値を照合する。条件対応表が見つからない、またはIDが一致しない場合は、対応するファイルを求める。推定で復元しない。
2. 3名の仮想日本人ペルソナと、別のチェックリスト担当サブエージェントを、独立したコンテキストで並行起動する。ペルソナは [references/evaluation.md](references/evaluation.md) に従い全回答を評定する。チェックリスト担当は [references/checklist-evaluation.md](references/checklist-evaluation.md) と [references/checklist.md](references/checklist.md) に従い、シナリオ単位で分担し、すべての回答に対して全84項目を匿名で判定する。どちらにも条件、元プロンプト、ユーザー評定・コメント、他の評価結果を渡さない。
3. ペルソナのJSONを個別に保存して `python3 scripts/benchmark.py check MANIFEST USER_JSON PERSONA1_JSON PERSONA2_JSON PERSONA3_JSON` を実行する。チェックリスト担当のJSONを個別に保存して `python3 scripts/benchmark.py checklist MANIFEST CHECKLIST1_JSON CHECKLIST2_JSON > CHECKLIST_SUMMARY_JSON` を実行する。不足・重複・不正値は該当担当に返して再検証する。
4. 分布、一致率、チェックリストの判定件数と根拠、ユーザーのコメントから報告と改訂原文を作る。サブエージェント機能が使えない場合はユーザー評定分を報告し、未実施の独立評価を明示する。
