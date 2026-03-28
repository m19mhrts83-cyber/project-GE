# LINE Open Chat 常駐運用（launchd）

## 目的
- `chrline_open_chat_realtime_watch.py` を macOS 起動後も自動で継続実行
- 日次で API/認証の健全性を確認し、失敗時に再ログイン推奨ログを残す

## インストール
`line_unofficial_poc` 直下で実行します。

```bash
chmod +x launchd/*.sh
./launchd/install_open_chat_launchd.sh
```

## 動作確認
- 監視ログ: `~/Library/Logs/line_open_chat/watch.err.log`
- ヘルスチェック履歴: `~/Library/Logs/line_open_chat/healthcheck_history.log`
- 要再ログインアラート: `~/Library/Logs/line_open_chat/NEEDS_RELOGIN.txt`

## 再ログイン（必要時）
`NEEDS_RELOGIN.txt` が増える場合は次を実行します。

```bash
cd ~/git-repos/line_unofficial_poc
.venv/bin/python chrline_qr_login_poc.py
```

## アンインストール
```bash
./launchd/uninstall_open_chat_launchd.sh
```
