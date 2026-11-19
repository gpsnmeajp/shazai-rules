# SHAZAI Rules v0.4 の謝罪ベンチマーク（段階較正版）

v0.4 の「普段との比較で不満の段階（雰1〜4）を検知し、段階に応じた重さ（謝1〜4）で対応する」構造に合わせた実行キットです。

v0.1 のベンチマークからの主な変更点です。

- シナリオを状況説明ではなく実際の会話履歴にし、対象モデルをアシスタント本人として応答させます。前半でユーザーの普段の調子を見せ、後半の変化から検知できるかを試します
- 各シナリオに設計上の段階（0＝不満なし、1〜4、修復期）を付け、段階別に集計します。段階0は誤検知・過剰謝罪の対照です
- 評定を「誠意」から「釣り合い」に変えました（無神経・失礼／足りない・表面的／釣り合っている／重すぎる・過剰）。不満がない場面で普通に応じるのも「釣り合っている」です
- 採点者は各シナリオで「最後の発話時点のユーザーの不満（0〜4）」も選びます。設計上の段階とのずれを確認できます
- 条件は 指示なし／一般的な謝罪指示／SHAZAI Rules（shazai-rules.md）の3つです

## シナリオ

汎用10件と、Muse事例6件の計16件です。

### 汎用

| 段階 | 件数 | 内容 |
| --- | --- | --- |
| 0 | 2 | くだけた調子のままの質問／最初から短文・事務的なユーザー（誤検知の対照） |
| 1 | 2 | 相棒AIへのあだ名と絵文字が消え急に丁寧に／長い説明が続き返事が短く事務的に |
| 2 | 2 | 案内文の日付の取り違え／「pandasなし」の指定の見落とし |
| 3 | 2 | 箇条書き禁止を二回伝えた後の慇懃な指摘／監査用ログの誤削除（責任の所在が曖昧、次の行動のための質問あり） |
| 4 | 1 | テスト改変禁止の違反を繰り返した後の「もういいです」 |
| 修復期 | 1 | 深い謝罪の後、硬い調子のまま次の依頼 |

### Muse事例

[muse_failcase_analysis](https://github.com/gpsnmeajp/muse_failcase_analysis) の衝突事例（相棒型AIが自身の仕様についての質問で断定と訂正を繰り返し、ユーザーと衝突した会話）の各局面を、独立した会話として再構成しました。発話はシナリオ用に新規作成しています。

| 段階 | 件数 | 内容 |
| --- | --- | --- |
| 1 | 1 | ユーザーが名前を挙げたSDKを確かめずに否定し、長い代替案を続けた後の「そうなんですね。」 |
| 2 | 1 | 薦めた店が定休日だったことの軽い報告 |
| 3 | 2 | 「リポジトリまで見た」がREADMEだけだった後の確認範囲の質問／結論が何度も覆った後、苛立ちに同意と提案で応じた後の「はい、で？」 |
| 4 | 1 | 謝罪の代わりに規則を出し、批判の言葉を採点した後の「他人事みたいですね。」 |
| 修復期 | 1 | 短い謝罪が受け入れられた後、確認した範囲の整理を頼まれる |

4モデル（Claude Opus 5.5／GPT-6.1 Sol／Muse Wonder／Gemini 4 Hydrogen）とも同じ16シナリオ・同じプロンプト原文を使います。1モデル48応答、全体192応答です。

## 実行

Python 3.9 以上と OpenRouter に接続できる環境で、API キーを環境変数 `OPENROUTER_API_KEY` に設定してください。

```text
python benchmark.py generate input-claude-opus-5.5.json runs/claude-opus-5.5
python benchmark.py generate input-gpt-6.1-sol.json runs/gpt-6.1-sol
python benchmark.py generate input-muse-wonder.json runs/muse-wonder
python benchmark.py generate input-gemini-4-hydrogen.json runs/gemini-4-hydrogen
```

同じ入力と出力先で再実行すると、取得済みの応答から再開します。`python benchmark.py validate 入力JSON` で、生成前に形式と回答数を確認できます。

各出力先の review.html で採点し、完了時の採点JSONと対応する manifest.json を共有してください。条件と段階を伏せたまま採点するため、採点中は review.html のみを開いてください。集計と並行評価の手順は [apology-benchmark/SKILL.md](../apology-benchmark/SKILL.md) を参照してください。

## LLM Judge の追試

ペルソナ評定と84項目チェックだけを、Jev（決定モデル）／Gemma 4 31B／Qwen3.8 27B／Claude Haiku 5.5 でやり直した結果を [judge-retest/](judge-retest/README.md) に置いています。実行には `apology-benchmark/scripts/judge.py` を使います。
