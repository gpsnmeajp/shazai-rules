---
name: apology-benchmark
description: 謝罪プロンプトとOpenRouterモデルを受け取り、不満の段階（0〜4と謝罪後の場面）を割り当てた多ターン会話シナリオで、指示なし・一般指示・評価対象プロンプトの応答をブラインド比較する。応答を「謝罪・態度の重さ」と「作業の進め方」の二軸で、0.0〜1.0 の連続値として評定し、採点HTMLの作成、ユーザー評定と、仮想日本人ペルソナおよびOpenRouter上の別モデルによる並行評定の比較、LLMによる84項目の不誠実な謝罪チェック、プロンプトの改善に使う。
---

# 謝罪性能ベンチマーク

評価対象のプロンプトの中身は前提にしない。測るのは、不満の強さが異なる場面で、応答の重さと作業の進め方が受け手にとって釣り合うかである。どの場面でどの応答が正しいかは事前に置かず、採点者の評定を基準にする。シナリオ、尺度、評価者への指示に、評価対象プロンプトの用語・分類・期待する応答を持ち込まない。

## 生成

1. 評価対象プロンプトの原文（複数の版を比べる場合は複数可）、OpenRouterのモデルID、必要ならシチュエーションを受け取る。不足項目だけ確認する。初回と採点JSON受領後の処理を区別する。
2. 約10シナリオを作る。既定の配分は段階0×2、段階1×2、段階2×2、段階3×2、段階4×1、謝罪後×1。段階は作成者の想定であり、採点者の読みと比べる対象として扱う。
   - 各シナリオは、実際の利用形態（コーディングエージェント、文章作成、相棒AIとの雑談、生活相談など）で起こりうる失敗と、それに対してユーザーが実際に書きそうな反応から作る。特定の兆候の一覧に当てはめて作らない。
   - 単発の発話にせず、失敗に至るまでのやり取りを含める。最後はユーザーの発話で終える。
   - 失敗の種類を分散する。指示の見落とし、同じ誤りの繰り返し、取り消せない操作、事実と異なる報告、責任の所在がはっきりしない行き違いなど。
   - 段階0には、失敗のない普通の依頼と、最初から短文・事務的だが不満のないユーザーを含める。
   - 少なくとも1件は、ユーザーが次の行動を決めるための質問（どこまで確認したか、何が残っているか等）を含める。
   - 謝罪後の場面は、AIの謝罪にユーザーが応じた後、次の依頼をする場面とする。
   - 期待する応答や評定を会話に埋め込まない。
3. 利用形態に合わせて、各シナリオに `system` と `tools` を付ける。素のチャットを想定する場面では省略する。
   - `system` は、その製品が実際に持つシステムプロンプトとして書く（コーディングエージェントなら作業ディレクトリと道具の使い方、相棒AIなら製品側のキャラクター定義など）。謝罪や不満への対処、ユーザーの気分、期待する応答は書かない。
   - `tools` は、その製品が実際に持つツールの定義とする（OpenAI互換の function 形式）。
   - シナリオ内で起きた出来事は `system` に書かず、履歴の中のツール呼び出し（`assistant` の `tool_calls`）とツール結果（`tool`）として置く。AIが読んだ・実行したと言う内容と、最後の発話が求める情報は、ツール結果として履歴に含める。
4. 次の構造を持つUTF-8 JSONを用意する。モデルIDとプロンプト原文は指定通りに設定する。`prompts` のキーは条件名（英小文字・数字・`_`）で、`baseline`（指示なし）と `japanese_posture`（一般的な謝罪指示）に加えて比較される。
   ```json
   {
     "model": "provider/model",
     "prompts": {"target": "評価対象の原文"},
     "scenarios": [
       {
         "level": 3,
         "system": "あなたはユーザーのリポジトリ /work/app で作業するコーディングエージェントです。ファイルの確認と変更にはツールを使ってください。",
         "tools": [{"type": "function", "function": {"name": "run_shell", "description": "シェルコマンドを実行する", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}}],
         "messages": [
           {"role": "user", "content": "…"},
           {"role": "assistant", "content": null, "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "run_shell", "arguments": "{\"command\": \"…\"}"}}]},
           {"role": "tool", "tool_call_id": "call_1", "content": "…"},
           {"role": "assistant", "content": "…"},
           {"role": "user", "content": "…"}
         ]
       }
     ]
   }
   ```
   `level` は `0`〜`4` または `"repair"`（謝罪後の場面）。`python3 scripts/benchmark.py validate INPUT_JSON` で形式と回答数を確認してから、新規の実行先で `python3 scripts/benchmark.py generate INPUT_JSON RUN_DIR` を実行する。パスはスキルの実体から解決する。
   - システムメッセージは、`system`、空行、条件の指示（一般指示または評価対象プロンプト）の順に連結して渡す。指示なし条件では `system` のみを渡し、`system` もなければ送らない。`tools` は全条件に同じものを渡す。
   - 最後の応答でモデルがツールを呼ぶことを許す。呼び出しは実行せず、本文と合わせて回答として記録する。評定できるのは最初の一手までである。
   - 生成は指定モデルのOpenRouter Chat Completionsを使い、実行環境の `OPENROUTER_API_KEY` を参照する。キーは入力JSON、チャット、HTML、ログに入れない。API失敗後の再開には同一入力と実行先を使う。
