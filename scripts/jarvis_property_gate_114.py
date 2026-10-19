#!/usr/bin/env python3
"""114 物件一次判定係 — Grok調査後の進行ゲート（A/B/C）＋ Slack。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_property_gate_114.py --scan
  ~/selenium_env/venv/bin/python scripts/jarvis_property_gate_114.py --scan --post
  ~/selenium_env/venv/bin/python scripts/jarvis_property_gate_114.py --deal-id UUID --post
  ~/selenium_env/venv/bin/python scripts/jarvis_property_gate_114.py --heal-handoff

正本: docs/AIエージェントチーム/23_物件進行ゲート_Grok調査_20261012.md
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_property_gate_lib import (  # noqa: E402
    JST,
    already_gated,
    classify_lane,
    fetch_gate_candidates,
    format_a_line,
    b_card_blocks,
    format_b_card,
    prefer_url_buttons,
    format_c_digest,
    heal_handoff_status,
    load_state,
    mark_deal_state,
    now_iso,
    now_jst_date,
    post_slack,
    save_state,
    sb_client,
)

LOG_DIR = (
    REPO
    / "docs"
    / "AIエージェントチーム"
    / "100_連絡・物件動向把握室"
    / "114_物件一次判定係"
    / "logs"
)


def _write_log(rows: list[dict]) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"{stamp}_gate114.md"
    lines = [f"# 114 進行ゲート {stamp}", ""]
    for r in rows:
        lines.append(
            f"- lane={r.get('lane')} deal=`{r.get('deal_id')}` "
            f"{r.get('title', '')[:40]} — {r.get('reason')}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def process_deal(
    sb,
    deal: dict,
    *,
    st: dict,
    post: bool,
    dry_run: bool,
    force: bool,
    run_a511: bool,
    post_b: bool = True,
) -> dict:
    healed = heal_handoff_status(sb, deal)
    if healed:
        deal = healed
    lane = classify_lane(deal)
    deal_id = str(deal["id"])
    title = str(deal.get("title") or "")
    out = {
        "deal_id": deal_id,
        "title": title,
        "lane": lane["lane"],
        "reason": lane.get("reason"),
        "listen": lane.get("listen"),
        "inquiry_action": lane.get("inquiry_action"),
        "inquiry_status": lane.get("inquiry_status"),
    }
    if already_gated(st, deal_id, lane["lane"], deal=deal) and not force:
        out["skipped"] = "already_gated"
        return out

    if lane["lane"] == "B":
        url_mode = prefer_url_buttons()
        text = format_b_card(deal, lane, include_action_links=url_mode)
        blocks = b_card_blocks(deal, lane, url_mode=url_mode)
        if post and post_b:
            pr = post_slack(
                "consult",
                text,
                dry_run=dry_run,
                username="114 物件一次判定",
                blocks=blocks,
            )
            out["slack"] = pr
            if pr.get("ok") and not dry_run:
                mark_deal_state(
                    st,
                    deal_id,
                    deal=deal,
                    lane="B",
                    b_card_posted_at=now_iso(),
                    reason=lane.get("reason"),
                )
                # 並列実行の再掲防止: 1件ごとに state を即保存
                from jarvis_property_gate_lib import save_state

                save_state(st)
        elif post and not post_b:
            # 上限で今回出せない分は「保留」として記録（リマインドが拾う）
            out["deferred"] = True
            if not dry_run:
                mark_deal_state(
                    st,
                    deal_id,
                    deal=deal,
                    lane="B",
                    b_deferred_at=now_iso(),
                    reason=lane.get("reason"),
                )
                from jarvis_property_gate_lib import save_state

                save_state(st)
        else:
            out["preview"] = text
        return out

    if lane["lane"] == "A":
        text = format_a_line(deal, lane)
        if post:
            pr = post_slack("report", text, dry_run=dry_run)
            out["slack"] = pr
        else:
            out["preview"] = text
        if run_a511 and lane.get("auto_send"):
            from jarvis_property_gate_lib import enqueue_inquiry_job

            jr = enqueue_inquiry_job(
                sb, deal, source="gate_114_auto_a", dry_run=dry_run
            )
            out["enqueue"] = jr
        if post and not dry_run:
            mark_deal_state(
                st,
                deal_id,
                deal=deal,
                lane="A",
                a_done_at=now_iso(),
                reason=lane.get("reason"),
            )
            from jarvis_property_gate_lib import save_state

            save_state(st)
        return out

    # C — digest later
    out["_c_pair"] = (deal, lane)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scan", action="store_true", help="候補 deals を走査")
    ap.add_argument("--deal-id", default="", help="1件指定")
    ap.add_argument("--post", action="store_true", help="Slack 投稿")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="既投稿でも再掲")
    ap.add_argument(
        "--auto-a-send",
        action="store_true",
        help="Aレーンで Tier3+To ありなら送信ジョブを積む",
    )
    ap.add_argument(
        "--heal-handoff",
        action="store_true",
        help="awaiting_grok 誤ラベルを awaiting_first_inquiry へ一括修復",
    )
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument(
        "--max-b",
        type=int,
        default=5,
        help="1回で出す Bカードの上限（超過分は保留として記録し翌回へ）",
    )
    ap.add_argument(
        "--c-list",
        action="store_true",
        help="C を件数サマリではなくタイトル羅列（旧挙動。通常は使わない）",
    )
    args = ap.parse_args()

    if os_disabled():
        print("property_gate disabled")
        return 0

    sb = sb_client()
    st = load_state()

    if args.heal_handoff:
        n = 0
        for deal in fetch_gate_candidates(sb, limit=args.limit):
            h = heal_handoff_status(sb, deal)
            if h:
                n += 1
                print(f"healed {deal.get('id')} → awaiting_first_inquiry")
        print(f"📎 heal-handoff: {n}件")
        return 0

    deals: list[dict] = []
    if args.deal_id:
        from jarvis_kurashift_re_inquiry import get_deal

        deals = [get_deal(sb, args.deal_id)]
    elif args.scan:
        deals = fetch_gate_candidates(sb, limit=args.limit)
    else:
        ap.print_help()
        return 2

    results: list[dict] = []
    c_pairs: list = []
    b_posted = 0
    for deal in deals:
        r = process_deal(
            sb,
            deal,
            st=st,
            post=args.post,
            dry_run=args.dry_run,
            force=args.force,
            run_a511=args.auto_a_send,
            post_b=b_posted < args.max_b,
        )
        if (r.get("slack") or {}).get("ok"):
            b_posted += 1
        if "_c_pair" in r:
            c_pairs.append(r.pop("_c_pair"))
            r["lane"] = "C"
        results.append(r)
        extra = ""
        if r.get("skipped"):
            extra += f" skipped={r['skipped']}"
        if r.get("deferred"):
            extra += " deferred=1"
        if r.get("slack"):
            extra += f" slack_ok={r['slack'].get('ok')}"
        print(
            f"lane={r.get('lane')} {r.get('deal_id')} "
            f"{(r.get('title') or '')[:40]} — {r.get('reason')}{extra}"
        )

    # C ダイジェスト（1日1通）
    if c_pairs and args.post:
        if st.get("digest_c_date") == now_jst_date() and not args.force:
            print("C digest: already posted today")
        else:
            text = format_c_digest(c_pairs, detail=bool(args.c_list))
            pr = post_slack("report", text, dry_run=args.dry_run)
            print(f"C digest: {pr}")
            if pr.get("ok") and not args.dry_run:
                st["digest_c_date"] = now_jst_date()
                for deal, lane in c_pairs:
                    mark_deal_state(
                        st,
                        str(deal["id"]),
                        deal=deal,
                        lane="C",
                        c_digested_at=now_iso(),
                        reason=lane.get("reason"),
                    )

    if not args.dry_run:
        save_state(st)
    log_path = _write_log(results)
    print(f"📎 log: {log_path}")
    print(
        "KURASHIFT_RESULT:"
        + json.dumps(
            {
                "ok": True,
                "count": len(results),
                "lanes": {
                    "A": sum(1 for r in results if r.get("lane") == "A"),
                    "B": sum(1 for r in results if r.get("lane") == "B"),
                    "C": sum(1 for r in results if r.get("lane") == "C"),
                },
                "b_posted": b_posted,
                "b_deferred": sum(1 for r in results if r.get("deferred")),
            },
            ensure_ascii=False,
        )
    )
    return 0


def os_disabled() -> bool:
    import os

    if (os.environ.get("JARVIS_PROPERTY_GATE_DISABLE") or "").strip() == "1":
        return True
    st = load_state()
    return bool(st.get("disabled"))


if __name__ == "__main__":
    raise SystemExit(main())
