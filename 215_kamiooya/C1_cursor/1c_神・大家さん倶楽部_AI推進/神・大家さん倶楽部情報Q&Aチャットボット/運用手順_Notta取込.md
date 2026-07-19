# Notta / WeStudy 動画文字起こし 取込手順

## エクスポート設定（依頼時）

Notta から次をダウンロードしてください。

1. **Excel (.xlsx)** — Include timestamps ON / Include speakers ON / Merge full text OFF
2. **SRT (.srt)** — 同内容（照合用）

保存先（推奨）:

```text
…/神・大家さん倶楽部情報Q&Aチャットボット/inbox/notta/YYYY-MM-DD/
```

## 取込コマンド

```bash
cd ~/git-repos/215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット

# dry-run（件数・警告確認）
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/notta_to_knowledge.py \
  --input inbox/notta/YYYY-MM-DD/xxx.xlsx \
  --meta meta/notta_lessons.yaml \
  --video-id your_video_id \
  --dry-run

# ローカルミラーへ登録（Supabase 復旧後は --skip-supabase を外す）
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/notta_to_knowledge.py \
  --input inbox/notta/YYYY-MM-DD/xxx.xlsx \
  --meta meta/notta_lessons.yaml \
  --video-id your_video_id \
  --title "講義タイトル" \
  --video-url "https://..."
```

SRT との突合:

```bash
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/notta_to_knowledge.py \
  --input inbox/notta/YYYY-MM-DD/xxx.srt \
  --video-id your_video_id --dry-run
```

## テスト

```bash
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/tests/test_notta_to_knowledge.py
```

## Supabase 復旧後

**新規プロジェクトは作らない**（Free は `kamiooya-qa` 1本にテーブル追加。`.cursor/rules/jarvis-supabase-free-one-project.mdc`）。

1. Dashboard でプロジェクトを Active にする（休止時は Resume。旧 URL が NXDOMAIN なら Restore）
2. SQL Editor で `apps/kamiooya-qa-web/supabase/schema.sql` を実行（`jarvis_heartbeat` 含む）
3. `scripts/.env` に `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` を設定（GitHub Secrets も同名）
4. コメント全件ミラー:

```bash
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/bootstrap_knowledge_mirror.py \
  --csv exports/full_authors_bootstrap_20260720.csv
```

5. 動画チャンクを同様に再取込（`--skip-supabase` なし）

## Supabase 新規プロジェクト（Jarvis 自動作成）

Management API でプロジェクト作成 → schema 適用 → `.env` 書き込みまで自動化しています。

1. [Access Tokens](https://supabase.com/dashboard/account/tokens) でトークン発行  
   または Cursor 内ブラウザの GitHub ログイン完了後に Jarvis が Dashboard から進める
2. `~/git-repos/.env.jarvis_private` に追記（**チャットに貼らない**）:

```bash
SUPABASE_ACCESS_TOKEN=sbp_xxxxx
```

3. 「保存した」と一声 → Jarvis が次を実行:

```bash
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/provision_supabase_project.py --reuse-if-exists
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/bootstrap_knowledge_mirror.py \
  --csv exports/full_authors_bootstrap_20260720.csv
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/sample_notta_e2e.py --with-supabase
```

## サンプル Notta での接続確認

全部の講義は不要。**サンプル 1本**で経路確認する想定です。

```bash
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/sample_notta_e2e.py
# Supabase 復旧後
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/sample_notta_e2e.py --with-supabase
```

届いたサンプルを inbox に置く場合:

```text
…/inbox/notta/YYYY-MM-DD/sample.xlsx
…/inbox/notta/YYYY-MM-DD/sample.srt
```

```bash
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/accept_notta_inbox.py
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/accept_notta_inbox.py --apply --with-supabase
```

---

## 正本の整理


| 役割 | 場所 |
|---|---|
| 原本（xlsx/srt） | OneDrive `inbox/notta/` |
| ローカル検証DB | `state/knowledge_local.sqlite3` |
| クラウド投影 | Supabase `comments` / `knowledge_*` |
| 表示 | Raimo アプリ / kamiooya-qa-web |

## 実データ到着後の受入れチェック（1回で完了）

1. ファイルを `inbox/notta/YYYY-MM-DD/` へ保存（xlsx + srt）
2. 列・文字コード確認後:

```bash
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/accept_notta_inbox.py
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/accept_notta_inbox.py --apply
# Supabase 復旧済みなら --skip-supabase を外す（accept スクリプト既定は skip）
```

3. xlsx と srt の先頭・中間・末尾の時刻／話者を突合（dry-run の warnings を確認）
4. ローカル検索でタイトル・`start_label`・秒数が返ることを確認
5. Supabase 投入後、Raimo / Next チャットで代表質問 → 出典パネルに動画タイトル・時刻リンクが出ることを確認

※ fixture（`fixtures/notta/`）でのパーサ・冪等・accept 経路は 2026-07-20 時点で検証済み。
