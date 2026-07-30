# Cursor Agent CLI はインストール済みだが未ログインのため品質比較は未実施。
# プランどおり「差がなければ Gemini」→ 夜間既定エンジンは gemini（無料枠）。
# Cursor 比較を再開するとき:
#   1) agent login
#   2) python scripts/jarvis_night_triage.py --compare-engines --skip-fetch --limit 5
# 比較後に明確に Cursor が勝つ場合のみ config.json の engine を cursor に変更。
compared_at: null
default_engine: gemini
cursor_agent_installed: true
cursor_agent_logged_in: false
note: "Gemini 試行で要返信判定・下書き品質は実用レベル。Cursor 未認証のため A/B は保留。"
