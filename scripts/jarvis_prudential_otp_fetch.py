#!/usr/bin/env python3
"""
プルデンシャル Myページの確認番号を Gmail API で取得して stdout に出す。

用法:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_prudential_otp_fetch.py           # 真治（account 1）
  python scripts/jarvis_prudential_otp_fetch.py --account 2   # 千景

.env.jarvis_private:
  PRUDENTIAL_GMAIL_TOKEN_PATH / PRUDENTIAL_GMAIL_EXPECT_EMAIL（1人目）
  PRUDENTIAL_GMAIL_TOKEN_PATH_2 / PRUDENTIAL_GMAIL_EXPECT_EMAIL_2（2人目）
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FINANCE = REPO / "215_kamiooya/C1_cursor/finance"
MANUAL = REPO / "215_kamiooya/C1_cursor/1b_Cursorマニュアル"


def _load_jarvis_private() -> None:
    env = REPO / ".env.jarvis_private"
    if not env.is_file():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        if k and k not in os.environ:
            os.environ[k] = v.strip().strip('"').strip("'")


def _account_gmail_config(account: int) -> tuple[str, str]:
    if account <= 1:
        tok_key = "PRUDENTIAL_GMAIL_TOKEN_PATH"
        exp_key = "PRUDENTIAL_GMAIL_EXPECT_EMAIL"
        default_exp = "m19m.hrts83@gmail.com"
        default_tok = MANUAL / "token_m19m.json"
    else:
        tok_key = f"PRUDENTIAL_GMAIL_TOKEN_PATH_{account}"
        exp_key = f"PRUDENTIAL_GMAIL_EXPECT_EMAIL_{account}"
        default_exp = os.environ.get(f"PRUDENTIAL_USERNAME_{account}", "").strip()
        default_tok = MANUAL / "token_chk59.json"

    token = os.environ.get(tok_key, "").strip() or str(default_tok)
    expect = os.environ.get(exp_key, "").strip() or default_exp
    if not expect:
        raise SystemExit(
            f"{exp_key} または PRUDENTIAL_USERNAME_{account} を .env.jarvis_private に設定してください。"
        )
    return token, expect


def main() -> int:
    parser = argparse.ArgumentParser(description="プルデンシャル確認番号を Gmail API で取得")
    parser.add_argument(
        "--account",
        type=int,
        default=1,
        choices=[1, 2],
        help="1=真治（m19m） 2=千景（chk59）",
    )
    parser.add_argument(
        "--lookback-min",
        type=int,
        default=30,
        help="何分前までのメールを探すか（既定30）",
    )
    args = parser.parse_args()

    _load_jarvis_private()
    token_path, expect_email = _account_gmail_config(args.account)

    sys.path.insert(0, str(FINANCE))
    os.environ["PRUDENTIAL_GMAIL_TOKEN_PATH"] = token_path
    os.environ["PRUDENTIAL_GMAIL_EXPECT_EMAIL"] = expect_email

    from prudential_gmail_otp import poll_prudential_otp_from_gmail

    min_ms = int(time.time() * 1000) - args.lookback_min * 60 * 1000
    print(
        f"📧 account={args.account} expect={expect_email} token={Path(token_path).name}",
        file=sys.stderr,
    )
    code = poll_prudential_otp_from_gmail(
        to_email=expect_email,
        min_internal_date_ms=min_ms,
        max_wait_s=15,
        poll_s=2,
    )
    print(code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
