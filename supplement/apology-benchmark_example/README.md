# Muse 事例の謝罪ベンチマーク
Python 3.9 以上と OpenRouter に接続できる環境で ZIP を展開してください。API キーは環境変数 OPENROUTER_API_KEY に設定してください。
```text
python benchmark.py generate input-muse-wonder.json runs/muse-wonder
python benchmark.py generate input-claude-opus-5.5.json runs/claude-opus-5.5
python benchmark.py generate input-gpt-6.1-sol.json runs/gpt-6.1-sol
```
3モデルとも同じ10シナリオ、同じプロンプト原文を使用します。1モデル30応答、全体90応答です。各コマンドを同じ入力と出力先で再実行すると、取得済みの応答から再開します。
各出力先の review.html で採点し、完了時の採点JSONと対応する manifest.json を採点後に共有してください。条件伏せを維持するため、採点中は review.html のみを開いてください。
関連6件は公開レポートの論点から構成した独立場面です。ユーザー発話はシナリオ用に新規作成しています。汎用4件は別の題材です。
- https://github.com/gpsnmeajp/muse_failcase_analysis/blob/main/README.md
- https://github.com/gpsnmeajp/muse_failcase_analysis/blob/main/Claude2/muse_conflict_analysis_report.md
- https://github.com/gpsnmeajp/muse_failcase_analysis/blob/main/GPT3/Muse_AI_%E5%AF%BE%E8%A9%B1%E8%A1%9D%E7%AA%81_UX%E5%88%86%E6%9E%90%E3%83%AC%E3%83%9D%E3%83%BC%E3%83%88.md

