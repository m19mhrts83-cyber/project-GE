#!/usr/bin/env python3
"""Fetch FlowForge (AI Automation) flow JSON via existing share API.

FlowForge rejects requests without its own Origin/Referer (403 forbidden_origin).
This CLI sets Origin so Codex / Cursor / Claude can read flows without screenshots.

Usage:
  python scripts/jarvis_flowforge_share_fetch.py --share tn9-F4fhdIgHVpRl
  python scripts/jarvis_flowforge_share_fetch.py --flow-id flow_M8SvKC1IDTDi496Vw-DgGjpD
  python scripts/jarvis_flowforge_share_fetch.py --url 'https://…/share/tn9-F4fhdIgHVpRl'
  python scripts/jarvis_flowforge_share_fetch.py --share tn9-… --summary
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DEFAULT_BASE = "https://flowforge-259747770348.asia-northeast1.run.app"
SHARE_URLS = REPO / "config" / "flowforge_share_urls.json"
SHARE_ID_RE = re.compile(r"/share/([A-Za-z0-9_-]+)")


def load_share_map() -> dict[str, str]:
    if not SHARE_URLS.is_file():
        return {}
    data = json.loads(SHARE_URLS.read_text(encoding="utf-8"))
    return dict(data.get("by_flow_id") or {})


def share_id_from_url(url: str) -> str:
    m = SHARE_ID_RE.search(url)
    if not m:
        raise SystemExit(f"shareId を URL から抽出できません: {url}")
    return m.group(1)


def resolve_share_id(args: argparse.Namespace) -> tuple[str, str]:
    """Return (share_id, base_url)."""
    base = (args.base or DEFAULT_BASE).rstrip("/")
    if args.share:
        return args.share.strip(), base
    if args.url:
        sid = share_id_from_url(args.url)
        # allow alternate host in URL
        if args.url.startswith("http"):
            from urllib.parse import urlparse

            p = urlparse(args.url)
            if p.scheme and p.netloc:
                base = f"{p.scheme}://{p.netloc}"
        return sid, base
    if args.flow_id:
        m = load_share_map()
        url = m.get(args.flow_id)
        if not url:
            raise SystemExit(
                f"flow_id={args.flow_id} の share URL が "
                f"{SHARE_URLS} にありません"
            )
        return share_id_from_url(url), base
    raise SystemExit("--share / --url / --flow-id のいずれかを指定してください")


def fetch_share(base: str, share_id: str, timeout: float) -> dict[str, Any]:
    url = f"{base}/api/shares/{share_id}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Origin": base,
            "Referer": f"{base}/share/{share_id}",
            "User-Agent": "jarvis-flowforge-share-fetch/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {e.code} from {url}: {err_body[:500]}") from e
    except urllib.error.URLError as e:
        raise SystemExit(f"request failed: {e}") from e


def summarize(payload: dict[str, Any]) -> dict[str, Any]:
    flow = payload.get("flow") or {}
    nodes = flow.get("nodes") or []
    edges = flow.get("edges") or []
    kinds: dict[str, int] = {}
    titles: list[dict[str, str]] = []
    for n in nodes:
        data = n.get("data") or {}
        kind = str(data.get("kind") or n.get("type") or "?")
        kinds[kind] = kinds.get(kind, 0) + 1
        titles.append(
            {
                "id": str(n.get("id") or ""),
                "kind": kind,
                "title": str(data.get("title") or data.get("toolName") or ""),
            }
        )
    return {
        "id": flow.get("id"),
        "name": flow.get("name"),
        "description": flow.get("description"),
        "updatedAt": flow.get("updatedAt"),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "kinds": kinds,
        "nodes": titles,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--share", help="shareId（/share/ の後ろ）")
    g.add_argument("--url", help="https://…/share/{id} 形式")
    g.add_argument("--flow-id", help="flow_…（config/flowforge_share_urls.json で解決）")
    ap.add_argument("--base", default=DEFAULT_BASE, help="FlowForge base URL")
    ap.add_argument("--summary", action="store_true", help="要約 JSON のみ")
    ap.add_argument("--out", type=Path, help="保存先パス（省略時は stdout）")
    ap.add_argument("--timeout", type=float, default=30.0)
    args = ap.parse_args()

    share_id, base = resolve_share_id(args)
    payload = fetch_share(base, share_id, args.timeout)
    out_obj: Any = summarize(payload) if args.summary else payload
    text = json.dumps(out_obj, ensure_ascii=False, indent=2) + "\n"

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        flow = (payload.get("flow") or {}) if isinstance(payload, dict) else {}
        print(
            f"saved {args.out}  share={share_id}  "
            f"flow={flow.get('id')}  nodes={len(flow.get('nodes') or [])}",
            file=sys.stderr,
        )
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
