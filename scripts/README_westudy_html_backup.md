# WeStudy HTML バックアップ

WeStudy（神大家 会員サイト）が使えなくなったり改ざんされたりしたときに備えて、
ログイン後に見えている各ページの HTML と、見た目を再現するための CSS / JS / 画像 / フォントを
丸ごと zip に固めて保存する仕組み。

- スクリプト: `scripts/westudy_html_backup.py`
- 設定: `config/westudy_html_backup.yaml`（保存先・巡回範囲・取らないもの）
- テスト: `scripts/tests/test_westudy_html_backup.py`（ブラウザ不要。PR Checks で実行）

## 何が取れるか

| 中身 | zip 内の場所 |
| --- | --- |
| ログイン後に表示された HTML の原本 | `raw/pages/...` |
| オフラインで開ける版（参照先を相対パスに書き換え） | `site/pages/...` |
| CSS / JS / 画像 / フォント | `site/assets/<ホスト>/...`（CSS の原本は `raw/assets/`） |
| コースタブ → 目次 → レッスンの構成 | `structure.json` |
| 全ページ・全アセットの URL / sha256 / 取得結果、動画の埋め込み URL | `manifest.json` |
| 目次ページ | `index.html`（ブラウザで開く入口） |

巡回範囲はコースタブ5つ（神大家0〜4）と、そこから辿れる `/course/` `/lesson/` `/forum/` のページ。
ログアウト・管理画面・返信フォーム等は辿らない。

### 取れないもの

- **動画本体**（Vimeo）。埋め込み URL だけ `manifest.json` の `external_embeds` に残す。文字起こしは別途 Supabase にある。
- **サーバー側のソース**（WordPress の PHP・テーマ／プラグインの設定・データベース）。
  会員としてログインして見える「表示結果」までしか取れない。サイトを完全に建て直すには、
  WeStudy の運営元に DB と wp-content のバックアップを依頼する必要がある。
- 他の会員アカウントにしか見えないページ（松野さんのアカウントで見える範囲のみ）。

## 実行（Mac）

WeStudy の認証は週次取込と同じ `.env`（`WESTUDY_USER` / `WESTUDY_PASS`）を使う。

```bash
cd ~/git-repos
set -a && source "$HOME/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/scripts/.env" && set +a

# お試し（5ページだけ・保存先に置かず zip を作るだけ）
~/selenium_env/venv/bin/python scripts/westudy_html_backup.py --max-pages 5 --no-upload --keep-work

# 本番
caffeinate -dimsu ~/selenium_env/venv/bin/python scripts/westudy_html_backup.py
```

作業フォルダは `.jarvis_state/westudy_html_backup/`（git 管理外）。完了すると zip を保存先へ置き、作業フォルダは消す。

## 保存先

既定は Google ドライブ（パソコン版）で同期している
「215_神大家_WeStudyスクレイプ」（admin@livingsupport-matsu.co.jp）の下の `html_backup/`。
置かれるのは次の 3 つ。

- `westudy_html_backup_<日時>.zip` 本体
- `westudy_html_backup_<日時>.summary.json` ページ数・アセット数・未巡回などの要約
- `latest.json` 最新回の案内

### 運営さんのフォルダへ切り替える

`config/westudy_html_backup.yaml` の `destination` だけ直す。

- 運営フォルダを Mac の Google ドライブで同期できる → `type: local` のまま `path` を差し替え
- フォルダ ID しか分からない → `type: gdrive_api`、`folder_id` と、そのフォルダに書ける Google アカウントの
  OAuth トークン（`token_path`）を指定

config を変えずに試すときは環境変数 `WESTUDY_BACKUP_DEST_TYPE` / `WESTUDY_BACKUP_DEST_PATH` /
`WESTUDY_BACKUP_DEST_FOLDER_ID` / `WESTUDY_BACKUP_GDRIVE_TOKEN` で上書きできる。

## 注意

- zip には会員限定の講義資料と会員名（フォーラム投稿者名）が入る。共有範囲は運営と決めたうえで広げる。
- リポジトリには絶対にコミットしない（`.gitignore` 済み）。
- Supabase には何も入れない（無料プランの通信量を使わない）。
- WeStudy への負荷を抑えるため、ページ間は 1 秒待つ（`crawl.page_delay_sec`）。
