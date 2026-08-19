#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NOTION_API_TOKEN を Vercel（dashboard + trade-desk）と GitHub Secrets へ投影する。

正本: .env.jarvis_private の NOTION_API_TOKEN
値はログに出さない。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_notion_token_sync.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_notion_token_sync.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
LOG_PREFIX = "📎 Notion token sync"
ENV_KEY = "NOTION_API_TOKEN"


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _token() -> str:
    tok = (os.environ.get(ENV_KEY) or "").strip()
    if not tok:
        print(f"{LOG_PREFIX}: FAIL {ENV_KEY} 未設定", file=sys.stderr)
        sys.exit(2)
    return tok


def _fp(tok: str) -> str:
    return hashlib.sha256(tok.encode("utf-8")).hexdigest()[:8]


def _project_ids(app: str) -> tuple[str, str, str]:
    env_project = {
        "jarvis-dashboard": os.environ.get("NOTION_VERCEL_DASHBOARD_PROJECT_ID", ""),
        "jarvis-trade-desk": os.environ.get("NOTION_VERCEL_TRADE_DESK_PROJECT_ID", ""),
    }.get(app, "")
    team = (os.environ.get("VERCEL_TEAM_ID") or "").strip()
    rel = {
        "jarvis-dashboard": REPO / "apps" / "jarvis-dashboard" / ".vercel" / "project.json",
        "jarvis-trade-desk": REPO / "apps" / "trade-desk" / ".vercel" / "project.json",
    }[app]
    if env_project.strip() and team:
        return env_project.strip(), team, app
    if rel.is_file():
        data = json.loads(rel.read_text(encoding="utf-8"))
        return (
            str(data.get("projectId") or ""),
            str(data.get("orgId") or team),
            str(data.get("projectName") or app),
        )
    return "", team, app


def _vercel_upsert(app: str, tok: str, vercel_token: str) -> bool:
    project_id, team_id, name = _project_ids(app)
    if not project_id:
        print(f"{LOG_PREFIX}: FAIL {app} projectId 不明", file=sys.stderr)
        return False
    qs = f"?teamId={team_id}" if team_id else ""
    headers = {
        "Authorization": f"Bearer {vercel_token}",
        "Content-Type": "application/json",
    }
    list_url = f"https://api.vercel.com/v9/projects/{project_id}/env{qs}"
    existing_ids: list[str] = []
    try:
        req = urllib.request.Request(list_url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        for env in body.get("envs") or []:
            if env.get("key") == ENV_KEY:
                eid = env.get("id")
                if eid:
                    existing_ids.append(str(eid))
    except Exception as e:  # noqa: BLE001
        print(f"{LOG_PREFIX}: {name} env list 警告 {type(e).__name__}", file=sys.stderr)

    for eid in existing_ids:
        del_url = f"https://api.vercel.com/v9/projects/{project_id}/env/{eid}{qs}"
        try:
            req = urllib.request.Request(del_url, headers=headers, method="DELETE")
            with urllib.request.urlopen(req, timeout=60) as resp:
                resp.read()
        except Exception as e:  # noqa: BLE001
            print(f"{LOG_PREFIX}: {name} env delete 警告 {type(e).__name__}", file=sys.stderr)

    create_url = f"https://api.vercel.com/v10/projects/{project_id}/env{qs}"
    payload = json.dumps(
        {
            "key": ENV_KEY,
            "value": tok,
            "type": "sensitive",
            "target": ["production", "preview"],
        }
    ).encode("utf-8")
    try:
        req = urllib.request.Request(create_url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp.read()
        print(f"{LOG_PREFIX}: OK Vercel {name} production+preview", file=sys.stderr)
        return True
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace")[:300]
        print(f"{LOG_PREFIX}: FAIL Vercel {name} HTTP {e.code}: {err}", file=sys.stderr)
        return False


def _gh_secret_set(tok: str) -> bool:
    from shutil import which

    if which("gh") is None:
        print(f"{LOG_PREFIX}: gh なし", file=sys.stderr)
        return False
    repo = (
        os.environ.get("GITHUB_NOTION_SECRET_REPO")
        or os.environ.get("GITHUB_GMAIL_SECRET_REPO")
        or "m19mhrts83-cyber/project-GE"
    ).strip()
    proc = subprocess.run(
        ["gh", "secret", "set", ENV_KEY, "--repo", repo],
        input=tok,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode == 0:
        print(f"{LOG_PREFIX}: OK gh secret {ENV_KEY} ({repo})", file=sys.stderr)
        return True
    err = (proc.stderr or proc.stdout or "").strip()[:200]
    print(f"{LOG_PREFIX}: FAIL gh secret: {err}", file=sys.stderr)
    return False


def _upsert_local_env(path: Path, tok: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []
    out: list[str] = []
    found = False
    for line in lines:
        if line.startswith(f"{ENV_KEY}="):
            out.append(f"{ENV_KEY}={tok}")
            found = True
        else:
            out.append(line)
    if not found:
        if out and out[-1].strip():
            out.append("")
        out.append(f"{ENV_KEY}={tok}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"{LOG_PREFIX}: OK local {path.relative_to(REPO)}", file=sys.stderr)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-github", action="store_true")
    ap.add_argument("--skip-vercel", action="store_true")
    ap.add_argument("--skip-local", action="store_true")
    args = ap.parse_args()

    if _truthy("NOTION_TOKEN_SYNC_DISABLE"):
        print(f"{LOG_PREFIX}: disabled", file=sys.stderr)
        return 0

    tok = _token()
    fp = _fp(tok)
    if args.dry_run:
        print(
            f"{LOG_PREFIX}: dry-run sha256_8={fp} "
            "targets=jarvis-dashboard,jarvis-trade-desk,gh:project-GE,.env.local x2",
            file=sys.stderr,
        )
        return 0

    ok = True
    if not args.skip_local:
        ok = _upsert_local_env(REPO / "apps" / "jarvis-dashboard" / ".env.local", tok) and ok
        ok = _upsert_local_env(REPO / "apps" / "trade-desk" / ".env.local", tok) and ok

    if not args.skip_vercel:
        vercel_token = (os.environ.get("VERCEL_TOKEN") or "").strip()
        if not vercel_token:
            print(f"{LOG_PREFIX}: FAIL VERCEL_TOKEN 未設定", file=sys.stderr)
            ok = False
        else:
            ok = _vercel_upsert("jarvis-dashboard", tok, vercel_token) and ok
            ok = _vercel_upsert("jarvis-trade-desk", tok, vercel_token) and ok

    if not args.skip_github:
        ok = _gh_secret_set(tok) and ok

    print(f"{LOG_PREFIX}: done sha256_8={fp} ok={ok}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
