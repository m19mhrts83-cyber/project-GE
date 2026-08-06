# 夜間トリアージ下書きエンジン

- **既定**: `gemini`（件数が多いためコスパ優先。2026-08-06 再確認）
- Cursor Agent CLI は Trust／ログイン次第で使えるが、夜間バッチの既定にはしない
- Claude は夜間 `engine` 選択肢に未配線（チャット／Cloud で人手見直し向け）

再開するとき:
1. `agent login` ＋ CLI に `--trust`
2. `python scripts/jarvis_night_triage.py --compare-engines --skip-fetch --limit 5`
3. 明確に Cursor が勝つ場合のみ `config.json` の `engine` を `cursor` に変更

compared_at: null
default_engine: gemini
note: "件数多・コスパ → Gemini 既定。ユーザーがダッシュボード／Jarvis Cloud で修正する運用。"
