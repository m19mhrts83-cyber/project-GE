#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Promote an approved user to master_admin via Raimo bootstrap API."""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

CHATBOT = Path(__file__).resolve().parents[1]


def load_env() -> None:
    for p in [
        Path.home() / "git-repos" / ".env.jarvis_private",
        CHATBOT / "scripts" / ".env",
    ]:
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
    email = (sys.argv[1] if len(sys.argv) > 1 else "").strip() or (
        os.environ.get("PERSONAL_EMAIL") or os.environ.get("RAIMO_PORTAL_EMAIL") or ""
    ).strip()
    if not email:
        print("usage: bootstrap_master_admin.py <email>", file=sys.stderr)
        return 2
    app_url = (os.environ.get("RAIMO_APP_URL") or "").rstrip("/")
    secret = (os.environ.get("NOTIFY_SHARED_SECRET") or "").strip()
    if not app_url:
        raise SystemExit("RAIMO_APP_URL 未設定")
    if not secret:
        raise SystemExit("NOTIFY_SHARED_SECRET 未設定")
    url = app_url + "/miniAppApi/be_nXbcTm3EumRbotHtAwGGXb45raHz0/admin/bootstrap-master"
    body = json.dumps({"email": email, "secret": secret}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode())
    user = (data or {}).get("user") or {}
    print(
        "ok role=",
        user.get("role"),
        "email=",
        user.get("email"),
        "id=",
        user.get("id"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
