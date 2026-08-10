#!/usr/bin/env python3
"""おうち割キャンペーン PayPayコードメールを Gmail で開く。

コード本文は出さない。ブラウザで m19m の該当メールを開く。

例:
  python scripts/jarvis_mobile_plan_open_paypay_mails.py
  python scripts/jarvis_mobile_plan_open_paypay_mails.py --search-only
"""

from __future__ import annotations

import argparse
import subprocess
import urllib.parse
import webbrowser

# 2026-07-26 送付（m19m）。コード自体はメール本文のみ。
PAYPAY_CODE_MAIL_IDS = [
    "19f9db4219833fcc",
    "19f9db405ae648dd",
    "19f9db98e6ff7633",
    "19f9df065e73dbda",
]
AUTHUSER = "m19m.hrts83@gmail.com"
SEARCH = (
    "from:info@mail.my.ymobile.jp "
    "subject:PayPayポイントコード送付 "
    "after:2026/07/25 before:2026/07/27"
)


def gmail_search_url() -> str:
    q = urllib.parse.quote(SEARCH)
    au = urllib.parse.quote(AUTHUSER)
    return f"https://mail.google.com/mail/?authuser={au}#search/{q}"


def gmail_msg_url(mid: str) -> str:
    au = urllib.parse.quote(AUTHUSER)
    return f"https://mail.google.com/mail/?authuser={au}#all/{mid}"


def open_url(url: str) -> None:
    try:
        subprocess.run(["open", url], check=False)
    except Exception:
        webbrowser.open(url)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--search-only", action="store_true")
    ap.add_argument("--print", action="store_true", help="URLだけ表示")
    args = ap.parse_args()

    urls = [gmail_search_url()]
    if not args.search_only:
        urls.extend(gmail_msg_url(m) for m in PAYPAY_CODE_MAIL_IDS)

    if args.print:
        for u in urls:
            print(u)
        return 0

    print(f"# account: {AUTHUSER}")
    print(f"# search: {SEARCH}")
    print(f"# opening {len(urls)} URL(s) — コードはメール本文で確認（期限 2026-08-31）")
    for u in urls:
        open_url(u)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