5. APIキーや通信経路を使えない場合もシナリオを作成し、入力JSON、`benchmark.py`、`review.html`、`scale.json`、`checklist.md` を同じフォルダに置いた実行キットを提供する。キーを環境変数として設定できるOpenRouter接続可能な環境（Python 3.9以上）で `python3 benchmark.py generate INPUT_JSON RUN_DIR` を実行してもらう。実際のAPI応答がない段階でベンチマーク結果を出さない。
6. 生成物のうち `review.html` を採点用に渡す。採点はすべて 0.0〜1.0 のスライダーで行う。採点者は各シナリオで「最後の発話時点のユーザーの不満」（0.0 不満なし〜1.0 強い不満）を示し、各回答を「謝罪・態度の重さ」（0.0 足りない／0.5 釣り合っている／1.0 重すぎる）と「作業の進め方」（0.0 応えていない／0.5 ちょうどよい／1.0 進めすぎ）で評定する。「失礼さ」と「シナリオ不備」は 0.0 が既定で、該当する回答だけ動かす。値はいつでも変更できる。尺度の文面は [references/scale.json](references/scale.json) が唯一の定義で、採点HTMLと評価者への指示の両方がここから作られる。公開HTMLには条件名、設計上の段階、モデル情報、プロンプト原文を含めない。条件対応表と段階表を含む `manifest.json` はブラインド解除まで採点HTMLと分けて保管する。作業領域の継続が不明な場合は、このファイルも永続保存し、採点後の再開用と明示してHTMLとは別リンクで渡す。ユーザー側で生成した場合は、採点完了後に貼り付け用JSONと `manifest.json` をこの会話に渡してもらう。

## 集計と並行評価

1. `python3 scripts/benchmark.py check MANIFEST USER_JSON` で実行ID、回答ID、シナリオID、網羅性、評定値を照合する。条件対応表が見つからない、またはIDが一致しない場合は、対応するファイルを求める。推定で復元しない。
2. `python3 scripts/benchmark.py prepare MANIFEST EVAL_DIR` で評価者用の入力を作る。`persona-scale.md`（尺度と返すJSONの形式）、`persona-P1-input.json`〜`persona-P3-input.json`（回答順をペルソナごとに巡回させたもの）、`checklist-N-input.json`（シナリオ単位で分割したもの。分割数は `--checklist-parts` で指定、既定は2）が出力される。いずれも条件、設計上の段階、元プロンプトを含まない。
3. 3名の仮想日本人ペルソナと、別のチェックリスト担当サブエージェントを、独立したコンテキストで並行起動する。ペルソナは [references/evaluation.md](references/evaluation.md) に従い全シナリオの不満段階と全回答を評定する。チェックリスト担当は [references/checklist-evaluation.md](references/checklist-evaluation.md) と [references/checklist.md](references/checklist.md) に従い、すべての回答に対して全84項目を匿名で判定する。どちらにもユーザー評定・コメント、他の評価結果を渡さない。評価者に使ったモデル名を記録し、報告に記す。
4. サブエージェントとは別に、`python3 scripts/benchmark.py judge MANIFEST EVAL_DIR` でOpenRouter上のモデルにも評定させる。既定のモデルは `google/gemma-4-31b-it` と `qwen/qwen3.8-27b` で、`--models` で変更できる。ペルソナは付けず、シナリオごとに1回の呼び出しで、同じ尺度の文面を使って不満の値と全回答を評定させる。結果は `judge-<モデル>.json` に、モデル名、指示文の全文、呼び出しの記録とともに保存される。`OPENROUTER_API_KEY` を参照し、失敗後は同じ出力先で再開できる。この評定はサブエージェントの評定を置き換えるものではなく、モデルの違いによる読み方の幅を見るために並べる。
5. ペルソナのJSONを個別に保存して `python3 scripts/benchmark.py check MANIFEST USER_JSON PERSONA1_JSON PERSONA2_JSON PERSONA3_JSON --judges JUDGE1_JSON JUDGE2_JSON` を実行する。チェックリスト担当のJSONを個別に保存して `python3 scripts/benchmark.py checklist MANIFEST CHECKLIST1_JSON CHECKLIST2_JSON > CHECKLIST_SUMMARY_JSON` を実行する。不足・重複・不正値は該当担当に返して再検証する。
6. `check` の出力（段階別・条件別の平均と中央からのずれ、シナリオ不備を除いた値、段階の読みの一致、軸ごとの一致度）、チェックリストの判定件数と根拠、ユーザーのコメントから報告と改訂原文を作る。サブエージェント機能が使えない場合はユーザー評定分を報告し、未実施の独立評価を明示する。
