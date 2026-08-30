#!/usr/bin/env python3
"""融資アプローチ先 YAML → jarvis-dashboard Supabase + 神大家Q&A／セミナーから intel 補完。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_lenders_sync.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_lenders_sync.py --apply
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_lenders_sync.py --apply --with-kamiooya
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

import urllib.error
import urllib.request

REPO = Path(__file__).resolve().parents[1]
YAML_PATH = REPO / "config" / "kurashift_lenders_approach.yaml"
SEMINAR_FILES = [
    REPO
    / "dx_kyouyuu/05_knowledge/神大家動画/基礎講座 STEP3/STEP3-2 金融機関情報（2025／7時点の全国融資情報とりまとめ）part2.md",
    REPO
    / "dx_kyouyuu/05_knowledge/神大家動画/実践動画【融資戦略編】～各地域特集～/【実践】東海地域 4県の融資情報.md",
]
ONEDRIVE_FINANCE = Path(
    "/Users/matsunomasaharu2/Library/CloudStorage/OneDrive-個人用/"
    "215_神・大家さん倶楽部/10_【購入】物件購入,融資"
)


def _load_kamiooya_env() -> None:
    """SUPABASE_* が無いときチャットボット scripts/.env を読む（値は出さない）."""
    if (os.environ.get("SUPABASE_URL") or "").strip():
        return
    candidates = [
        REPO
        / "215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/scripts/.env",
        Path.home()
        / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/scripts/.env",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            if k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY") and not (
                os.environ.get(k) or ""
            ).strip():
                os.environ[k] = v.strip().strip('"').strip("'")
        break


def _load_yaml() -> dict[str, Any]:
    import yaml  # type: ignore

    return yaml.safe_load(YAML_PATH.read_text(encoding="utf-8")) or {}


def _sb_url_key(*, jarvis: bool) -> tuple[str, str]:
    if jarvis:
        url = (os.environ.get("JARVIS_SUPABASE_URL") or "").rstrip("/")
        key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
        label = "JARVIS_SUPABASE_*"
    else:
        url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
        key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
        label = "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY (kamiooya-qa)"
    if not url or not key:
        raise SystemExit(f"{label} 未設定")
    return url, key


def _req(
    method: str,
    url: str,
    key: str,
    path: str,
    body: Any | None = None,
    *,
    prefer: str | None = None,
) -> Any:
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"{url}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace")[:500]
        raise SystemExit(f"HTTP {e.code} {path}: {err}") from e


def _display_name(name: str, category: str) -> str:
    if category == "shinkin" and not name.endswith("信用金庫") and "信用" not in name:
        return f"{name}信用金庫"
    return name


def _slug(name: str, code: str | None) -> str:
    if code:
        cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", str(code).lower())
        if cleaned:
            return cleaned[:48]
    # Prefer stable ascii id from hash of name (Japanese-safe for HTTP)
    import hashlib

    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]
    base = re.sub(r"[^a-zA-Z0-9]", "", name)[:16].lower() or "lender"
    return f"{base}_{digest}"[:48]


def upsert_lenders(rows: list[dict[str, Any]], *, dry_run: bool) -> list[dict[str, Any]]:
    url, key = _sb_url_key(jarvis=True)
    payload = []
    for L in rows:
        lid = _slug(L["name"], L.get("code"))
        approach = L.get("approach") or "yes"
        if approach == "yes" and "後回し" in (L.get("notes") or ""):
            approach = "deferred"
        payload.append(
            {
                "id": lid,
                "code": L.get("code"),
                "name": L["name"],
                "display_name": _display_name(L["name"], L.get("category") or "bank"),
                "category": L.get("category") or "bank",
                "approach": approach,
                "case_report": bool(L.get("case_report")),
                "matsuno_notes": L.get("notes"),
                "store_page_label": L.get("store_page_label"),
                "region_tags": ["tokai"]
                if (L.get("category") in ("shinkin", "shinkumi") or "名古屋" in L["name"] or "あいち" in L["name"])
                else [],
                "active": True,
                "source_xlsx": "★金融機関一覧(アプローチ先まとめ).xlsx",
                "updated_at": date.today().isoformat() + "T00:00:00+09:00",
            }
        )
    if dry_run:
        print(json.dumps({"dry_run_lenders": len(payload), "sample": payload[:3]}, ensure_ascii=False, indent=2))
        return payload
    _req(
        "POST",
        url,
        key,
        "/rest/v1/kurashift_lenders?on_conflict=id",
        payload,
        prefer="resolution=merge-duplicates,return=minimal",
    )
    print(f"# upserted lenders: {len(payload)}")
    return payload


def _seminar_snippets(name: str) -> list[dict[str, str]]:
    out = []
    short = re.sub(r"(銀行|信用金庫|信用組合)$", "", name)
    for path in SEMINAR_FILES:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if short not in text and name not in text:
            continue
        # grab nearby lines
        lines = text.splitlines()
        hits = []
        for i, line in enumerate(lines):
            if short in line or name in line:
                chunk = "\n".join(lines[max(0, i - 1) : i + 4]).strip()
                hits.append(chunk[:800])
        if hits:
            out.append(
                {
                    "source_kind": "seminar",
                    "source_ref": str(path.relative_to(REPO)),
                    "summary": hits[0][:500],
                    "source_excerpt": hits[0],
                }
            )
    return out


def _onedrive_file_refs(name: str) -> list[dict[str, str]]:
    if not ONEDRIVE_FINANCE.is_dir():
        return []
    short = re.sub(r"(銀行|信用金庫|信用組合)$", "", name)
    refs = []
    for p in ONEDRIVE_FINANCE.rglob("*"):
        if not p.is_file():
            continue
        if short in p.name or name in p.name:
            refs.append(
                {
                    "source_kind": "onedrive",
                    "source_ref": str(p),
                    "summary": f"フォルダ内ファイル: {p.name}",
                    "source_excerpt": p.name,
                }
            )
    # also generic PDFs as catalog refs once per sync via special lender? skip
    return refs[:5]


def _kamiooya_search(name: str, limit: int = 5) -> list[dict[str, str]]:
    from urllib.parse import quote

    url, key = _sb_url_key(jarvis=False)
    short = re.sub(r"(銀行|信用金庫|信用組合)$", "", name)
    path = (
        "/rest/v1/comments?select=comment_id,author_name,posted_at,content,forum_category"
        f"&content=ilike.*{quote(short)}*"
        "&or=(is_deleted.is.null,is_deleted.eq.false)"
        f"&order=posted_at.desc&limit={limit}"
    )
    try:
        rows = _req("GET", url, key, path) or []
    except SystemExit as e:
        print(f"# kamiooya skip {name}: {e}", file=sys.stderr)
        return []
    out = []
    for r in rows:
        content = (r.get("content") or "").strip()
        if len(content) < 40:
            continue
        out.append(
            {
                "source_kind": "kamiooya_qa",
                "source_ref": f"comments:{r.get('comment_id')}",
                "summary": content[:280].replace("\n", " "),
                "source_excerpt": content[:900],
            }
        )
    return out


def upsert_intel(
    lenders: list[dict[str, Any]],
    *,
    dry_run: bool,
    with_kamiooya: bool,
) -> int:
    url, key = _sb_url_key(jarvis=True)
    # clear auto-sourced intel for re-sync (keep manual)
    if not dry_run:
        # delete non-manual for these lenders
        for L in lenders:
            lid = L["id"]
            path = (
                f"/rest/v1/kurashift_lender_intel?lender_id=eq.{lid}"
                "&source_kind=in.(seminar,kamiooya_qa,onedrive,xlsx)"
            )
            _req("DELETE", url, key, path)

    count = 0
    batch: list[dict[str, Any]] = []
    for L in lenders:
        lid = L["id"]
        name = L.get("display_name") or L["name"]
        # xlsx notes as intel
        if L.get("matsuno_notes"):
            batch.append(
                {
                    "lender_id": lid,
                    "kind": None,
                    "summary": L["matsuno_notes"],
                    "source_kind": "xlsx",
                    "source_ref": "★金融機関一覧(アプローチ先まとめ).xlsx",
                }
            )
        for snip in _seminar_snippets(name) + _seminar_snippets(L["name"]):
            batch.append({"lender_id": lid, **snip})
        for ref in _onedrive_file_refs(name):
            batch.append({"lender_id": lid, **ref})
        if with_kamiooya:
            try:
                for k in _kamiooya_search(name):
                    batch.append({"lender_id": lid, **k})
            except SystemExit as e:
                print(f"# kamiooya disabled: {e}", file=sys.stderr)
                with_kamiooya = False

    # normalize rows
    clean = []
    for b in batch:
        row = {
            "lender_id": b["lender_id"],
            "kind": b.get("kind"),
            "income_requirement": b.get("income_requirement"),
            "specialty": b.get("specialty"),
            "rate_notes": b.get("rate_notes"),
            "full_loan_notes": b.get("full_loan_notes"),
            "partner_realtors": b.get("partner_realtors"),
            "summary": b.get("summary") or "",
            "source_kind": b.get("source_kind") or "manual",
            "source_ref": b.get("source_ref"),
            "source_excerpt": b.get("source_excerpt"),
            "observed_on": date.today().isoformat(),
            "payload": {},
        }
        clean.append(row)
        count += 1

    if dry_run:
        print(json.dumps({"dry_run_intel": count, "sample": clean[:2]}, ensure_ascii=False, indent=2))
        return count
    # chunk insert
    for i in range(0, len(clean), 50):
        chunk = clean[i : i + 50]
        if not chunk:
            continue
        _req("POST", url, key, "/rest/v1/kurashift_lender_intel", chunk, prefer="return=minimal")
    print(f"# inserted intel rows: {count}")
    return count


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--with-kamiooya", action="store_true", help="神大家 comments を検索して補完")
    args = p.parse_args()
    if not args.dry_run and not args.apply:
        print("ERROR: --dry-run または --apply", file=sys.stderr)
        return 2
    if args.with_kamiooya:
        _load_kamiooya_env()
    data = _load_yaml()
    raw = list(data.get("lenders") or [])
    # build id map like upsert
    lenders_payload = []
    for L in raw:
        lid = _slug(L["name"], L.get("code"))
        approach = L.get("approach") or "yes"
        if "後回し" in (L.get("notes") or ""):
            approach = "deferred"
        lenders_payload.append(
            {
                "id": lid,
                "name": L["name"],
                "display_name": _display_name(L["name"], L.get("category") or "bank"),
                "matsuno_notes": L.get("notes"),
                "approach": approach,
            }
        )
    upsert_lenders(raw, dry_run=args.dry_run)
    upsert_intel(lenders_payload, dry_run=args.dry_run, with_kamiooya=args.with_kamiooya)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
