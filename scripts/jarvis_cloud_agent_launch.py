#!/usr/bin/env python3
"""
Cursor Cloud Agents API の薄いラッパ（起動のみ・完了待ちしない）。

  python scripts/jarvis_cloud_agent_launch.py --prompt "…" --name jarvis-ops-fix

環境: CURSOR_API_KEY
任意: CURSOR_CLOUD_REPO_URL（未設定なら project-GE）
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

API_BASE = "https://api.cursor.com/v1"
DEFAULT_REPO = "https://github.com/m19mhrts83-cyber/project-GE"


def auth_header(api_key: str) -> str:
    return "Basic " + base64.b64encode(f"{api_key}:".encode()).decode()


def is_limit_error(status: int, body: str) -> bool:
    b = (body or "").lower()
    if status in (402, 429):
        return True
    keys = (
        "rate limit",
        "rate_limit",
        "quota",
        "usage limit",
        "usage_limit",
        "too many",
        "concurrent",
        "on-demand",
        "spending",
        "budget",
        "capacity",
        "limit exceeded",
        "max agents",
    )
    return any(k in b for k in keys)


def launch_cloud_agent(
    *,
    prompt: str,
    name: str = "jarvis-ops-fix",
    repo_url: str | None = None,
    starting_ref: str = "main",
    auto_create_pr: bool = True,
    mode: str = "agent",
    timeout_sec: int = 90,
) -> dict[str, Any]:
    """
    Cloud Agent を起動する（完了は待たない）。

    戻り値:
      ok=True → agent_id / run_id / url
      ok=False → error / limit (bool)
    """
    api_key = (os.environ.get("CURSOR_API_KEY") or "").strip()
    if not api_key:
        return {
            "ok": False,
            "limit": False,
            "error": "CURSOR_API_KEY 未設定",
        }

    prompt = (prompt or "").strip()
    if not prompt:
        return {"ok": False, "limit": False, "error": "プロンプトが空"}

    repo = (repo_url or os.environ.get("CURSOR_CLOUD_REPO_URL") or DEFAULT_REPO).strip()
    body: dict[str, Any] = {
        "prompt": {"text": prompt},
        "name": name[:80] or "jarvis-ops-fix",
        "mode": mode or "agent",
        "repos": [{"url": repo, "startingRef": starting_ref or "main"}],
        "autoCreatePR": bool(auto_create_pr),
        "skipReviewerRequest": True,
        "workOnCurrentBranch": False,
    }

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}/agents",
        data=data,
        method="POST",
        headers={
            "Authorization": auth_header(api_key),
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as res:
            raw = res.read().decode("utf-8", errors="replace")
            status = res.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        status = e.code
        limit = is_limit_error(status, raw)
        return {
            "ok": False,
            "limit": limit,
            "error": f"Cloud Agent 起動 {status}: {raw[:240]}",
            "http_status": status,
        }
    except Exception as e:
        msg = str(e)
        limit = is_limit_error(0, msg)
        return {
            "ok": False,
            "limit": limit,
            "error": f"Cloud Agent 起動失敗: {msg[:240]}",
        }

    if status >= 400:
        return {
            "ok": False,
            "limit": is_limit_error(status, raw),
            "error": f"Cloud Agent 起動 {status}: {raw[:240]}",
            "http_status": status,
        }

    try:
        created = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "limit": False, "error": f"JSONでない応答: {raw[:200]}"}

    agent_id = (created.get("agent") or {}).get("id") or created.get("id")
    run = created.get("run") or {}
    run_id = run.get("id")
    if not agent_id:
        return {
            "ok": False,
            "limit": False,
            "error": f"agent id 不足: {raw[:200]}",
        }

    url = f"https://cursor.com/agents/{agent_id}"
    return {
        "ok": True,
        "agent_id": agent_id,
        "run_id": run_id,
        "url": url,
        "repo": repo,
        "raw_status": run.get("status"),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--name", default="jarvis-ops-fix")
    ap.add_argument("--repo", default="")
    ap.add_argument("--ref", default="main")
    ap.add_argument("--no-pr", action="store_true")
    args = ap.parse_args(argv)
    r = launch_cloud_agent(
        prompt=args.prompt,
        name=args.name,
        repo_url=args.repo or None,
        starting_ref=args.ref,
        auto_create_pr=not args.no_pr,
    )
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
