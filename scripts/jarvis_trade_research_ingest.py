#!/usr/bin/env python3
"""分野別ニュースを trade_research に取り込む。

オンライン: Tavily API → ローカルキャッシュ → Supabase
オフライン: キャッシュ／既存 DB を読む（API 不要）

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_trade_research_ingest.py \\
    --from-file path/to/weekly.md --source chatgpt_weekly --topic ai,space
  ~/selenium_env/venv/bin/python scripts/jarvis_trade_research_ingest.py --tavily
  ~/selenium_env/venv/bin/python scripts/jarvis_trade_research_ingest.py --tavily --cache-only
  ~/selenium_env/venv/bin/python scripts/jarvis_trade_research_ingest.py --from-inbox
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from jarvis_trade_common import JST, REPO, sb_client

THEMES = REPO / "config" / "trade_research_themes.yaml"
INBOX = REPO / ".jarvis_state" / "trade_research_inbox"
CACHE_DIR = REPO / ".jarvis_state" / "tavily_cache"


def load_themes() -> dict:
    return yaml.safe_load(THEMES.read_text(encoding="utf-8")) or {}


def query_key(query: str) -> str:
    return hashlib.sha1(query.strip().encode("utf-8")).hexdigest()[:16]


def cache_path(query: str) -> Path:
    return CACHE_DIR / f"{query_key(query)}.json"


def save_cache(query: str, theme: str, data: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "query": query,
        "theme": theme,
        "fetched_at": datetime.now(JST).isoformat(),
        "data": data,
    }
    cache_path(query).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_cache(query: str) -> dict[str, Any] | None:
    p = cache_path(query)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def insert_research(
    sb,
    *,
    source: str,
    topic: str,
    summary: str,
    url: str | None,
    payload: dict,
    fetched_at: str | None = None,
) -> None:
    sb.table("trade_research").insert(
        {
            "source": source,
            "topic": topic,
            "summary": summary[:8000],
            "url": url,
            "payload": payload,
            "fetched_at": fetched_at or datetime.now(JST).isoformat(),
        }
    ).execute()


def ingest_file(sb, path: Path, source: str, topic: str) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    insert_research(
        sb,
        source=source,
        topic=topic,
        summary=text[:8000],
        url=None,
        payload={"filename": path.name, "chars": len(text)},
    )
    print(f"# ingested file {path.name} topic={topic} chars={len(text)}")


def tavily_search_live(query: str) -> dict:
    import urllib.request

    key = (os.environ.get("TAVILY_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("TAVILY_API_KEY 未設定")
    body = json.dumps(
        {
            "api_key": key,
            "query": query,
            "search_depth": "basic",
            "max_results": 5,
            "include_answer": True,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def summarize_results(query: str, data: dict) -> tuple[str, list[str]]:
    results = data.get("results") or []
    lines = []
    urls: list[str] = []
    for r in results[:5]:
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        snippet = (r.get("content") or "").strip()[:280]
        lines.append(f"- {title}: {snippet}")
        if url:
            urls.append(url)
    summary = f"query={query}\n" + "\n".join(lines)
    return summary, urls


def recent_db_has(sb, topic: str, query: str, days: int = 7) -> bool:
    since = (datetime.now(JST) - timedelta(days=days)).isoformat()
    res = (
        sb.table("trade_research")
        .select("id,payload,fetched_at")
        .eq("topic", topic)
        .gte("fetched_at", since)
        .order("fetched_at", desc=True)
        .limit(20)
        .execute()
    )
    for row in res.data or []:
        payload = row.get("payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        if (payload.get("query") or "") == query:
            return True
    return False


def ingest_tavily(sb, cfg: dict, *, cache_only: bool) -> tuple[int, int]:
    """returns (inserted, cache_hits)"""
    inserted = 0
    cache_hits = 0
    for th in cfg.get("themes") or []:
        for q in th.get("queries") or []:
            data: dict | None = None
            fetched_at: str | None = None
            from_cache = False
            if not cache_only:
                try:
                    data = tavily_search_live(q)
                    save_cache(q, th["id"], data)
                except Exception as e:
                    print(f"# tavily live fail {th['id']} {q!r}: {e}", flush=True)
            if data is None:
                cached = load_cache(q)
                if not cached:
                    print(f"# tavily no-cache skip {th['id']} {q!r}", flush=True)
                    continue
                data = cached.get("data") or {}
                fetched_at = cached.get("fetched_at")
                from_cache = True
                cache_hits += 1
            summary, urls = summarize_results(q, data)
            if from_cache and recent_db_has(sb, th["id"], q, days=7):
                print(f"# tavily cache reuse(db) {th['id']} q={q!r}")
                continue
            insert_research(
                sb,
                source="tavily_cache" if from_cache else "tavily",
                topic=th["id"],
                summary=summary,
                url=urls[0] if urls else None,
                payload={
                    "query": q,
                    "urls": urls,
                    "answer": data.get("answer"),
                    "from_cache": from_cache,
                },
                fetched_at=fetched_at,
            )
            print(
                f"# tavily {'cache' if from_cache else 'live'} {th['id']} "
                f"q={q!r} hits={len(data.get('results') or [])}"
            )
            inserted += 1
    return inserted, cache_hits


def research_bonus_for_symbol(sb, symbol: str, lookback_days: int = 14) -> tuple[float, str]:
    """ニュース加点。API は呼ばない（DB／キャッシュ済みのみ）。"""
    cfg = load_themes()
    topics: list[str] = []
    for th in cfg.get("themes") or []:
        watches = th.get("watch_symbols") or []
        if symbol in watches:
            topics.append(th["id"])
    if not topics:
        return 0.0, ""
    since = (datetime.now(JST) - timedelta(days=lookback_days)).isoformat()
    res = (
        sb.table("trade_research")
        .select("topic,fetched_at,source")
        .in_("topic", topics)
        .gte("fetched_at", since)
        .limit(5)
        .execute()
    )
    rows = res.data or []
    if not rows:
        return 0.0, ""
    return 5.0, f"ニュース加点({rows[0].get('source')}/{rows[0].get('topic')})"


def main() -> int:
    ap = argparse.ArgumentParser(description="Trade Desk リサーチ取込")
    ap.add_argument("--from-file", default="")
    ap.add_argument("--from-inbox", action="store_true")
    ap.add_argument("--tavily", action="store_true")
    ap.add_argument(
        "--cache-only",
        action="store_true",
        help="Tavily API を呼ばずローカルキャッシュだけ使う",
    )
    ap.add_argument("--source", default="chatgpt_weekly")
    ap.add_argument("--topic", default="ai")
    args = ap.parse_args()

    sb = sb_client()
    cfg = load_themes()
    INBOX.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if args.from_file:
        ingest_file(sb, Path(args.from_file), args.source, args.topic)
        return 0
    if args.from_inbox:
        files = sorted(
            p
            for p in INBOX.iterdir()
            if p.is_file() and p.suffix.lower() in {".md", ".txt"}
        )
        if not files:
            print("# inbox empty")
            return 0
        for p in files:
            ingest_file(sb, p, args.source, args.topic)
            dest = INBOX / "processed"
            dest.mkdir(exist_ok=True)
            p.rename(dest / p.name)
        return 0
    if args.tavily:
        n, cached = ingest_tavily(sb, cfg, cache_only=args.cache_only)
        print(f"📎 Trade Desk リサーチ Tavily: inserted={n} cache_hits={cached}")
        return 0

    print(
        "指定がありません。--from-file / --from-inbox / --tavily [--cache-only]",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
