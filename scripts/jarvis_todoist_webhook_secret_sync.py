#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TODOIST_APP_CLIENT_SECRET / CLIENT_ID を Vercel（jarvis-dashboard）へ投影する。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_webhook_secret_sync.py

値は標準出力に出さない。App Console の client_id / client_secret を
.env.jarvis_private に保存したあと実行。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LOG = "📎 Todoist Webhook secret → Vercel"
KEYS = ("TODOIST_APP_CLIENT_SECRET", "TODOIST_APP_CLIENT_ID")


def _project_ids() -> tuple[str, str]:
    project = (
        os.environ.get("VERCEL_PROJECT_ID_DASHBOARD")
        or os.environ.get("GMAIL_ADMIN_VERCEL_PROJECT_ID")
        or ""
    ).strip()
    team = (
        os.environ.get("VERCEL_TEAM_ID")
        or os.environ.get("GMAIL_ADMIN_VERCEL_TEAM_ID")
        or ""
    ).strip()
    pj = REPO / "apps" / "jarvis-dashboard" / ".vercel" / "project.json"
    if pj.is_file():
        data = json.loads(pj.read_text(encoding="utf-8"))
        project = project or str(data.get("projectId") or "")
        team = team or str(data.get("orgId") or "")
    return project, team


def _upsert_env(
    *,
    project_id: str,
    team_id: str,
    token: str,
    key: str,
    value: str,
) -> None:
    qs = f"?teamId={team_id}" if team_id else ""
    headers = {
        "Authorization": f"Bearer {token}",
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
        print(f"{LOG}: env list 警告 {key} {type(e).__name__}", file=sys.stderr)

    for eid in existing_ids:
        del_url = f"https://api.vercel.com/v9/projects/{project_id}/env/{eid}{qs}"
        try:
            req = urllib.request.Request(del_url, headers=headers, method="DELETE")
            with urllib.request.urlopen(req, timeout=60) as resp:
                resp.read()
        except Exception as e:  # noqa: BLE001
            print(f"{LOG}: env delete 警告 {key} {type(e).__name__}", file=sys.stderr)

    create_url = f"https://api.vercel.com/v10/projects/{project_id}/env{qs}"
    payload = json.dumps(
        {
            "key": key,
            "value": value,
            "type": "sensitive",
            "target": ["production", "preview"],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        create_url, data=payload, headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        resp.read()


def main() -> int:
    token = (os.environ.get("VERCEL_TOKEN") or "").strip()
    if not token:
        print(f"{LOG}: FAIL VERCEL_TOKEN 未設定", file=sys.stderr)
        return 2

    values: dict[str, str] = {}
    for key in KEYS:
        v = (os.environ.get(key) or "").strip()
        if not v:
            print(
                f"{LOG}: FAIL {key} が空です（.env.jarvis_private に追記してから再実行）",
                file=sys.stderr,
            )
            return 2
        values[key] = v

    project_id, team_id = _project_ids()
    if not project_id:
        print(f"{LOG}: FAIL projectId 不明", file=sys.stderr)
        return 2

    for key, value in values.items():
        try:
            _upsert_env(
                project_id=project_id,
                team_id=team_id,
                token=token,
                key=key,
                value=value,
            )
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", "replace")[:300]
            print(f"{LOG}: FAIL {key} HTTP {e.code}: {err}", file=sys.stderr)
            return 1
        except Exception as e:  # noqa: BLE001
            print(f"{LOG}: FAIL {key} {type(e).__name__}", file=sys.stderr)
            return 1

    print(f"{LOG}: OK jarvis-dashboard production+preview（CLIENT_ID+SECRET・値は非表示）")
    print("次: デプロイ反映 → OAuth 再承認（トークン交換で Webhook 有効化）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
