#!/usr/bin/env python3
"""分野別ニュースを trade_research に取り込む。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  # ChatGPT週次メモ（ファイル横流し）
  ~/selenium_env/venv/bin/python scripts/jarvis_trade_research_ingest.py \\
    --from-file path/to/weekly.md --source chatgpt_weekly --topic ai,space
  # Tavily 週次（テーマ横断）
  ~/selenium_env/venv/bin/python scripts/jarvis_trade_research_ingest.py --tavily
  # inbox フォルダを一括
  ~/selenium_env/venv/bin/python scripts/jarvis_trade_research_ingest.py --from-inbox
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml

from jarvis_trade_common import JST, REPO, sb_client

THEMES = REPO / "config" / "trade_research_themes.yaml"
INBOX = REPO / ".jarvis_state" / "trade_research_inbox"


def load_themes() -> dict:
    return yaml.safe_load(THEMES.read_text(encoding="utf-8")) or {}


def insert_research(sb, *, source: str, topic: str, summary: str, url: str | None, payload: dict) -> None:
    sb.table("trade_research").insert(
        {
            "source": source,
            "topic": topic,
            "summary": summary[:8000],
            "url": url,
            "payload": payload,
            "fetched_at": datetime.now(JST).isoformat(),
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


def tavily_search(query: str) -> dict:
    import urllib.request

    key = (os.environ.get("TAVILY_API_KEY") or "").strip()
    if not key:
        raise SystemExit("TAVILY_API_KEY が未設定です")
    body = json.dumps(
        {"api_key": key, "query": query, "search_depth": "basic", "max_results": 5}
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ingest_tavily(sb, cfg: dict) -> int:
    n = 0
    for th in cfg.get("themes") or []:
        for q in th.get("queries") or []:
            data = tavily_search(q)
            results = data.get("results") or []
            lines = []
            urls = []
            for r in results[:5]:
                title = (r.get("title") or "").strip()
                url = (r.get("url") or "").strip()
                snippet = (r.get("content") or "").strip()[:280]
                lines.append(f"- {title}: {snippet}")
                if url:
                    urls.append(url)
            summary = f"query={q}\n" + "\n".join(lines)
            insert_research(
                sb,
                source="tavily",
                topic=th["id"],
                summary=summary,
                url=urls[0] if urls else None,
                payload={"query": q, "urls": urls, "answer": data.get("answer")},
            )
            print(f"# tavily {th['id']} q={q!r} hits={len(results)}")
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="Trade Desk リサーチ取込")
    ap.add_argument("--from-file", default="")
    ap.add_argument("--from-inbox", action="store_true")
    ap.add_argument("--tavily", action="store_true")
    ap.add_argument("--source", default="chatgpt_weekly")
    ap.add_argument("--topic", default="ai")
    args = ap.parse_args()

    sb = sb_client()
    cfg = load_themes()
    INBOX.mkdir(parents=True, exist_ok=True)

    if args.from_file:
        ingest_file(sb, Path(args.from_file), args.source, args.topic)
        return 0
    if args.from_inbox:
        files = sorted(p for p in INBOX.iterdir() if p.is_file() and p.suffix.lower() in {".md", ".txt"})
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
        n = ingest_tavily(sb, cfg)
        print(f"📎 Trade Desk リサーチ Tavily: {n} queries")
        return 0

    print("指定がありません。--from-file / --from-inbox / --tavily", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
