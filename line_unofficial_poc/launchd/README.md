# LINE Open Chat 常駐運用（launchd）

## 目的
- `chrline_open_chat_realtime_watch.py` を macOS 起動後も自動で継続実行
- **メイン / スレッド返信 / 専用スレッド（event 54）** の新着を即時に `5.やり取り.md` へ追記
- 日次で API/認証の健全性を確認し、失敗時に再ログイン推奨ログを残す

## 前提（2026-07-19 判明の制約）
- Square **履歴読み取り API** は約17回で401→トークン失効しやすい（過去の一括バックフィルは非現実的）
- 常駐は **PUSH 受信**で新着を拾う（履歴読みとは別経路）
- 実行は必ず **`./run_patch.sh`（CHRLINE-Patch）** 経由
- 常駐起動時は **QR 禁止**（トークン切れは healthcheck が通知）
- **公式Mac版LINEは起動しない**。CHRLINEと同じデスクトップ認証枠を使うため、同時起動すると約90秒後に `V3_TOKEN_CLIENT_LOGGED_OUT` となる
- iPhone版LINE・iPhoneミラーリングは別枠なので併用可

## Mac版LINEとの競合防止
- 起動前にMac版LINEを検出した場合、runnerはトークンを使わず待機し、Mac版終了後に自動開始する
- 監視中にMac版LINEが起動した場合、5秒以内に検出して監視を正常停止する
- launchdがrunnerを再起動し、Mac版LINEが終了するまで待機する
- 保存トークンでのQRなし再起動は2026-07-20に実証済み

## インストール
`line_unofficial_poc` 直下で実行します。

```bash
chmod +x launchd/*.sh
# 初回だけ対話でトークン確保（必要なとき）
./run_patch.sh chrline_qr_login_poc.py
# 前景で数分動作確認してから常駐化を推奨
./run_patch.sh chrline_open_chat_realtime_watch.py --verbose
# Ctrl+C で止め、問題なければ:
./launchd/install_open_chat_launchd.sh
```

## 動作確認
- 監視ログ: `~/Library/Logs/line_open_chat/watch.err.log`
- ヘルスチェック履歴: `~/Library/Logs/line_open_chat/healthcheck_history.log`
- 要再ログインアラート: `~/Library/Logs/line_open_chat/NEEDS_RELOGIN.txt`
- 状態: `.line_auth/.chrline_open_chat_watch_status.json`（30秒ごとにheartbeat）

```bash
launchctl print "gui/$(id -u)/com.matsunoma.line.openchat.watch" | grep -E 'state =|pid =|last exit code'
tail -n 30 ~/Library/Logs/line_open_chat/watch.err.log
```

healthcheckは常駐中に別クライアントでAPIを呼ばない。プロセスとheartbeatだけを毎日4:10に確認する。

## パートナー確認バッチとの排他
常駐とバッチ同期は同一セッションを共有できない。バッチ前に一時停止:

```bash
./launchd/open_chat_watch_pause.sh
# … パートナー確認（LINE/オプチャ）…
./launchd/open_chat_watch_resume.sh
```

ロック競合時、バッチ側は `# open-chat skipped: realtime watch holds session lock` を出してスキップする。

## スリープ・再起動
- Macのスリープ中はPUSH受信も止まる
- 復帰後に接続が生きていればそのまま継続し、切断終了した場合はlaunchdが保存トークンで再起動する
- Mac再起動・ログイン後もlaunchdが自動起動する
- QRが必要なのは保存トークン自体がLINE側で失効した場合だけ

## 翌日の実投稿確認
1. `watch.err.log` に対象ルートの `# append ... kind=【スレッド】` が出ること
2. 対象の `5.やり取り.md` に同じmessageIdの `【スレッド】` 見出しが1件だけ入ること
3. `.chrline_open_chat_watch_status.json` の `last_append_at`・`last_append_route`・`last_append_kind` が更新されること

## 再ログイン（必要時）
`NEEDS_RELOGIN.txt` が増える場合は次を実行します。

```bash
cd ~/git-repos/line_unofficial_poc
./launchd/open_chat_watch_pause.sh
./run_patch.sh chrline_qr_login_poc.py
./launchd/open_chat_watch_resume.sh
```

## アンインストール
```bash
./launchd/uninstall_open_chat_launchd.sh
```
