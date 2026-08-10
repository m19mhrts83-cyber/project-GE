# BugBot（このリポジトリ向け）

PR レビュー時の観点。本番 Vercel / GHA の定例 Fail 監視は
`scripts/jarvis_ops_fail_watch.py` 本線（BugBot は置換しない）。

## 見てほしいこと

- Next.js（`apps/jarvis-dashboard`）の Server / Client 境界（`next/headers` を client に引かない）
- 秘密（`SUPABASE_*` / `JARVIS_SUPABASE_*` / API キー）をコード・ログに出さない
- 対外メール送信の承認ゲートを外していないか
- Vercel の Root Directory 想定外のビルド破壊（無関係な一括設定）
- 個人 Free Supabase の第3プロジェクト追加や提供用 DB への個人テーブル混在

## Autofix

有効なら、指摘の修正は最小 diff・既存トーン維持。全面リデザインやナビ再編はしない。
