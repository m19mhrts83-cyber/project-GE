#!/usr/bin/env python3
"""業者 URL の生存 Web チェック → YAML alive_* 更新。

  cd ~/git-repos
  ~/selenium_env/venv/bin/python scripts/jarvis_vendor_alive_web_check.py --kind re --limit 20
  ~/selenium_env/venv/bin/python scripts/jarvis_vendor_alive_web_check.py --kind mgmt --apply
  ~/selenium_env/venv/bin/python scripts/jarvis_vendor_alive_web_check.py --kind repair --apply --limit 30

電話 ok（期限内）は上書きしない。結果は --apply で YAML 更新。
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_vendor_alive_lib import (  # noqa: E402
    apply_web_result,
    build_alive_queue,
    ensure_alive_fields,
    is_overdue,
    pick_check_url,
)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT_S = 8


def load_kind(kind: str) -> tuple[Any, list[dict[str, Any]], Path]:
    if kind == "re":
        from jarvis_kurashift_vendor_list import LIST_PATH, load_list, save_list

        data = load_list()
        vendors = [v for v in (data.get("vendors") or []) if isinstance(v, dict)]
        return data, vendors, LIST_PATH
    if kind == "mgmt":
        from jarvis_kurashift_mgmt_vendor_list import LIST_PATH, load_list, save_list

        data = load_list()
        vendors = [v for v in (data.get("vendors") or []) if isinstance(v, dict)]
        return data, vendors, LIST_PATH
    if kind == "repair":
        from jarvis_kurashift_repair_vendor_list import LIST_PATH, load_list, save_list

        data = load_list()
        vendors = [v for v in (data.get("vendors") or []) if isinstance(v, dict)]
        return data, vendors, LIST_PATH
    raise SystemExit(f"unknown kind: {kind}")


def save_kind(kind: str, data: Any) -> None:
    if kind == "re":
        from jarvis_kurashift_vendor_list import save_list

        save_list(data)
    elif kind == "mgmt":
        from jarvis_kurashift_mgmt_vendor_list import save_list

        save_list(data)
    elif kind == "repair":
        from jarvis_kurashift_repair_vendor_list import save_list

        save_list(data)


def http_probe(url: str) -> tuple[bool, str]:
    from urllib.parse import urlsplit, urlunsplit, quote

    parts = urlsplit(url.strip())
    # 非ASCIIパスを安全にエンコード
    path = quote(parts.path or "/", safe="/%")
    query = quote(parts.query, safe="=&%")
    safe_url = urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))

    req = urllib.request.Request(
        safe_url,
        method="HEAD",
        headers={"User-Agent": UA, "Accept": "*/*"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            if 200 <= int(code) < 400:
                return True, f"HEAD {code}"
            if int(code) in (405, 403, 501):
                pass
            else:
                return False, f"HEAD {code}"
    except urllib.error.HTTPError as e:
        if e.code in (405, 403, 501):
            pass
        elif 200 <= e.code < 400:
            return True, f"HEAD {e.code}"
        else:
            if e.code not in (404, 405, 403):
                return False, f"HEAD {e.code}"
    except Exception:
        pass

    req_g = urllib.request.Request(
        safe_url,
        method="GET",
        headers={"User-Agent": UA, "Accept": "text/html,*/*"},
    )
    try:
        with urllib.request.urlopen(req_g, timeout=TIMEOUT_S) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            if 200 <= int(code) < 400:
                return True, f"GET {code}"
            return False, f"GET {code}"
    except urllib.error.HTTPError as e:
        if 200 <= e.code < 400:
            return True, f"GET {e.code}"
        return False, f"GET {e.code}"
    except Exception as e:  # noqa: BLE001
        return False, f"err:{str(e)[:100]}"


def select_targets(
    vendors: list[dict[str, Any]],
    *,
    kind: str,
    limit: int,
    overdue_only: bool,
) -> list[dict[str, Any]]:
    with_url: list[dict[str, Any]] = []
    for v in vendors:
        ensure_alive_fields(v, kind=kind)
        if not pick_check_url(v):
            continue
        if overdue_only and not is_overdue(v, kind=kind):
            continue
        with_url.append(v)
    # 期限切れ優先（キューと同型スコア）
    queued_ids = {str(x["id"]) for x in build_alive_queue(with_url, kind=kind, limit=10_000)}
    with_url.sort(key=lambda v: (0 if str(v.get("id")) in queued_ids else 1, str(v.get("id"))))
    return with_url[: max(0, limit)]


def main() -> int:
    ap = argparse.ArgumentParser(description="Vendor alive Web check")
    ap.add_argument(
        "--kind",
        choices=("re", "repair", "mgmt"),
        default="re",
        help="リスト種別",
    )
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument(
        "--all-urls",
        action="store_true",
        help="期限切れに限らず URL あり全件（上限内）",
    )
    args = ap.parse_args()

    data, vendors, path = load_kind(args.kind)
    targets = select_targets(
        vendors,
        kind=args.kind,
        limit=args.limit,
        overdue_only=not args.all_urls,
    )
    results: list[dict[str, Any]] = []
    changed = 0
    for v in targets:
        url = pick_check_url(v)
        ok, detail = http_probe(url)
        did = apply_web_result(v, web_ok=ok, note=detail, kind=args.kind)
        if did:
            changed += 1
        results.append(
            {
                "id": v.get("id"),
                "name": v.get("name"),
                "url": url,
                "web_ok": ok,
                "detail": detail,
                "updated": did,
                "alive_status": v.get("alive_status"),
            }
        )

    if args.apply and changed:
        save_kind(args.kind, data)

    out = {
        "ok": True,
        "kind": args.kind,
        "yaml": str(path),
        "checked": len(results),
        "changed": changed,
        "apply": bool(args.apply),
        "results": results,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(
        f"📎 alive_web: kind={args.kind} checked={len(results)} "
        f"changed={changed} apply={bool(args.apply)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
