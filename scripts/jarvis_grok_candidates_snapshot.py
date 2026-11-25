#!/usr/bin/env python3
"""Grok 候補（S9 など）の取り込み結果を sync_meta(grok_candidates_snapshot) に写す（AI なし）。

jarvis_s9_candidates_apply.py が MD を台帳へ取り込んだ直後に呼ぶ。MD は取り込み後に
90_archive へ動くので、「新規／重複（理由つき）／判断待ち／送らない」の結果はここで残さないと
後から見えなくなる（2026-10-21 設計依頼：既に登録済みかが Grok から見えず重複依頼が起きる）。

- 既存テーブル sync_meta の 1 キーに置くだけ。新しいテーブル・権限は作らない。
- 送信待ち／送信済みは画面側が台帳（kurashift_re_mgmt_vendors）と突き合わせて決める。ここでは持たない。
- 直近 KEEP_DAYS 日・最大 MAX_ITEMS 件。同じ会社（key）は新しい取り込みで上書き。
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

SNAPSHOT_KEY = "grok_candidates_snapshot"
KEEP_DAYS = 21
MAX_ITEMS = 150
KINDS = ("add", "dup", "consult", "drop")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def make_item(
    row: dict[str, Any],
    kind: str,
    why: str,
    *,
    key: str,
    n: int,
    source_md: str,
    now: datetime,
    existing: dict[str, Any] | None = None,
    upgraded: bool = False,
) -> dict[str, Any]:
    """画面と採用ボタン（s9 の候補ペイロードと同じ項目）に必要な最小限。"""
    if kind not in KINDS:
        raise ValueError(f"kind が不正です: {kind!r}")
    item: dict[str, Any] = {
        "key": key,
        "kind": kind,
        "why": str(why or "")[:200],
        "seen_at": _iso(now),
        "md": str(source_md or "")[:80],
        "cand": {
            "n": int(n),
            "name": str(row.get("name") or "")[:120],
            "area": str(row.get("property_area") or "")[:40],
            "pref": str(row.get("prefecture") or "愛知県")[:20],
            "city": str(row.get("city") or "")[:20],
            "lane": str(row.get("property_lane") or "midori_caramel")[:40],
            "url": str(row.get("url") or "")[:300],
            "cu": str(row.get("contact_url") or "")[:300],
            "em": str(row.get("contact_email") or "")[:120],
            "tel": str(row.get("phone") or "")[:30],
            "ch": str(row.get("channel") or "")[:20],
            "memo": str(row.get("_memo") or "")[:200],
            "src": str(source_md or "")[:80],
            "dt": str(row.get("discovered_at") or "")[:10],
        },
    }
    if existing is not None:
        item["existing"] = {
            "name": str(existing.get("name") or "")[:120],
            "status": str(existing.get("status") or ""),
        }
    if upgraded:
        item["upgraded"] = True
    return item


def merge_items(
    prev: list[dict[str, Any]], new: list[dict[str, Any]], *, now: datetime
) -> list[dict[str, Any]]:
    """key で重ね、期限切れを落とし、新しい順に MAX_ITEMS 件まで。"""
    by_key: dict[str, dict[str, Any]] = {}
    for it in prev + new:
        k = str(it.get("key") or "")
        if not k or it.get("kind") not in KINDS:
            continue
        old = by_key.get(k)
        if old is None or str(it.get("seen_at") or "") >= str(old.get("seen_at") or ""):
            by_key[k] = it
    cutoff = _iso(now - timedelta(days=KEEP_DAYS))
    kept = [it for it in by_key.values() if str(it.get("seen_at") or "") >= cutoff]
    kept.sort(key=lambda it: str(it.get("seen_at") or ""), reverse=True)
    return kept[:MAX_ITEMS]


def _rest(path: str, params: dict | None = None, method: str = "GET", body: Any = None) -> Any:
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").rstrip("/")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        raise RuntimeError("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が未設定")
    q = ("?" + urllib.parse.urlencode(params, safe=",.:()*>")) if params else ""
    req = urllib.request.Request(
        f"{url}/rest/v1/{path}{q}",
        method=method,
        data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal,resolution=merge-duplicates",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def load_prev() -> list[dict[str, Any]]:
    rows = _rest("sync_meta", {"select": "value", "key": f"eq.{SNAPSHOT_KEY}"}) or []
    if not rows:
        return []
    try:
        v = json.loads(rows[0].get("value") or "{}")
    except (TypeError, ValueError):
        # 読めない＝空として上書きすると履歴が消えるので、呼び出し側で失敗扱いにする
        raise RuntimeError("既存の grok_candidates_snapshot が読めません（上書きしません）")
    items = v.get("items") if isinstance(v, dict) else None
    return [i for i in items or [] if isinstance(i, dict)]


def push(new: list[dict[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    """soft-fail：失敗しても台帳取り込みは止めない。"""
    now = now or datetime.now(timezone.utc)
    try:
        merged = merge_items(load_prev(), new, now=now)
        _rest(
            "sync_meta",
            {"on_conflict": "key"},
            method="POST",
            body={
                "key": SNAPSHOT_KEY,
                "value": json.dumps({"generated_at": _iso(now), "items": merged}, ensure_ascii=False),
                "updated_at": _iso(now),
            },
        )
        return {"ok": True, "items": len(merged), "new": len(new)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}
