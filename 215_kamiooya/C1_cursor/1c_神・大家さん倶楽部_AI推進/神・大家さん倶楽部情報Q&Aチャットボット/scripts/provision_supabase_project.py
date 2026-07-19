#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Supabase 新規プロジェクトを Management API で作成し、schema.sql を適用して
scripts/.env / .env.jarvis_private に URL・キーを書き込む。

前提:
  ~/.env.jarvis_private または scripts/.env に SUPABASE_ACCESS_TOKEN=sbp_...
  （Dashboard → Account → Access Tokens で発行。チャットに貼らない）

例:
  python3 provision_supabase_project.py
  python3 provision_supabase_project.py --name kamiooya-qa --region ap-northeast-1
  python3 provision_supabase_project.py --reuse-if-exists
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import string
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[4]  # …/git-repos
SCHEMA_PATH = REPO_ROOT / "apps" / "kamiooya-qa-web" / "supabase" / "schema.sql"
JARVIS_PRIVATE = Path.home() / "git-repos" / ".env.jarvis_private"
OD_ENV = Path(
    "/Users/matsunomasaharu2/Library/CloudStorage/OneDrive-個人用/"
    "215_神・大家さん倶楽部/C1_cursor/1c_神・大家さん倶楽部_AI推進/"
    "神・大家さん倶楽部情報Q&Aチャットボット/scripts/.env"
)
GIT_ENV = SCRIPT_DIR / ".env"
API = "https://api.supabase.com/v1"


def load_dotenv_files() -> None:
    for p in (JARVIS_PRIVATE, OD_ENV, GIT_ENV):
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def api(method: str, path: str, token: str, body: dict | None = None, timeout: int = 120):
    data = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} {method} {path}: {err}") from e


def gen_db_password(n: int = 28) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


