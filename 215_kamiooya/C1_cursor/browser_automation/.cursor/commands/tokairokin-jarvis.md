---
description: Jarvis にそのまま貼る東海労金 tokairokin 実行・トラブルシュート用（全文版）
---

## Jarvis にそのまま貼る用（全文・これだけで可）

次のブロックをコピーして Jarvis に送ってください。金額は指示があれば `--amount` だけ書き換えます。

```
東海労金 tokairokin を非対話で実行して結果を要約して。

1) 作業ディレクトリと Python 環境（Homebrew Python / PEP 668 ではグローバル pip が使えないため、必ずこのフォルダの venv を使う）

cd /Users/matsunomasaharu/git-repos/215_kamiooya/C1_cursor/browser_automation

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
・「ログイン後トップページ相当と判断し、合言葉の Enter 待ちをスキップ」→ 合言葉なしルートで正常（BLI001Dispatch トップ到達済み）。
・B0470 / BER020 → 無操作切断。再実行か、対話実行（--non-interactive なし・Terminal.app）を提案。
・合言葉・質問が検出できない（かつトップスキップメッセージも無い）→ config の secret_phrase_page_markers・secret_phrase_auto の match、secret_phrase_dom_wait_seconds を確認。
・iframe 関連は secret_phrase_check_iframes: true が既定。
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
| トップ到達・合言葉なし | stderr にスキップメッセージが出れば Enter 待ちはしない（fetch_after_login の post_login_dashboard_detect） |
| 合言葉が見えない／検出できない | BLI017 経路のみ該当。`secret_phrase_dom_wait_seconds`、`secret_phrase_page_markers`、`match` の見直し |
| B0470 | セッション切れ・タイマー。再ログインや待機調整、`TOKAIROKIN_NON_INTERACTIVE_TRANSFER_MENU_WAIT_CAP` |

詳細設定キーは `config_tokairokin.yaml` と `config_tokairokin.example.yaml` を参照。
