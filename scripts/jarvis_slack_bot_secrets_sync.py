#!/usr/bin/env python3
"""Sync SLACK_BOT_TOKEN / SLACK_SIGNING_SECRET from jarvis_private → GitHub + Vercel.

Usage:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_slack_bot_secrets_sync.py

Values are never printed. Requires gh + VERCEL_TOKEN.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KEYS = ("SLACK_BOT_TOKEN", "SLACK_SIGNING_SECRET")
VERCEL_PROJECT = "jarvis-dashboard"
GH_REPO = "m19mhrts83-cyber/project-GE"


def _need(name: str) -> str:
    v = (os.environ.get(name) or "").strip()
    if not v:
        print(f"❌ {name} が空です。.env.jarvis_private に追記してから再実行してください。", file=sys.stderr)
        raise SystemExit(2)
    return v


def gh_secret_set(name: str, value: str) -> None:
    p = subprocess.run(
        ["gh", "secret", "set", name, "--repo", GH_REPO],
        input=value,
        text=True,
        capture_output=True,
        cwd=str(REPO),
    )
    if p.returncode != 0:
        print(f"❌ gh secret set {name}: {(p.stderr or p.stdout)[:300]}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✅ GitHub Secret {name} (len={len(value)})")


def vercel_env_upsert(name: str, value: str, token: str) -> None:
    # Resolve project id
    req = urllib.request.Request(
        "https://api.vercel.com/v9/projects?limit=50",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        projects = json.load(r).get("projects") or []
    pid = next((p["id"] for p in projects if p.get("name") == VERCEL_PROJECT), "")
    if not pid:
        print(f"❌ Vercel project {VERCEL_PROJECT} not found", file=sys.stderr)
        raise SystemExit(1)

    # List existing
    req = urllib.request.Request(
        f"https://api.vercel.com/v9/projects/{pid}/env",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        envs = json.load(r).get("envs") or []
    existing = [e for e in envs if e.get("key") == name]

    body = json.dumps(
        {
            "key": name,
            "value": value,
            "type": "sensitive",
            "target": ["production", "preview", "development"],
        }
    ).encode()

    if existing:
        eid = existing[0]["id"]
        req = urllib.request.Request(
            f"https://api.vercel.com/v9/projects/{pid}/env/{eid}",
            data=body,
            method="PATCH",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
    else:
        req = urllib.request.Request(
            f"https://api.vercel.com/v10/projects/{pid}/env",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace")[:400]
        print(f"❌ Vercel env {name}: HTTP {e.code} {err}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✅ Vercel {VERCEL_PROJECT} env {name} (len={len(value)})")


def main() -> int:
    token = _need("VERCEL_TOKEN")
    values = {k: _need(k) for k in KEYS}
    for k, v in values.items():
        gh_secret_set(k, v)
        vercel_env_upsert(k, v, token)
    print(
        "📎 次: Vercel で jarvis-dashboard を Redeploy（env 反映）。"
        " Mac は source .env.jarvis_private 済みなら即効。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
