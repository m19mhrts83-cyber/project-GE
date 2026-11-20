#!/usr/bin/env python3
"""神大家 AI ナビの東京移設: 切替前後の「数と応答」を写して比べる（2026-11-20）。

使い方（Mac の .env.jarvis_private を値を表示せず読み込んでから）:
    # 1) 旧（ムンバイ）と新（東京）をそれぞれ写す
    SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... \
        python scripts/kamiooya_cutover_check.py snapshot --out /tmp/old.json
    SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... \
        python scripts/kamiooya_cutover_check.py snapshot --out /tmp/new.json
    # 2) 比べる（違いがあれば終了コード 1）
    python scripts/kamiooya_cutover_check.py compare /tmp/old.json /tmp/new.json

写すもの: 表ごとの行数・Storage のバケット一覧・Edge Function の応答コード。
本文・会員情報・鍵は写さない。出力ファイルにも残さない。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

# 行数を照合する表（11/20 時点で行がある表と、アプリが読む空の表）
TABLES = [
    "comments", "line_openchat_logs", "knowledge_chunks", "knowledge_sources",
    "qa_roster_hashes", "qa_roster_meta", "community_attachments", "openchat_attachments",
    "qa_openchat_threads", "qa_openchat_rankings", "qa_feature_flags", "qa_answer_cache",
    "qa_answer_jobs", "qa_answer_meta", "qa_answer_feedback", "qa_answer_source_clicks",
    "qa_keyword_search_events", "app_qa_search_events", "qa_change_log", "qa_theme_rounds",
    "qa_theme_decisions", "raimo_auth_limits", "prompts", "prompt_groups",
    "prompt_usage_events", "suggested_questions", "jarvis_heartbeat",
]
# 切替の前後で増えてよい表（ログ・セッション・心拍）。行数の差は警告だけにする。
GROWING = {
    "line_openchat_logs", "comments", "app_qa_search_events", "qa_keyword_search_events",
    "qa_answer_jobs", "qa_answer_meta", "qa_answer_feedback", "qa_answer_source_clicks",
    "qa_answer_cache", "prompt_usage_events", "raimo_auth_limits", "jarvis_heartbeat",
}
FUNCTIONS = ["semantic-search", "qa-analytics", "qa-search-log", "raimo-auth",
             "community-attachments", "srt-ingest"]


def _req(method: str, url: str, key: str | None, headers: dict | None = None):
    r = urllib.request.Request(url, method=method)
    if key:
        r.add_header("apikey", key)
        r.add_header("Authorization", f"Bearer {key}")
    for k, v in (headers or {}).items():
        r.add_header(k, v)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), b""


def _count(base: str, key: str, table: str) -> int | None:
    status, headers, _ = _req("HEAD", f"{base}/rest/v1/{table}?select=*", key,
                              {"Prefer": "count=exact", "Range": "0-0"})
    rng = {k.lower(): v for k, v in headers.items()}.get("content-range", "")
    if status >= 400 or "/" not in rng:
        return None
    tail = rng.rsplit("/", 1)[1]
    return int(tail) if tail.isdigit() else None


def snapshot(base: str, key: str) -> dict:
    out: dict = {"base": base, "at": datetime.now(timezone.utc).isoformat(), "tables": {}, "buckets": [], "functions": {}}
    for t in TABLES:
        out["tables"][t] = _count(base, key, t)
    status, _, body = _req("GET", f"{base}/storage/v1/bucket", key)
    if status < 400:
        out["buckets"] = sorted((b.get("id"), bool(b.get("public"))) for b in json.loads(body or b"[]"))
    for f in FUNCTIONS:
        # 鍵なしの OPTIONS で「関数が置かれているか」だけ見る（404=未配置）。
        status, _, _ = _req("OPTIONS", f"{base}/functions/v1/{f}", None,
                            {"Origin": "https://example.invalid", "Access-Control-Request-Method": "POST"})
        out["functions"][f] = status
    return out


def compare(old: dict, new: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warns: list[str] = []
    for t in TABLES:
        a, b = old["tables"].get(t), new["tables"].get(t)
        if b is None:
            errors.append(f"表 {t}: 新側で読めない")
        elif a is None:
            warns.append(f"表 {t}: 旧側で読めない（新 {b}）")
        elif a != b:
            (warns if t in GROWING and b >= a else errors).append(f"表 {t}: 旧 {a} / 新 {b}")
    if [tuple(x) for x in old["buckets"]] != [tuple(x) for x in new["buckets"]]:
        errors.append(f"バケット: 旧 {old['buckets']} / 新 {new['buckets']}")
    for f in FUNCTIONS:
        if new["functions"].get(f) in (None, 404) or new["functions"].get(f, 0) >= 500:
            errors.append(f"関数 {f}: 新側の応答 {new['functions'].get(f)}")
    return errors, warns


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("--out", required=True)
    c = sub.add_parser("compare")
    c.add_argument("old")
    c.add_argument("new")
    a = ap.parse_args(argv)

    if a.cmd == "snapshot":
        base = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
        if not base or not key:
            print("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY が必要です", file=sys.stderr)
            return 2
        snap = snapshot(base, key)
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(snap, fh, ensure_ascii=False, indent=2)
        unread = [t for t, n in snap["tables"].items() if n is None]
        print(f"# {base}: 表 {len(TABLES) - len(unread)}/{len(TABLES)} 読めた・バケット {len(snap['buckets'])}・関数 {snap['functions']}")
        return 0

    with open(a.old, encoding="utf-8") as fh:
        old = json.load(fh)
    with open(a.new, encoding="utf-8") as fh:
        new = json.load(fh)
    errors, warns = compare(old, new)
    for w in warns:
        print(f"注意: {w}")
    for e in errors:
        print(f"違い: {e}")
    print("OK: 切替してよい状態です" if not errors else f"NG: {len(errors)} 件の違い")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
