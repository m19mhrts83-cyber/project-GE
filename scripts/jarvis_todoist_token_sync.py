#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TODOIST_API_TOKEN（と任意で JARVIS_TASK_BACKEND）を
Vercel jarvis-dashboard と .env.local へ投影する。

正本: .env.jarvis_private
値はログに出さない。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_token_sync.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_token_sync.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LOG_PREFIX = "📎 Todoist token sync"
ENV_KEY = "TODOIST_API_TOKEN"
BACKEND_KEY = "JARVIS_TASK_BACKEND"


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


def _project_ids() -> tuple[str, str, str]:
    env_project = (os.environ.get("NOTION_VERCEL_DASHBOARD_PROJECT_ID") or "").strip()
    team = (os.environ.get("VERCEL_TEAM_ID") or "").strip()
    rel = REPO / "apps" / "jarvis-dashboard" / ".vercel" / "project.json"
    if env_project and team:
        return env_project, team, "jarvis-dashboard"
    if rel.is_file():
        data = json.loads(rel.read_text(encoding="utf-8"))
        return (
            str(data.get("projectId") or ""),
            str(data.get("orgId") or team),
            str(data.get("projectName") or "jarvis-dashboard"),
        )
    return "", team, "jarvis-dashboard"


def _vercel_upsert_key(
    key: str, value: str, vercel_token: str, *, sensitive: bool
) -> bool:
    project_id, team_id, name = _project_ids()
    if not project_id:
        print(f"{LOG_PREFIX}: FAIL projectId 不明", file=sys.stderr)
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
            if env.get("key") == key:
                eid = env.get("id")
                if eid:
                    existing_ids.append(str(eid))
    except Exception as e:  # noqa: BLE001
        print(f"{LOG_PREFIX}: env list 警告 {type(e).__name__}", file=sys.stderr)

    for eid in existing_ids:
        del_url = f"https://api.vercel.com/v9/projects/{project_id}/env/{eid}{qs}"
        try:
            req = urllib.request.Request(del_url, headers=headers, method="DELETE")
            with urllib.request.urlopen(req, timeout=60) as resp:
                resp.read()
        except Exception as e:  # noqa: BLE001
            print(f"{LOG_PREFIX}: env delete 警告 {type(e).__name__}", file=sys.stderr)

    create_url = f"https://api.vercel.com/v10/projects/{project_id}/env{qs}"
    payload = json.dumps(
        {
            "key": key,
            "value": value,
            "type": "sensitive" if sensitive else "plain",
            "target": ["production", "preview"],
        }
    ).encode("utf-8")
    try:
        req = urllib.request.Request(
            create_url, data=payload, headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp.read()
        print(f"{LOG_PREFIX}: OK Vercel {name} {key}", file=sys.stderr)
        return True
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace")[:300]
        print(f"{LOG_PREFIX}: FAIL Vercel {key} HTTP {e.code}: {err}", file=sys.stderr)
        return False


def _upsert_local_env(path: Path, pairs: dict[str, str]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    keys = set(pairs)
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        hit = False
        for k, v in pairs.items():
            if line.startswith(f"{k}="):
                out.append(f"{k}={v}")
                seen.add(k)
                hit = True
                break
        if not hit:
            out.append(line)
    for k, v in pairs.items():
        if k not in seen:
            if out and out[-1].strip():
                out.append("")
            out.append(f"{k}={v}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(
        f"{LOG_PREFIX}: OK local {path.relative_to(REPO)} keys={','.join(sorted(keys))}",
        file=sys.stderr,
    )
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-vercel", action="store_true")
    ap.add_argument("--skip-local", action="store_true")
    ap.add_argument(
        "--backend",
        default="",
        help="JARVIS_TASK_BACKEND 値（空なら env または todoist）",
    )
    args = ap.parse_args()

    if _truthy("TODOIST_TOKEN_SYNC_DISABLE"):
        print(f"{LOG_PREFIX}: disabled", file=sys.stderr)
        return 0

    tok = _token()
    backend = (
        (args.backend or os.environ.get(BACKEND_KEY) or "todoist").strip()
        or "todoist"
    )
    fp = _fp(tok)
    if args.dry_run:
        print(
            f"{LOG_PREFIX}: dry-run sha256_8={fp} backend={backend} "
            "targets=jarvis-dashboard .env.local",
            file=sys.stderr,
        )
        return 0

    pairs = {ENV_KEY: tok, BACKEND_KEY: backend}
    ok = True
    if not args.skip_local:
        ok = (
            _upsert_local_env(REPO / "apps" / "jarvis-dashboard" / ".env.local", pairs)
            and ok
        )

    if not args.skip_vercel:
        vercel_token = (os.environ.get("VERCEL_TOKEN") or "").strip()
        if not vercel_token:
            print(f"{LOG_PREFIX}: FAIL VERCEL_TOKEN 未設定", file=sys.stderr)
            ok = False
        else:
            ok = _vercel_upsert_key(ENV_KEY, tok, vercel_token, sensitive=True) and ok
            ok = (
                _vercel_upsert_key(BACKEND_KEY, backend, vercel_token, sensitive=False)
                and ok
            )

    print(f"{LOG_PREFIX}: done sha256_8={fp} backend={backend} ok={ok}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
