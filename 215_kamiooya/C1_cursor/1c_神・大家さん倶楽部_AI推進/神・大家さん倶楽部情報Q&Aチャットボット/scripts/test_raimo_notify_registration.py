#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 1: Call Raimo POST /notify/registration (register 未接続の単体検証)."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))
DEFAULT_API_BASE = (
    "https://ma-54t2keqdelz3.raimo-app.buzz/miniAppApi/be_nXbcTm3EumRbotHtAwGGXb45raHz0"
)


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
    api_base = (
        os.environ.get("RAIMO_MINIAPP_API_BASE") or DEFAULT_API_BASE
    ).rstrip("/")
    email = (sys.argv[1] if len(sys.argv) > 1 else "").strip() or "phase1-raimo-notify@example.com"
    url = f"{api_base}/notify/registration"
    payload = {
        "email": email,
        "registered_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST"),
        "note": "Phase1 Raimo /notify/registration 単体テスト",
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    print("POST", url)
    print("payload email=", email)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
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