def upsert_env_file(path: Path, updates: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()
    keys_done: set[str] = set()
    out: list[str] = []
    for line in lines:
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=", line)
        if m and m.group(1) in updates:
            k = m.group(1)
            out.append(f"{k}={updates[k]}")
            keys_done.add(k)
        else:
            out.append(line)
    for k, v in updates.items():
        if k not in keys_done:
            out.append(f"{k}={v}")
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    print(f"updated env: {path}")


def wait_active(token: str, ref: str, timeout_sec: int = 600) -> dict:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        _st, proj = api("GET", f"/projects/{ref}", token)
        status = (proj or {}).get("status") or (proj or {}).get("status")
        # API may return status under different keys
        st = str((proj or {}).get("status") or "")
        print(f"  project status={st or '?'}")
        if st.upper() in {"ACTIVE_HEALTHY", "ACTIVE", "ACTIVE_HEALTHY".lower()} or st == "ACTIVE_HEALTHY":
            return proj or {}
        if st.upper() in {"ACTIVE_HEALTHY", "ACTIVE"}:
            return proj or {}
        # common: COMING_UP / UNKNOWN / INACTIVE
        if st in ("ACTIVE_HEALTHY", "ACTIVE"):
            return proj or {}
        time.sleep(10)
    raise TimeoutError(f"project {ref} not active within {timeout_sec}s")


def apply_schema(token: str, ref: str, schema_sql: str) -> None:
    # Management API executes SQL; split on semicolons carefully is hard — send whole file
    # Some statements may need sequential execution; try whole then fallback to chunks.
    try:
        api("POST", f"/projects/{ref}/database/query", token, {"query": schema_sql})
        print("schema applied (single query)")
        return
    except RuntimeError as e:
        print(f"single-query apply failed, trying statements: {e}")
    # naive split (schema is controlled)
    parts = [p.strip() for p in schema_sql.split(";") if p.strip() and not p.strip().startswith("--")]
    for i, part in enumerate(parts, 1):
        # keep comments-only out
        sql = part + ";"
        if not re.search(r"\b(create|alter|grant|drop|comment)\b", sql, re.I):
            continue
        api("POST", f"/projects/{ref}/database/query", token, {"query": sql})
        print(f"  statement {i}/{len(parts)} ok")


def pick_api_keys(token: str, ref: str) -> tuple[str, str]:
    _st, keys = api("GET", f"/projects/{ref}/api-keys", token)
    anon = ""
    service = ""
    for item in keys or []:
        name = str(item.get("name") or item.get("type") or "").lower()
        api_key = item.get("api_key") or item.get("key") or ""
        if name in ("anon", "anonymous") or "anon" in name:
            anon = api_key
        if name in ("service_role", "service") or "service" in name:
            service = api_key
    if not anon or not service:
        # legacy endpoint
        try:
            _st2, legacy = api("GET", f"/projects/{ref}/api-keys/legacy", token)
            if isinstance(legacy, dict):
                anon = anon or legacy.get("anon") or legacy.get("anon_key") or ""
                service = service or legacy.get("service_role") or legacy.get("service_role_key") or ""
            elif isinstance(legacy, list):
                for item in legacy:
                    name = str(item.get("name") or "").lower()
                    api_key = item.get("api_key") or ""
                    if "anon" in name:
                        anon = anon or api_key
                    if "service" in name:
                        service = service or api_key
        except RuntimeError:
            pass
    if not service:
        raise RuntimeError(f"service_role key not found for {ref}. keys={keys!r}")
    return anon, service


def main() -> int:
    load_dotenv_files()
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="kamiooya-qa")
    ap.add_argument("--region", default="ap-northeast-1")
    ap.add_argument("--org-id", default="", help="organization id (省略時は先頭 org)")
    ap.add_argument("--reuse-if-exists", action="store_true")
    ap.add_argument("--skip-schema", action="store_true")
    ap.add_argument("--skip-env-write", action="store_true")
    args = ap.parse_args()

    token = (os.environ.get("SUPABASE_ACCESS_TOKEN") or "").strip()
    if not token:
        print(
            "SUPABASE_ACCESS_TOKEN がありません。\n"
            "1) https://supabase.com/dashboard/account/tokens で Access Token を発行\n"
            "2) ~/git-repos/.env.jarvis_private に SUPABASE_ACCESS_TOKEN=sbp_... を追記\n"
            "3) 『保存した』と一声ください（値はチャットに貼らない）",
            file=sys.stderr,
        )
        return 2

    _st, orgs = api("GET", "/organizations", token)
    if not orgs:
        print("organizations が空です", file=sys.stderr)
        return 2
    org = None
    if args.org_id:
        org = next((o for o in orgs if o.get("id") == args.org_id), None)
        if not org:
            print(f"org-id not found: {args.org_id}", file=sys.stderr)
            return 2
    else:
        org = orgs[0]
    org_id = org.get("id")
    org_slug = org.get("slug") or org.get("id")
    print(f"org id={org_id} slug={org_slug} name={org.get('name')}")

    _st, projects = api("GET", "/projects", token)
    existing = next((p for p in (projects or []) if p.get("name") == args.name), None)
    if existing and args.reuse_if_exists:
        ref = existing["id"]
        print(f"reuse existing project ref={ref}")
        proj = existing
    elif existing and not args.reuse_if_exists:
        print(
            f"同名プロジェクトが既にあります ref={existing.get('id')}。"
            " --reuse-if-exists を付けるか別名にしてください。",
            file=sys.stderr,
        )
        return 3
    else:
        db_pass = gen_db_password()
        body = {
            "name": args.name,
            "organization_id": org_id,
            "organization_slug": org_slug,
            "region": args.region,
            "db_pass": db_pass,
            "plan": "free",
        }
        # Some API versions use password instead of db_pass
        print(f"creating project name={args.name} region={args.region} …")
        try:
            _st, proj = api("POST", "/projects", token, body)
        except RuntimeError as e:
            # retry with alternate field names
            body2 = {
                "name": args.name,
                "organization_id": org_id,
                "region": args.region,
                "password": db_pass,
            }
            print(f"retry create with password field: {e}")
            _st, proj = api("POST", "/projects", token, body2)
        ref = proj["id"]
        print(f"created ref={ref}")
        # store db pass privately
        upsert_env_file(JARVIS_PRIVATE, {"SUPABASE_DB_PASSWORD": db_pass, "SUPABASE_PROJECT_REF": ref})

    print("waiting until ACTIVE…")
    # poll projects list / get
    deadline = time.time() + 600
    while time.time() < deadline:
        _st, p = api("GET", f"/projects/{ref}", token)
        st = str((p or {}).get("status") or "")
        print(f"  status={st}")
        if st in ("ACTIVE_HEALTHY", "ACTIVE"):
            proj = p
            break
        time.sleep(12)
    else:
        print("timeout waiting for ACTIVE", file=sys.stderr)
        return 4

    url = f"https://{ref}.supabase.co"
    anon, service = pick_api_keys(token, ref)
    print(f"url={url}")
    print(f"anon_key len={len(anon)} service_role len={len(service)}")

    if not args.skip_schema:
        if not SCHEMA_PATH.is_file():
            print(f"schema missing: {SCHEMA_PATH}", file=sys.stderr)
            return 5
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        print(f"applying schema {SCHEMA_PATH} …")
        apply_schema(token, ref, schema)

    updates = {
        "SUPABASE_URL": url,
        "SUPABASE_ANON_KEY": anon,
        "SUPABASE_SERVICE_ROLE_KEY": service,
        "SUPABASE_PROJECT_REF": ref,
        "SUPABASE_ACCESS_TOKEN": token,
    }
    if not args.skip_env_write:
        upsert_env_file(JARVIS_PRIVATE, updates)
        upsert_env_file(OD_ENV, updates)
        # git-repos side copy (gitignore expected for .env)
        upsert_env_file(GIT_ENV, {k: updates[k] for k in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_PROJECT_REF")})

    # verify
    try:
        api("POST", f"/projects/{ref}/database/query", token, {"query": "select count(*)::int as c from public.comments;"})
        print("verify: comments table reachable")
    except RuntimeError as e:
        print(f"verify warning: {e}")

    print("DONE. Next: bootstrap comments + sample Notta ingest.")
    print(f"  SUPABASE_URL={url}")
    print(f"  SUPABASE_PROJECT_REF={ref}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
