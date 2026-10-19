#!/usr/bin/env python3
"""業者開拓・定期情報確認（nurture）due 抽出・定型 preview・mark・キュー。

Phase1: due 抽出 → state（送信しない）
Phase2: 定型 preview／--next／--mark／--queue-outbox（approved 時のみキュー）

正本: docs/KURASHIFT_業者開拓_定期情報確認_20261019.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
STATE_DIR = REPO / ".jarvis_state"
STATE_PATH = STATE_DIR / "vendor_nurture_due.json"
DEFAULT_CFG = REPO / "config" / "kurashift_vendor_nurture.yaml"

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _today() -> date:
    return datetime.now().astimezone().date()


def _parse_day(raw: Any) -> date | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _last_outbound(v: dict[str, Any]) -> date | None:
    days = [
        _parse_day(v.get("contacted_at")),
        _parse_day(v.get("nurture_last_sent_at")),
    ]
    days = [d for d in days if d]
    return max(days) if days else None


def _eligible(v: dict[str, Any], *, include: set[str], exclude: set[str]) -> bool:
    st = str(v.get("status") or "pending").strip()
    if st in exclude:
        return False
    if _parse_day(v.get("contacted_at")):
        return True
    return st in include


def _area_line(template: dict[str, Any], list_region: str) -> str:
    lines = template.get("area_lines") or {}
    if not isinstance(lines, dict):
        lines = {}
    region = (list_region or "").strip() or "default"
    return str(lines.get(region) or lines.get("default") or "愛知・岐阜・静岡")


def render_template(
    template: dict[str, Any],
    *,
    vendor_name: str,
    list_region: str = "chubu",
    short: bool = False,
) -> tuple[str, str]:
    """Return (subject, body)."""
    subject = str(template.get("subject") or "最近の物件情報について")
    key = "body_short" if short else "body"
    raw = str(template.get(key) or template.get("body") or "").rstrip() + "\n"
    body = raw.format(
        vendor_name=vendor_name or "ご担当者",
        area_line=_area_line(template, list_region),
    )
    return subject, body


def collect_due(
    *,
    list_path: Path,
    interval_days: int,
    include_statuses: list[str],
    exclude_statuses: list[str],
    as_of: date | None = None,
) -> dict[str, Any]:
    as_of = as_of or _today()
    data = _load_yaml(list_path)
    vendors = [v for v in (data.get("vendors") or []) if isinstance(v, dict) and v.get("id")]
    include = {str(s) for s in include_statuses}
    exclude = {str(s) for s in exclude_statuses}
    threshold = as_of - timedelta(days=interval_days)

    due: list[dict[str, Any]] = []
    soon: list[dict[str, Any]] = []
    skipped = 0
    for v in vendors:
        if not _eligible(v, include=include, exclude=exclude):
            skipped += 1
            continue
        last = _last_outbound(v)
        if last is None:
            skipped += 1
            continue
        gap = (as_of - last).days
        days_until = interval_days - gap
        row = {
            "id": str(v["id"]),
            "name": str(v.get("name") or v["id"]),
            "status": str(v.get("status") or ""),
            "list_region": str(v.get("list_region") or "chubu"),
            "contacted_at": str(v.get("contacted_at") or "")[:10],
            "nurture_last_sent_at": str(v.get("nurture_last_sent_at") or "")[:10],
            "nurture_last_reply": str(v.get("nurture_last_reply") or "none"),
            "nurture_last_reply_at": str(v.get("nurture_last_reply_at") or "")[:10],
            "last_outbound": last.isoformat(),
            "gap_days": gap,
            "days_until_due": days_until,
            "contact_email": str(v.get("contact_email") or ""),
            "contact_url": str(v.get("contact_url") or ""),
            "channel": str(v.get("channel") or ""),
        }
        if last <= threshold:
            due.append(row)
        else:
            soon.append(row)

    due.sort(key=lambda r: (-int(r["gap_days"]), str(r["id"])))
    soon.sort(key=lambda r: (int(r["days_until_due"]), str(r["id"])))
    return {
        "as_of": as_of.isoformat(),
        "interval_days": interval_days,
        "list_path": str(list_path),
        "total_vendors": len(vendors),
        "skipped_or_ineligible": skipped,
        "due_count": len(due),
        "due": due,
        "soon": soon,
    }


def mark_nurture_sent(
    vid: str,
    *,
    note: str = "",
    dry_run: bool,
    reply: str | None = None,
    reply_note: str = "",
) -> dict[str, Any]:
    from zoneinfo import ZoneInfo

    from jarvis_kurashift_vendor_list import load_list, save_list, vendor_index, now_iso

    data = load_list()
    by_id = vendor_index(data)
    v = by_id.get(vid)
    if not v:
        return {"ok": False, "error": f"vendor not found: {vid}"}
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date().isoformat()
    v["nurture_last_sent_at"] = today
    if reply is not None:
        v["nurture_last_reply"] = reply
        if reply != "none":
            v["nurture_last_reply_at"] = today
        if reply_note:
            v["nurture_last_reply_note"] = reply_note
    if note:
        prev = str(v.get("notes") or "").strip()
        tag = f"nurture送信 {today}"
        if note:
            tag = f"{tag} | {note}"
        v["notes"] = tag if not prev else f"{prev} | {tag}"
    v["updated_at"] = now_iso()
    if not dry_run:
        save_list(data)
    return {"ok": True, "vendor_id": vid, "nurture_last_sent_at": today, "dry_run": dry_run}


def build_queue_body(
    *,
    rows: list[dict[str, Any]],
    template: dict[str, Any],
    as_of: str,
) -> str:
    subject, sample_body = render_template(
        template,
        vendor_name="{vendor_name}",
        list_region="chubu",
    )
    lines = [
        "[Jarvis] 定期情報確認（nurture）送信キュー",
        f"as_of: {as_of}",
        f"template_id: {template.get('id')}",
        f"approved: {template.get('approved')}",
        f"件数: {len(rows)}（日次上限内）",
        "",
        "## 定型（改変禁止）",
        f"件名: {subject}",
        "",
        "```",
        sample_body.rstrip(),
        "```",
        "",
        "## 対象（1社ずつ Webフォームへ。チャネルが email なら Gmail）",
        "",
    ]
    for r in rows:
        lines.append(f"- id: {r['id']}")
        lines.append(f"  name: {r['name']}")
        lines.append(f"  channel: {r.get('channel') or '-'}")
        lines.append(f"  contact_url: {r.get('contact_url') or '-'}")
        lines.append(f"  contact_email: {r.get('contact_email') or '-'}")
        lines.append(f"  list_region: {r.get('list_region')}")
        lines.append(f"  last_outbound: {r['last_outbound']} ({r['gap_days']}d)")
        lines.append(f"  mark後: --mark {r['id']}")
        lines.append("")
    lines.append("送信後は各社 `--mark ID`（または本スクリプト `--mark ID`）を報告。")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=DEFAULT_CFG)
    ap.add_argument("--dry-run", action="store_true", help="state／YAML／outbox に書かず表示のみ")
    ap.add_argument("--apply", action="store_true", help="state に due 一覧を書く（送信しない）")
    ap.add_argument("--limit", type=int, default=20, help="stdout に出す件数")
    ap.add_argument(
        "--preview",
        action="store_true",
        help="定型文面を表示（例: --preview --vendor-name 〇〇不動産）",
    )
    ap.add_argument("--vendor-name", default="（社名）", help="--preview 用の宛名")
    ap.add_argument("--list-region", default="chubu", help="--preview 用 list_region")
    ap.add_argument("--short", action="store_true", help="--preview で短文版")
    ap.add_argument(
        "--next",
        type=int,
        metavar="N",
        help="次に送る候補 N 件（due 優先。0件なら soon 先頭）",
    )
    ap.add_argument(
        "--queue-outbox",
        action="store_true",
        help="due 先頭を Grok outbox_to_teams/re へ書く（template.approved 必須）",
    )
    ap.add_argument("--mark", metavar="ID", help="nurture_last_sent_at を今日で記録")
    ap.add_argument("--mark-note", default="", help="--mark 時の notes 追記")
    ap.add_argument(
        "--mark-reply",
        choices=("none", "replied", "ignored"),
        default=None,
        help="任意: nurture_last_reply も同時更新",
    )
    ap.add_argument("--mark-reply-note", default="", help="--mark-reply 用メモ")
    args = ap.parse_args()

    if os.environ.get("JARVIS_VENDOR_NURTURE_DISABLE", "").strip() in {"1", "true", "yes"}:
        print("disabled via JARVIS_VENDOR_NURTURE_DISABLE=1")
        return 0

    cfg = _load_yaml(args.config)
    if cfg.get("disabled") is True:
        print("disabled via config disabled: true")
        return 0

    settings = cfg.get("settings") or {}
    template = cfg.get("template") or {}
    if not isinstance(template, dict):
        template = {}
    interval = int(settings.get("interval_days") or 60)
    rel = str(settings.get("list_yaml") or "config/kurashift_re_vendor_list.yaml")
    list_path = (REPO / rel).resolve() if not Path(rel).is_absolute() else Path(rel)
    include = list(settings.get("include_statuses") or ["contacted", "replied"])
    exclude = list(
        settings.get("exclude_statuses")
        or ["skip", "invalid", "pending", "discovered"]
    )
    daily_limit = int(settings.get("daily_send_limit") or 3)

    if args.preview:
        subj, body = render_template(
            template,
            vendor_name=args.vendor_name,
            list_region=args.list_region,
            short=args.short,
        )
        print(f"📎 nurture 定型 preview · id={template.get('id')} · approved={template.get('approved')}")
        print(f"From: {template.get('from_name')} <{template.get('from_email')}>")
        print(f"件名: {subj}")
        print("---")
        print(body.rstrip())
        return 0

    if args.mark:
        res = mark_nurture_sent(
            args.mark,
            note=args.mark_note,
            dry_run=bool(args.dry_run),
            reply=args.mark_reply,
            reply_note=args.mark_reply_note,
        )
        if not res.get("ok"):
            print(res.get("error"), file=sys.stderr)
            return 2
        mode = "dry-run" if res.get("dry_run") else "wrote"
        print(f"📎 nurture mark ({mode}): {res['vendor_id']} → {res['nurture_last_sent_at']}")
        return 0

    if not list_path.is_file():
        print(f"list yaml missing: {list_path}", file=sys.stderr)
        return 2

    result = collect_due(
        list_path=list_path,
        interval_days=interval,
        include_statuses=include,
        exclude_statuses=exclude,
    )
    result["daily_send_limit"] = daily_limit
    result["lane"] = str(settings.get("lane") or "s2")
    result["template_id"] = str(template.get("id") or "")
    result["template_approved"] = bool(template.get("approved"))
    result["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")

    print(
        f"📎 定期情報確認 due — as_of {result['as_of']} · "
        f"interval {interval}d · due {result['due_count']} / "
        f"vendors {result['total_vendors']} · daily_cap {daily_limit} · "
        f"approved={result['template_approved']}"
    )
    for row in result["due"][: max(0, args.limit)]:
        print(
            f"- {row['id']}: {row['name'][:40]} · "
            f"last_out {row['last_outbound']} ({row['gap_days']}d) · "
            f"ch={row.get('channel') or '-'} · reply={row['nurture_last_reply'] or 'none'}"
        )
    if result["due_count"] > args.limit:
        print(f"  …他 {result['due_count'] - args.limit} 件")

    next_n = args.next if args.next is not None else (daily_limit if args.queue_outbox else None)
    if next_n is not None:
        pool = list(result["due"])
        source = "due"
        if not pool:
            pool = list(result.get("soon") or [])
            source = "soon（まだ未due・参考）"
        batch = pool[: max(0, next_n)]
        print(f"📎 next {len(batch)} · source={source}")
        for i, row in enumerate(batch, 1):
            until = row.get("days_until_due")
            until_s = f"until_due={until}d" if until is not None and until > 0 else "DUE"
            print(
                f"  {i}. {row['id']} {row['name'][:36]} · {until_s} · "
                f"last={row['last_outbound']} · {row.get('channel') or '-'}"
            )
            if row.get("contact_url"):
                print(f"     url: {row['contact_url']}")
            if row.get("contact_email"):
                print(f"     email: {row['contact_email']}")

    if args.queue_outbox:
        if not template.get("approved"):
            print(
                "# queue-outbox 中止: template.approved が false。"
                "文面OK後に config/kurashift_vendor_nurture.yaml で true にして再実行",
                file=sys.stderr,
            )
            return 3
        if result["due_count"] == 0:
            print("# queue-outbox: due 0件のためキューなし")
            return 0
        batch = result["due"][:daily_limit]
        body = build_queue_body(
            rows=batch,
            template=template,
            as_of=result["as_of"],
        )
        if args.dry_run:
            print("# dry-run queue-outbox")
            print(body)
            return 0
        from jarvis_bucho_outbox_write import build_md, now_stamp
        from jarvis_bucho_bridge_lib import outbox_dir_for_target, sanitize_title

        day, hm = now_stamp()
        title = f"nurture送信キュー_{len(batch)}社"
        path = outbox_dir_for_target("re") / f"{day}_{hm}_{sanitize_title(title)}.md"
        text = build_md(
            title=title,
            body=body,
            action="s2_batch",
            priority="normal",
            target="re",
        )
        path.write_text(text, encoding="utf-8")
        print(f"📎 nurture queue → {path}")

    if args.apply and not args.dry_run:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        # soon は巨大になりうるので state には due 中心＋soon先頭だけ
        to_store = dict(result)
        to_store["soon"] = (result.get("soon") or [])[:30]
        STATE_PATH.write_text(
            json.dumps(to_store, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"# wrote {STATE_PATH}")
    elif args.dry_run or (not args.apply and not args.queue_outbox and args.next is None):
        if not args.queue_outbox and args.next is None and not args.mark:
            print("# dry-run（state 未更新。書くときは --apply）")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
