#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""loopware（判断デスク）の鍵と環境変数を .env.jarvis_private を正本にして Vercel へ送る。

  cd ~/git-repos && python3 scripts/loopware_env_setup.py            # 鍵が無ければ作り、Vercel へ登録
  python3 scripts/loopware_env_setup.py --dry-run                     # 何をするかだけ表示
  python3 scripts/loopware_env_setup.py --sql apps/jarvis-dashboard/supabase/migrations/20261108_owner_decisions_idem_key.sql
                                                                      # SQL を Supabase に流す（SUPABASE_ACCESS_TOKEN）

やること:
  1. .env.jarvis_private に LOOPWARE_ACCESS_KEY が無ければ、ランダムな値を作って追記する
  2. Vercel の jarvis-loopware に LOOPWARE_ACCESS_KEY / MAIL_ACTION_TOKEN（無ければ PROPERTY_GATE_ACTION_TOKEN） /
     JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY / JARVIS_DASHBOARD_URL を登録（sensitive）
  3. Vercel の jarvis-dashboard に LOOPWARE_ACCESS_KEY を登録（Slack リンクの署名用）
  4. --sql を付けたときだけ、その SQL を Supabase Management API で流す

値は画面にもログにも出さない（指紋 8 桁だけ）。Vercel の値は次のデプロイから効く。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ENV_FILE = REPO / ".env.jarvis_private"
SUPABASE_REF = "idkdqneutpvkhxhpjtgc"
DEFAULT_TEAM = "team_NJph8Tc5cSqw7rZSrPOQMp00"
DEFAULT_LOOPWARE_PROJECT = "prj_D6sckfsTtBzuO1kNEERuXCQ1nL8w"
DEFAULT_DASHBOARD_PROJECT = "prj_3rP2c8CCYIhRFyECBycV8Y3gFluG"  # jarvis-dashboard

LOOPWARE_KEYS = (
    "LOOPWARE_ACCESS_KEY",
    "MAIL_ACTION_TOKEN",
    "PROPERTY_GATE_ACTION_TOKEN",  # MAIL_ACTION_TOKEN が無い環境の署名鍵（dashboard と同じ値）
    "JARVIS_SUPABASE_URL",
    "JARVIS_SUPABASE_SERVICE_ROLE_KEY",
    "JARVIS_DASHBOARD_URL",
)
DASHBOARD_KEYS = ("LOOPWARE_ACCESS_KEY",)


def fp(v: str) -> str:
    return hashlib.sha256(v.encode("utf-8")).hexdigest()[:8]


def read_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip().removeprefix("export ").strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        out[k] = v
    return out


def ensure_key(path: Path, dry_run: bool) -> tuple[str, bool]:
    env = read_env(path)
    if env.get("LOOPWARE_ACCESS_KEY"):
        return env["LOOPWARE_ACCESS_KEY"], False
    val = secrets.token_urlsafe(24)
    if not dry_run:
        with path.open("a", encoding="utf-8") as f:
            f.write("\n# loopware 判断デスクの入場鍵（scripts/loopware_env_setup.py が作成）\n")
            f.write(f"LOOPWARE_ACCESS_KEY={val}\n")
        os.chmod(path, 0o600)
    return val, True


