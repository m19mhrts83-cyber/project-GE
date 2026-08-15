#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
admin Gmail トークン（token_livingsupport.json）を Vercel jarvis-dashboard の
GMAIL_ADMIN_TOKEN_B64 へ一方向投影する。

正本: Mac の token_livingsupport.json
投影: Vercel env（Production + Preview）＋ 任意で GHA Secret

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_gmail_admin_token_to_vercel.py

無効化: GMAIL_ADMIN_TOKEN_VERCEL_SYNC_DISABLE=1
値はログに出さない。指紋のみ sync_meta / ローカル state に残す。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DEFAULT_TOKEN = (
    Path.home()
    / "git-repos/215_kamiooya/C1_cursor/1b_Cursorマニュアル/token_livingsupport.json"
)
STATE_PATH = Path.home() / "git-repos/.jarvis_state/gmail_admin_token_sync.json"
LOG_PREFIX = "📎 Gmail admin token → Vercel"


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def token_sha256_8(token_path: Path) -> str:
    raw = token_path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
        material = str(data.get("refresh_token") or data.get("token") or raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        material = raw
    if isinstance(material, bytes):
        digest = hashlib.sha256(material).hexdigest()
    else:
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return digest[:8]


def _write_state(payload: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _upsert_sync_meta(fingerprint: str, vercel_ok: bool) -> None:
    url = os.environ.get("JARVIS_SUPABASE_URL") or os.environ.get(
        "NEXT_PUBLIC_SUPABASE_URL"
    )
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return
    try:
        from supabase import create_client

        sb = create_client(url, key)
        value = {
            "last_synced_at": _now(),
            "token_sha256_8": fingerprint,
            "vercel_ok": vercel_ok,
            "target": "jarvis-dashboard:GMAIL_ADMIN_TOKEN_B64",
        }
        sb.table("sync_meta").upsert(
            {
                "key": "gmail_admin_token_sync",
                "value": json.dumps(value, ensure_ascii=False),
                "updated_at": _now(),
            },
            on_conflict="key",
        ).execute()
    except Exception as e:  # noqa: BLE001
        print(f"{LOG_PREFIX}: sync_meta 更新スキップ ({type(e).__name__})", file=sys.stderr)


def _vercel_project_ids() -> tuple[str, str]:
    """(projectId, team/orgId) from env or .vercel/project.json."""
    project = (
        os.environ.get("GMAIL_ADMIN_VERCEL_PROJECT_ID")
        or os.environ.get("VERCEL_PROJECT_ID_DASHBOARD")
        or ""
    ).strip()
    team = (
        os.environ.get("GMAIL_ADMIN_VERCEL_TEAM_ID")
        or os.environ.get("VERCEL_TEAM_ID")
        or ""
    ).strip()
    if project and team:
        return project, team
    pj = REPO / "apps" / "jarvis-dashboard" / ".vercel" / "project.json"
    if pj.is_file():
        data = json.loads(pj.read_text(encoding="utf-8"))
        return str(data.get("projectId") or ""), str(data.get("orgId") or "")
    return project, team


def _vercel_env_set(b64: str, _project_dir: str, token: str) -> bool:
    """Vercel REST API で GMAIL_ADMIN_TOKEN_B64 を Production/Preview に upsert。"""
    import urllib.error
    import urllib.request

    project_id, team_id = _vercel_project_ids()
    if not project_id:
        print(f"{LOG_PREFIX}: FAIL projectId 不明（.vercel/project.json）", file=sys.stderr)
        return False

    qs = f"?teamId={team_id}" if team_id else ""
    list_url = f"https://api.vercel.com/v9/projects/{project_id}/env{qs}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # 既存 ID を取得して delete → create（型 sensitive 推奨）
    existing_ids: list[str] = []
    try:
        req = urllib.request.Request(list_url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        for env in body.get("envs") or []:
            if env.get("key") == "GMAIL_ADMIN_TOKEN_B64":
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
            "key": "GMAIL_ADMIN_TOKEN_B64",
            "value": b64,
            "type": "sensitive",
            "target": ["production", "preview"],
        }
    ).encode("utf-8")
    try:
        req = urllib.request.Request(create_url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp.read()
        print(f"{LOG_PREFIX}: OK jarvis-dashboard production+preview", file=sys.stderr)
        return True
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace")[:400]
        print(f"{LOG_PREFIX}: FAIL HTTP {e.code}: {err}", file=sys.stderr)
        return False
    except Exception as e:  # noqa: BLE001
        print(f"{LOG_PREFIX}: FAIL {type(e).__name__}: {e}", file=sys.stderr)
        return False


def _gh_secret_set(b64: str) -> None:
    if shutil_which("gh") is None:
        return
    if _truthy("GMAIL_ADMIN_TOKEN_SKIP_GITHUB_SYNC"):
        return
    repo = os.environ.get(
        "GITHUB_GMAIL_ADMIN_SECRET_REPO",
        os.environ.get("GITHUB_GMAIL_SECRET_REPO", ""),
    ).strip()
    if not repo or "/" not in repo:
        return
    # いけとも GMAIL_TOKEN_B64 と混ぜない。ADMIN 専用 Secret 名のみ
    name = os.environ.get("GITHUB_GMAIL_ADMIN_SECRET_NAME", "GMAIL_ADMIN_TOKEN_B64").strip()
    proc = subprocess.run(
        ["gh", "secret", "set", name, "--repo", repo],
        input=b64,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode == 0:
        print(f"{LOG_PREFIX}: OK gh secret {name} ({repo})", file=sys.stderr)
    else:
        err = (proc.stderr or proc.stdout or "").strip()[:200]
        print(
            f"{LOG_PREFIX}: gh secret スキップ/失敗 (exit {proc.returncode})"
            + (f": {err}" if err else ""),
            file=sys.stderr,
        )


def shutil_which(cmd: str) -> str | None:
    from shutil import which

    return which(cmd)


def sync_admin_token(
    token_path: Path | None = None,
    *,
    dry_run: bool = False,
) -> int:
    if _truthy("GMAIL_ADMIN_TOKEN_VERCEL_SYNC_DISABLE"):
        print(f"{LOG_PREFIX}: disabled", file=sys.stderr)
        return 0

    path = (token_path or Path(os.environ.get("GMAIL_ADMIN_TOKEN_PATH") or DEFAULT_TOKEN)).expanduser()
    if not path.is_file():
        print(f"{LOG_PREFIX}: token なし {path}", file=sys.stderr)
        return 1

    fp = token_sha256_8(path)
    b64 = base64.b64encode(path.read_bytes()).decode("ascii").replace("\n", "")
    vercel_token = (os.environ.get("VERCEL_TOKEN") or "").strip()
    project = (os.environ.get("GMAIL_ADMIN_VERCEL_PROJECT") or "jarvis-dashboard").strip()

    if dry_run:
        print(f"{LOG_PREFIX}: dry-run sha256_8={fp} project={project}", file=sys.stderr)
        return 0

    vercel_ok = False
    if not vercel_token:
        print(f"{LOG_PREFIX}: FAIL VERCEL_TOKEN 未設定", file=sys.stderr)
    else:
        vercel_ok = _vercel_env_set(b64, project, vercel_token)

    _gh_secret_set(b64)
    _write_state(
        {
            "last_synced_at": _now(),
            "token_sha256_8": fp,
            "vercel_ok": vercel_ok,
            "project": project,
        }
    )
    _upsert_sync_meta(fp, vercel_ok)

    if vercel_ok:
        print(
            f"{LOG_PREFIX}: 完了 sha256_8={fp}。"
            " env 反映には jarvis-dashboard の再デプロイが必要な場合があります"
            "（cd apps/jarvis-dashboard && npx vercel redeploy …）",
            file=sys.stderr,
        )
        return 0
    return 2


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--token", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    return sync_admin_token(args.token, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
