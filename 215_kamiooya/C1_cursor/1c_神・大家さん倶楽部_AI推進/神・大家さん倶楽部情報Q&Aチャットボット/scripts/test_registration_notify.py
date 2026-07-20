#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""POST test payload to registration-notify GAS webhook.

Usage:
  test_registration_notify.py [email]                    # type=registration（管理者宛）
  test_registration_notify.py --approval [email]         # type=approval（申請者宛）
  test_registration_notify.py --password-reset [email]   # type=password_reset（申請者宛）
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4

JST = timezone(timedelta(hours=9))


def load_env() -> None:
    roots = [
        Path.home() / "git-repos" / ".env.jarvis_private",
        Path(__file__).resolve().parents[1] / "scripts" / ".env",
    ]
    for p in roots:
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> int:
    load_env()
    args = [a for a in sys.argv[1:] if a]
    mode = "registration"
    if args and args[0] in ("--approval", "-a"):
        mode = "approval"
        args = args[1:]
    elif args and args[0] in ("--password-reset", "--reset", "-p"):
        mode = "password_reset"
        args = args[1:]

    url = (os.environ.get("NOTIFY_WEBHOOK_URL") or "").strip()
    secret = (os.environ.get("NOTIFY_SHARED_SECRET") or "").strip()
    app_url = (
        os.environ.get("NOTIFY_APP_URL")
        or os.environ.get("RAIMO_APP_URL")
        or "https://ma-54t2keqdelz3.raimo-app.buzz/"
    ).rstrip("/") + "/"

    default_email = (
        (os.environ.get("NOTIFY_ADMIN_TO") or "").split(",")[0].strip()
        if mode in ("approval", "password_reset")
        else "phase0-test@example.com"
    )
    email = (args[0] if args else "").strip() or default_email

    if not url or url.startswith("https://script.google.com/macros/s/PASTE"):
        print("NOTIFY_WEBHOOK_URL が未設定です。")
        return 1
    if not secret:
        print("NOTIFY_SHARED_SECRET が未設定です。")
        return 1
    if not email:
        print("送信先 email が未指定です（--approval / --password-reset 時は NOTIFY_ADMIN_TO か引数）。")
        return 1

    if mode == "approval":
        payload = {
            "secret": secret,
            "type": "approval",
            "email": email,
        }
        print("mode approval →", email)
    elif mode == "password_reset":
        token = str(uuid4())
        reset_url = f"{app_url}#reset-password?token={token}"
        # 日本時間で「今日＋7日」の 23:59 表示（メール用）
        now_jst = datetime.now(JST)
        end = (now_jst + timedelta(days=7)).replace(
            hour=23, minute=59, second=59, microsecond=999000
        )
        expires_display = f"{end.year}年{end.month}月{end.day}日 23:59（日本時間）"
        payload = {
            "secret": secret,
            "type": "password_reset",
            "email": email,
            "reset_url": reset_url,
            "expires_at": expires_display,
        }
        print("mode password_reset →", email)
        print("reset_url", reset_url)
        print("expires", expires_display)
    else:
        payload = {
            "secret": secret,
            "type": "registration",
            "email": email,
            "registered_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST"),
            "note": "手動テスト（scripts/test_registration_notify.py）",
        }
        print("mode registration → ADMIN_TO (payload email=", email, ")")

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read().decode("utf-8", errors="replace")
            print("status", r.status)
            print(body)
            return 0 if r.status == 200 else 1
    except urllib.error.HTTPError as e:
        print("status", e.code)
        print(e.read().decode("utf-8", errors="replace"))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
