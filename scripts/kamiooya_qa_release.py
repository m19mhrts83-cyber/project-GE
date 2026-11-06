#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""神大家Q&Aチャットボットの本番反映（固定手順）。

マージ済み PR を本番へ出すときに Miss Lemon（Claude）が使う 1 本の入口。
Claude Code の許可リストにはこのスクリプトだけを足す（他の本番コマンドは足さない）。

順番は固定（migration → Edge Function → 動作確認 → Raimo フロント）。
どこかで失敗したらそこで止まり、以降は実行しない。秘密値は表示しない。

例:
  python3 scripts/kamiooya_qa_release.py \
      --migration 20261105_qa_usage_metering.sql \
      --functions semantic-search,qa-analytics \
      --check-analytics --raimo-front

  --dry-run を付けると実行内容だけ表示する。
  Raimo の API YAML（miniAppBackend 1046）は、このスクリプトでは更新しない。
  （添付閲覧の緊急停止などバックエンド設定を巻き戻さないため。必要なら publish_raimo_1346.py を人の了承付きで使う）
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
QA_WEB = REPO / "apps" / "kamiooya-qa-web"
MIGRATIONS = QA_WEB / "supabase" / "migrations"
PROJECT_REF = "mwubzgefkkjjbingrmqu"
ALLOWED_FUNCTIONS = {
    "semantic-search", "qa-analytics", "qa-search-log",
    "raimo-auth", "community-attachments", "srt-ingest",
}
CHATBOT = REPO / "215_kamiooya" / "C1_cursor" / "1c_神・大家さん倶楽部_AI推進" / "神・大家さん倶楽部情報Q&Aチャットボット"
ENV_FILE = Path.home() / "git-repos" / ".env.jarvis_private"
UA = "kamiooya-qa-release/1"
# Q&A プロジェクトは jarvis-dashboard と別アカウント。専用トークンを使う
TOKEN_KEY = "SUPABASE_ACCESS_TOKEN_KAMIOOYA"


def load_env() -> None:
    if not ENV_FILE.exists():
        raise SystemExit(f"env file not found: {ENV_FILE}")
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def need(name: str) -> str:
    v = (os.environ.get(name) or "").strip()
    if not v:
        raise SystemExit(f"{name} が未設定です（値は表示しません）")
    return v