def _req(method: str, url: str, token: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode("utf-8") or "{}"
    return json.loads(raw)


def vercel_upsert(project: str, team: str, key: str, value: str, token: str) -> None:
    qs = f"?teamId={team}" if team else ""
    envs = _req("GET", f"https://api.vercel.com/v9/projects/{project}/env{qs}", token).get("envs") or []
    for e in envs:
        if e.get("key") == key and e.get("id"):
            _req("DELETE", f"https://api.vercel.com/v9/projects/{project}/env/{e['id']}{qs}", token)
    _req("POST", f"https://api.vercel.com/v10/projects/{project}/env{qs}", token, {
        "key": key, "value": value, "type": "sensitive", "target": ["production", "preview"],
    })


def dashboard_project_id(env: dict[str, str]) -> str:
    pid = env.get("VERCEL_PROJECT_ID_DASHBOARD") or os.environ.get("VERCEL_PROJECT_ID_DASHBOARD") or ""
    if pid:
        return pid
    pj = REPO / "apps/jarvis-dashboard/.vercel/project.json"
    if pj.is_file():
        pid = str(json.loads(pj.read_text(encoding="utf-8")).get("projectId") or "")
    # .vercel/project.json が無い Mac でも飛ばさない
    return pid or DEFAULT_DASHBOARD_PROJECT


def run_sql(path: Path, token: str) -> list:
    q = path.read_text(encoding="utf-8")
    return _req("POST", f"https://api.supabase.com/v1/projects/{SUPABASE_REF}/database/query", token, {"query": q})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sql", action="append", default=[], help="Supabase に流す SQL ファイル（複数可）")
    ap.add_argument("--skip-vercel", action="store_true")
    args = ap.parse_args()

    if not ENV_FILE.exists():
        print(f"✗ {ENV_FILE} がありません", file=sys.stderr)
        return 1
    key, created = ensure_key(ENV_FILE, args.dry_run)
    print(f"・LOOPWARE_ACCESS_KEY: {'作成して追記' if created else '既存'}（指紋 {fp(key)}）")
    env = read_env(ENV_FILE)
    if created:
        env["LOOPWARE_ACCESS_KEY"] = key
    env.setdefault("JARVIS_DASHBOARD_URL", "https://jarvis-dashboard-amber.vercel.app")
    rc = 0

    if not args.skip_vercel:
        token = env.get("VERCEL_TOKEN") or os.environ.get("VERCEL_TOKEN") or ""
        team = env.get("VERCEL_ORG_ID") or DEFAULT_TEAM
        targets = [
            ("jarvis-loopware", env.get("VERCEL_LOOPWARE_PROJECT_ID") or DEFAULT_LOOPWARE_PROJECT, LOOPWARE_KEYS),
            ("jarvis-dashboard", dashboard_project_id(env), DASHBOARD_KEYS),
        ]
        if not token:
            print("✗ VERCEL_TOKEN が .env.jarvis_private にありません", file=sys.stderr)
            rc = 1
        for name, pid, keys in targets if token else []:
            if not pid:
                print(f"✗ {name}: Vercel のプロジェクトIDが分かりません", file=sys.stderr)
                rc = 1
                continue
            for k in keys:
                v = env.get(k) or ""
                if not v:
                    print(f"  - {name} {k}: .env.jarvis_private に無いので飛ばします")
                    continue
                if args.dry_run:
                    print(f"  - {name} {k}: 登録予定（指紋 {fp(v)}）")
                    continue
                try:
                    vercel_upsert(pid, team, k, v, token)
                    print(f"  ✓ {name} {k}（指紋 {fp(v)}）")
                except urllib.error.HTTPError as e:
                    print(f"  ✗ {name} {k}: HTTP {e.code}", file=sys.stderr)
                    rc = 1
        if token and not args.dry_run:
            print("・Vercel の値は次のデプロイから効きます（./scripts/vercel_loopware_deploy.sh）")

    for s in args.sql:
        p = (REPO / s) if not Path(s).is_absolute() else Path(s)
        token = env.get("SUPABASE_ACCESS_TOKEN") or os.environ.get("SUPABASE_ACCESS_TOKEN") or ""
        if not token:
            print("✗ SUPABASE_ACCESS_TOKEN がありません", file=sys.stderr)
            return 1
        if args.dry_run:
            print(f"・SQL 実行予定: {p.relative_to(REPO) if p.is_relative_to(REPO) else p}")
            continue
        try:
            run_sql(p, token)
            print(f"  ✓ SQL 実行: {p.name}")
        except urllib.error.HTTPError as e:
            print(f"  ✗ SQL {p.name}: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:300]}", file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
