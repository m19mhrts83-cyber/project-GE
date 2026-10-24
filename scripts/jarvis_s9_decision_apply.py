#!/usr/bin/env python3
"""S9 候補の「採用／見送り」を台帳へ反映（Slack ボタン → kurashift_jobs → ここ）.

Vercel の consult-action / /api/g/s9 が `re_mgmt_vendor_decision` を積み、
Mac の kurashift job worker が本スクリプトを実行する。

  ~/selenium_env/venv/bin/python scripts/jarvis_s9_decision_apply.py \
    --payload-json '{"decision":"adopt","name":"...","area":"...","channel":"web_form",...}'
  ~/selenium_env/venv/bin/python scripts/jarvis_s9_decision_apply.py --payload-json … --dry-run

採用: status=pending（送信候補になる）／見送り: status=skip（二度と相談しない）
反映後に YAML → Supabase を同期（--no-sync で止められる）。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_kurashift_mgmt_vendor_list as ml  # noqa: E402
import jarvis_s9_candidates_apply as s9  # noqa: E402
import jarvis_s9_slack_blocks as blocks  # noqa: E402

DECISIONS = ("adopt", "skip")
STATUS_BY_DECISION = {"adopt": "pending", "skip": "skip"}
NOTE_BY_DECISION = {"adopt": "S9 Slack 採用", "skip": "S9 Slack 見送り"}


def _row_from_payload(p: dict[str, Any]) -> dict[str, Any]:
    decision = str(p.get("decision") or "")
    if decision not in DECISIONS:
        raise SystemExit(f"decision が不正です: {decision!r}")
    name = str(p.get("name") or "").strip()
    if not name:
        raise SystemExit("name が空です")
    area = str(p.get("area") or "").strip()
    memo = str(p.get("memo") or "").strip()
    note_prefix = NOTE_BY_DECISION[decision]
    note = " ".join(x for x in (note_prefix, memo) if x)[:400]
    return {
        "name": name,
        "area": area or ("愛知県" if not area else area),
        "prefecture": str(p.get("pref") or "愛知県").strip() or "愛知県",
        "city": str(p.get("city") or "").strip(),
        "property_area": area,
        "property_lane": str(p.get("lane") or "midori_caramel").strip()
        or "midori_caramel",
        "url": str(p.get("url") or "").strip()[:300],
        "contact_url": str(p.get("cu") or p.get("url") or "").strip()[:300],
        "channel": str(p.get("ch") or "web_form").strip() or "web_form",
        "contact_email": str(p.get("em") or "").strip()[:120],
        "phone": str(p.get("tel") or "").strip()[:30],
        "status": STATUS_BY_DECISION[decision],
        "source": f"s9_slack_{str(p.get('dt') or '')}".rstrip("_") or "s9_slack",
        "notes": note,
        "discovered_at": str(p.get("dt") or ml.today_jst())[:10],
        "vacancy_listing_ok": None,
        "_decision": decision,
    }


def apply_decision(
    payload: dict[str, Any], *, list_path: Path | None = None, dry_run: bool = False
) -> dict[str, Any]:
    decision = str(payload.get("decision") or "")
    row = _row_from_payload(payload)
    data = ml.load_list(list_path)
    vendors = [v for v in data.get("vendors") or [] if isinstance(v, dict)]
    existing = s9.find_existing(row, vendors)
    action = "added"
    if existing:
        action = "updated"
        existing["status"] = row["status"]
        existing["notes"] = row["notes"]
        if row["url"] and not existing.get("url"):
            existing["url"] = row["url"]
        if row["contact_url"] and not existing.get("contact_url"):
            existing["contact_url"] = row["contact_url"]
        if row["contact_email"] and not existing.get("contact_email"):
            existing["contact_email"] = row["contact_email"]
        if not dry_run:
            ml.save_list(data, list_path)
        vid = str(existing.get("id") or "")
    else:
        clean = {k: v for k, v in row.items() if not k.startswith("_")}
        res = ml.merge_append([clean], dry_run=dry_run, path=list_path)
        vid = ""
        for v in ml.load_list(list_path).get("vendors") or []:
            if isinstance(v, dict) and v.get("name") == row["name"]:
                vid = str(v.get("id") or "")
                break
        action = "added" if res.get("added") else "unchanged"
    return {
        "ok": True,
        "decision": decision,
        "action": action,
        "vendor_id": vid,
        "name": row["name"],
        "status": row["status"],
        "dry_run": dry_run,
    }


def _sync() -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(REPO / "scripts" / "jarvis_kurashift_mgmt_vendor_sync.py"),
        "--apply",
    ]
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    return {"rc": r.returncode, "tail": (r.stdout or r.stderr or "")[-500:]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--payload-json", default="", help="job payload（JSON 文字列）")
    ap.add_argument("--payload-file", default="", help="job payload（JSON ファイル）")
    ap.add_argument("--list-path", default="", help="台帳 YAML（テスト用）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-sync", action="store_true")
    ap.add_argument("--no-notify", action="store_true", help="Slack スレッド返信をしない")
    args = ap.parse_args()

    raw = args.payload_json
    if args.payload_file:
        raw = Path(args.payload_file).read_text(encoding="utf-8")
    if not raw:
        ap.error("--payload-json または --payload-file")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        ap.error("payload は JSON オブジェクト")

    list_path = Path(args.list_path) if args.list_path else None
    res = apply_decision(payload, list_path=list_path, dry_run=args.dry_run)
    if not args.dry_run and not args.no_sync:
        res["sync"] = _sync()

    if not args.dry_run and not args.no_notify:
        label = blocks.DECISION_LABEL.get(res["decision"], res["decision"])
        icon = blocks.DECISION_ICON.get(res["decision"], "•")
        note = "台帳へ反映済み" if res["action"] in ("added", "updated") else "変更なし（既に同状態）"
        text = f"{icon} *{res['name']}* を{label}しました（{note}）"
        if res.get("vendor_id"):
            text += f"\nid: `{res['vendor_id']}`"
        blocks.thread_ack(
            channel=str(payload.get("channel") or ""),
            thread_ts=str(payload.get("message_ts") or ""),
            text=text,
        )

    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