def mgmt_query(sql: str):
    req = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query",
        data=json.dumps({"query": sql}).encode(),
        headers={
            "Authorization": "Bearer " + need(TOKEN_KEY),
            "Content-Type": "application/json",
            "User-Agent": UA,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Management API {e.code}: {e.read().decode()[:400]}")


def step_migration(names: list[str], dry: bool) -> None:
    for name in names:
        path = (MIGRATIONS / name).resolve()
        if path.parent != MIGRATIONS.resolve() or not path.is_file():
            raise SystemExit(f"migration が見つかりません（migrations 直下のみ可）: {name}")
        print(f"[1] migration: {name}")
        if dry:
            continue
        mgmt_query(path.read_text(encoding="utf-8"))
        print("    applied")


def step_functions(names: list[str], dry: bool) -> None:
    for fn in names:
        if fn not in ALLOWED_FUNCTIONS:
            raise SystemExit(f"未登録の Edge Function: {fn}")
        cmd = ["npx", "--yes", "supabase@latest", "functions", "deploy", fn,
               "--project-ref", PROJECT_REF, "--no-verify-jwt"]
        print(f"[2] deploy: {fn}")
        if dry:
            continue
        env = dict(os.environ, SUPABASE_ACCESS_TOKEN=need(TOKEN_KEY))
        r = subprocess.run(cmd, cwd=QA_WEB, env=env, capture_output=True, text=True)
        tail = (r.stdout + r.stderr).strip().splitlines()[-5:]
        for line in tail:
            print("    " + line)
        if r.returncode != 0:
            raise SystemExit(f"deploy 失敗: {fn}")


def step_check_analytics(dry: bool) -> None:
    print("[3] check: qa-analytics metering")
    if dry:
        return
    url = f"https://{PROJECT_REF}.supabase.co/functions/v1/qa-analytics"
    req = urllib.request.Request(
        url, data=json.dumps({"days": 30}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": UA,
                 "X-Semantic-Shared-Secret": need("SEMANTIC_SEARCH_SHARED_SECRET")},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"qa-analytics {e.code}: {e.read().decode()[:300]}")
    m = body.get("metering") or {}
    weekly = m.get("weekly") if isinstance(m, dict) else None
    print(f"    metering.weekly={'list(%d)' % len(weekly) if isinstance(weekly, list) else weekly!r}"
          f" metering_error={body.get('metering_error')!r}")
    if not isinstance(weekly, list) or body.get("metering_error") is not None:
        raise SystemExit("metering の確認に失敗")


def _load_publish_module():
    path = CHATBOT / "scripts" / "publish_raimo_1346.py"
    spec = importlib.util.spec_from_file_location("publish_raimo_1346", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def step_raimo_front(expect: list[str], dry: bool) -> None:
    """index.html / style.css / app.js を miniApp 1346 に save → deploy（API YAML は触らない）。"""
    print("[4] raimo front: miniApp 1346 save+deploy（API YAML は更新しない）")
    if dry:
        return
    pub = _load_publish_module()
    pub.load_env()
    html = (CHATBOT / "index.html").read_text(encoding="utf-8")
    css = (CHATBOT / "style.css").read_text(encoding="utf-8")
    js = (CHATBOT / "app.js").read_text(encoding="utf-8")
    lookup = CHATBOT / "forum_category_lookup.js"
    if lookup.exists():
        js = lookup.read_text(encoding="utf-8") + "\n" + js
    js = pub.inject_js_placeholders(js)
    catalog = CHATBOT / "course_catalog.js"
    if catalog.exists():
        js = catalog.read_text(encoding="utf-8") + "\n" + js
    html = pub.prepare_html_for_raimo(html)
    marker = "<!-- RAIMO_KNOWLEDGE_UI_20260720 -->"
    if marker not in html:
        html = html.replace("<!DOCTYPE html>", "<!DOCTYPE html>\n" + marker, 1)

    from playwright.sync_api import sync_playwright

    base = "https://raimo.buzz"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{base}/login", wait_until="networkidle", timeout=120000)
        page.fill('input[type="email"], input[placeholder*="company"]', need("RAIMO_PORTAL_EMAIL"))
        page.fill('input[type="password"]', need("RAIMO_PORTAL_PASSWORD"))
        page.click('button:has-text("ログイン")')
        page.wait_for_timeout(5000)
        page.goto(f"{base}/miniApp/{pub.APP_ID}/edit", wait_until="domcontentloaded", timeout=180000)
        page.wait_for_timeout(5000)
        if "権限がありません" in page.inner_text("body"):
            raise SystemExit("Raimo 編集権限がありません")
        save = page.request.post(
            f"{base}/gpt/api/miniApp/{pub.APP_ID}/save",
            data={"title": "神・大家さん倶楽部Q&Aチャットボット",
                  "htmlContent": html, "cssContent": css, "jsContent": js},
            timeout=120000,
        )
        print("    save", save.status)
        if save.status != 200:
            raise SystemExit("Raimo save 失敗")
        deploy = page.request.post(f"{base}/gpt/api/miniApp/{pub.APP_ID}/deploy", data={}, timeout=120000)
        print("    deploy", deploy.status)
        browser.close()
        if deploy.status != 200:
            raise SystemExit("Raimo deploy 失敗")

    app_url = need("RAIMO_APP_URL").rstrip("/")
    time.sleep(3)
    live_js = urllib.request.urlopen(f"{app_url}/app.js?t={int(time.time())}", timeout=30).read().decode("utf-8", "replace")
    result = {k: (k in live_js) for k in expect}
    print("    live app.js contains", result)
    if not all(result.values()):
        raise SystemExit("反映後の app.js に期待する文字列がありません")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--migration", action="append", default=[], help="migrations 直下のファイル名（複数可）")
    ap.add_argument("--functions", default="", help="カンマ区切りの Edge Function 名")
    ap.add_argument("--check-analytics", action="store_true", help="qa-analytics の metering を確認")
    ap.add_argument("--raimo-front", action="store_true", help="Raimo 1346 のフロントのみ反映")
    ap.add_argument("--expect", default="", help="反映後 app.js に含まれるべき文字列（カンマ区切り）")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if not re.fullmatch(r"[a-z0-9,\-]*", a.functions):
        raise SystemExit("--functions の形式が不正です")
    load_env()
    step_migration(a.migration, a.dry_run)
    step_functions([f for f in a.functions.split(",") if f], a.dry_run)
    if a.check_analytics:
        step_check_analytics(a.dry_run)
    if a.raimo_front:
        step_raimo_front([s for s in a.expect.split(",") if s], a.dry_run)
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
