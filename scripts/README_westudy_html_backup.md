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
| レッスンからリンクされた配布資料（PDF・Excel 等、westudy.co.jp 内） | `site/assets/<ホスト>/...` |
| ページ全体の画面キャプチャ（コース・レッスン） | `screenshots/...` |
| WordPress REST API で取れた本文データ（固定ページ・投稿・レッスン等） | `api/wp-json/<種類>/page-NNN.json` |
| robots.txt・サイトマップ | `api/extra/` |
| コースタブ → 目次 → レッスンの構成 | `structure.json` |
| 全ページ・全アセットの URL / sha256 / 取得結果、動画の埋め込み URL | `manifest.json` |
| 目次ページ | `index.html`（ブラウザで開く入口） |

巡回範囲はコースタブ5つ（神大家0〜4）と、そこから辿れる `/course/` `/lesson/` `/forum/` のページ。
ログアウト・管理画面・返信フォーム等は辿らない。

### 取れないもの

- **動画本体**（Vimeo）。埋め込み URL だけ `manifest.json` の `external_embeds` に残す。動画は Vimeo 側にあるので WeStudy が落ちても消えない。文字起こしは別途 Supabase にある。
- **外部の配布資料**（Google ドライブ等へのリンク）。URL だけ `external_documents` に残す。
- **WordPress API が閉じている場合の本文データ**。そのときは `manifest.json` の `api` に HTTP ステータスだけ残る（HTML 側には本文がある）。
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

途中で止まったとき（Mac のスリープ・回線断など）は、10 ページごとに `_checkpoint.json` へ途中経過を保存しているので、
作業フォルダ名（日時）を指定すると続きから再開できる。

```bash
~/selenium_env/venv/bin/python scripts/westudy_html_backup.py --resume 20261028-130012
```

Chrome は 40 ページごとに作り直し、セッション切れ（InvalidSessionId）のときもその場で作り直して再ログインする。
1 ページの読み込みは 30 秒で打ち切る（`crawl.page_load_timeout_sec`）。

## 毎週の自動実行（Mac）

`launchd/install_westudy_html_backup_launchd.sh` を一度実行すると、毎週 日曜 12:00 に
`launchd/westudy_html_backup_runner.sh` が動く（Mac が寝ていたら次に起きたとき）。runner は

1. 途中で止まった回（`_checkpoint.json` が残っている作業フォルダ）があれば `--resume` で続きから
2. 全ページを巡回して zip を `02_バックアップデータ/` に置く
3. このプログラム一式を `01_ソースコード/` に書き出す（`--export-source`。毎回最新に上書き）

ログは `~/Library/Logs/westudy_html_backup/`。止めるときは `WESTUDY_HTML_BACKUP_DISABLE=1` か
`launchctl bootout gui/$(id -u)/com.matsunoma.westudy.html-backup`。今すぐ 1 回動かすときは
`launchctl kickstart gui/$(id -u)/com.matsunoma.westudy.html-backup`。

## 引き渡し用のソースコード

`config/westudy_html_backup.yaml` の `handover.files` が引き渡し対象。リポジトリと同じ相対パスで
`01_ソースコード/` に写すので、そのフォルダだけで動く（`VERSION.txt` に書き出し日時と元コミット）。

| ファイル | 役割 |
| --- | --- |
| `scripts/westudy_html_backup.py` | 本体。ログイン → 巡回 → HTML・アセット・画面・配布資料の保存 → zip → 保存先へ配置 |
| `config/westudy_html_backup.yaml` | 設定。保存先、巡回範囲、取らないもの、引き渡し対象 |
| `ProgramCode/alfred_python/westudy_lesson_pages.py` | WeStudy へのログインと、コースタブ → 目次 → レッスンの一覧取得（週次取込と共通） |
| `launchd/westudy_html_backup_runner.sh` | 毎週の実行役。途中再開・二重起動防止・ソースコード書き出し |
| `launchd/install_westudy_html_backup_launchd.sh` | Mac に毎週の予定を登録する |
| `scripts/tests/test_westudy_html_backup.py` | 動作確認のテスト（ブラウザ不要） |
| `scripts/requirements_westudy_html_backup.txt` | 必要な Python パッケージ |
| `scripts/README_westudy_html_backup.md` | この説明 |

## 保存先

既定は Google ドライブ（パソコン版）で同期している
「マイドライブ/217_westudyソースコードバックアップ/02_バックアップデータ」（admin@livingsupport-matsu.co.jp、2026-10-28 松野さん指定）。
置かれるのは次の 3 つ。

- `westudy_html_backup_<日時>.zip` 本体
- `westudy_html_backup_<日時>.summary.json` ページ数・アセット数・未巡回などの要約
- `latest.json` 最新回の案内

残すのは最新1回分（`destination.keep_last: 1`）。新しい zip を置き終えてから、前の回の zip と summary を消す。

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
