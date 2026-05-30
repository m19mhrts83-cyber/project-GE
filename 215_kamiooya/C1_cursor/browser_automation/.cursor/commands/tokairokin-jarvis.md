---
description: Jarvis にそのまま貼る東海労金 tokairokin 実行・トラブルシュート用（全文版）
---

## Jarvis にそのまま貼る用（全文・これだけで可）

次のブロックをコピーして Jarvis に送ってください。金額は指示があれば `--amount` だけ書き換えます。

```
東海労金 tokairokin を非対話で実行して結果を要約して。

1) 作業ディレクトリと Python 環境（Homebrew Python / PEP 668 ではグローバル pip が使えないため、必ずこのフォルダの venv を使う）

cd /Users/matsunomasaharu2/git-repos/215_kamiooya/C1_cursor/browser_automation

初回または ModuleNotFoundError のときだけ（venv が無い・壊れている場合）:

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium

2) 本実行（非対話・Enter を読まない）:

PYTHONWARNINGS=ignore TOKAIROKIN_NON_INTERACTIVE=1 \
  .venv/bin/python fetch_after_login.py tokairokin --non-interactive --amount 240000

※ グローバルの python3 を直接使わないこと（別環境だと dotenv / setuptools が無くて落ちる）。

3) 前提: browser_automation/.env に TOKAIROKIN_* が入っていること。振込先は TOKAIROKIN_DEFAULT_* か CLI で足りていること。

4) ログで次を見て報告すること:
・「【主経路】…合言葉の Enter 待ちをスキップ」→ 合言葉画面なしでログイン後トップ相当と判定済み（post_login_dashboard_detect）。この経路が既定の想定。
・「【主経路から外れた可能性】」→ ブラウザで実画面を確認。トップなら post_login_dashboard_detect を調整。合言葉が出ているなら secret_phrase_* を検討。
・B0470 / BER020 → 無操作だけでなく **振込 Dispatch の URL 直叩き**でも出ることがある。transfer_direct_first: false（メニュー優先）を確認。再実行や対話実行も検討。
・iframe 関連は secret_phrase_check_iframes: true が既定。
・OTP → 既定は fetch_otp_from_gmail: false（ワンタイムPW アプリ＋ユーザーがブラウザで入力・実行確定）。**スクリプト終了だけでは振込完了と断定しない**。統合ターミナルで Enter が自動処理される問題があるので、OTP 時は Terminal.app 実行を推奨。**非対話実行では OTP ホールドを期待しない**（ブラウザ完了はユーザー確認）。
・distutils / setuptools → requirements に setuptools あり。.venv で pip install -r requirements.txt をやり直す。

5) コード変更はユーザーが明示したときだけ。まずは設定・再実行で様子を見る。
```

---

## 参考（人間用・短く）

| 項目 | 内容 |
|------|------|
| Python | `.venv/bin/python` を固定で使用（`python3` 直実行しない） |
| 初回 | `python3 -m venv .venv` → `pip install -r requirements.txt` → `playwright install chromium` |
| 非対話 | `TOKAIROKIN_NON_INTERACTIVE=1` と `--non-interactive` がセット |
| 警告抑制 | `PYTHONWARNINGS=ignore` |
| トップ到達・合言葉なし（主経路） | 「【主経路】…スキップ」が出れば合言葉 Enter 待ちなし（post_login_dashboard_detect・allow_dispatch_url_without_body_markers） |
| 主経路から外れたログ | 「【主経路から外れた可能性】」→ 画面確認後に post_login_dashboard_detect または secret_phrase_* を調整 |
| B0470 | 無操作に加え不正な URL 直遷移でも発生しうる。メニュー経由・`transfer_direct_first: false` を確認 |
| OTP | fetch_otp_from_gmail: false 既定。**ユーザーがブラウザで入力・実行確定しないと振込は完了しない**。Terminal.app 推奨 |

詳細設定キーは `config_tokairokin.yaml` と `config_tokairokin.example.yaml` を参照。
