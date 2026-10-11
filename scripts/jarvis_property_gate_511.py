#!/usr/bin/env python3
"""511 問合せ送信準備係 — Slack Yes/No 後の送信／見送り。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_property_gate_511.py --deal-id UUID --yes
  ~/selenium_env/venv/bin/python scripts/jarvis_property_gate_511.py --deal-id UUID --no
  ~/selenium_env/venv/bin/python scripts/jarvis_property_gate_511.py --deal-id UUID --yes --dry-run
  # 直接送信（ジョブ経由ではなく Mac 上で re_inquiry）
  ~/selenium_env/venv/bin/python scripts/jarvis_property_gate_511.py --deal-id UUID --yes --direct

正本: docs/AIエージェントチーム/23_物件進行ゲート_Grok調査_20261012.md
B の Yes ＝対外送信了承（追加のチャット確認なし）。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_property_gate_lib import (  # noqa: E402
    JST,
    enqueue_inquiry_job,
    heal_handoff_status,
    load_state,
    mark_deal_state,
    mark_skip_no,
    now_iso,
    post_slack,
    py,
    save_state,
    sb_client,
)

LOG_DIR = (
    REPO
    / "docs"
    / "AIエージェントチーム"
    / "500_不動産パイプライン実行室"
    / "511_問合せ送信準備係"
    / "logs"
)


def _log(msg: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"{stamp}_gate511.md"
    path.write_text(f"# 511 {stamp}\n\n{msg}\n", encoding="utf-8")
    return path


def direct_send(deal_id: str, *, dry_run: bool) -> dict:
    cmd = [
        py(),
        str(REPO / "scripts" / "jarvis_kurashift_re_inquiry.py"),
        "--send-deal-id",
        deal_id,
    ]
    if dry_run:
        cmd.append("--dry-run")
    else:
        cmd.append("--i-confirm-send")
    r = subprocess.run(
        cmd,
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        timeout=180,
    )
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    return {"ok": r.returncode == 0, "code": r.returncode, "out": out}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--deal-id", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--yes", action="store_true", help="問合せ送信（了承）")
    g.add_argument("--no", action="store_true", help="見送り")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--direct",
        action="store_true",
        help="ジョブを積まず Mac 上で re_inquiry を直接実行",
    )
    ap.add_argument("--no-slack", action="store_true")
    args = ap.parse_args()

    if (os.environ.get("JARVIS_PROPERTY_GATE_DISABLE") or "").strip() == "1":
        print("property_gate disabled")
        return 0

    sb = sb_client()
    from jarvis_kurashift_re_inquiry import get_deal

    deal = get_deal(sb, args.deal_id)
    healed = heal_handoff_status(sb, deal)
    if healed:
        deal = healed

    st = load_state()
    prev = (st.get("deals") or {}).get(args.deal_id) or {}
    if prev.get("decision") in ("yes", "sent") and args.yes and not args.dry_run:
        msg = f"冪等スキップ: 既に Yes/送信済 deal={args.deal_id}"
        print(msg)
        print(f"KURASHIFT_RESULT:{json.dumps({'ok': True, 'skipped': 'already_yes'}, ensure_ascii=False)}")
        return 0
    if prev.get("decision") == "no" and args.no and not args.dry_run:
        print(f"冪等スキップ: 既に No deal={args.deal_id}")
        return 0

    if args.no:
        if args.dry_run:
            result = {"ok": True, "dry_run": True, "decision": "no"}
        else:
            result = mark_skip_no(sb, deal, source="gate_511_cli")
            mark_deal_state(st, args.deal_id, decision="no", lane="C")
            save_state(st)
        text = (
            f"【物件進行ゲート】No 見送り — {str(deal.get('title') or '')[:50]}\n"
            f"deal_id=`{args.deal_id}`"
        )
        if not args.no_slack:
            post_slack("consult", text, dry_run=args.dry_run)
        path = _log(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"📎 {path}")
        print(f"KURASHIFT_RESULT:{json.dumps(result, ensure_ascii=False)}")
        return 0 if result.get("ok") else 1

    # Yes
    if args.direct:
        result = direct_send(args.deal_id, dry_run=args.dry_run)
        source = "gate_511_direct"
    else:
        result = enqueue_inquiry_job(
            sb, deal, source="gate_511_cli", dry_run=args.dry_run
        )
        source = "gate_511_enqueue"

    if result.get("ok") and not args.dry_run and not result.get("skipped"):
        mark_deal_state(
            st,
            args.deal_id,
            decision="yes" if not args.direct else "sent",
            job_id=result.get("job_id"),
            source=source,
            at=now_iso(),
        )
        save_state(st)

    title = str(deal.get("title") or "")[:50]
    if result.get("ok"):
        if result.get("skipped"):
            text = (
                f"【物件進行ゲート】Yes 処理スキップ ({result.get('skipped')}) — "
                f"{title}\ndeal_id=`{args.deal_id}`"
            )
        elif args.dry_run:
            text = f"【物件進行ゲート】Yes dry-run — {title}\ndeal_id=`{args.deal_id}`"
        else:
            text = (
                f"【物件進行ゲート】Yes → 送信キュー — {title}\n"
                f"deal_id=`{args.deal_id}` job=`{result.get('job_id') or 'direct'}`"
            )
    else:
        err = result.get("error") or result.get("out") or "fail"
        text = (
            f"【物件進行ゲート】Yes 失敗 — {title}\n"
            f"deal_id=`{args.deal_id}`\n{str(err)[:400]}"
        )
    if not args.no_slack:
        post_slack("consult", text, dry_run=args.dry_run)

    path = _log(json.dumps({"result": result, "out": result.get("out")}, ensure_ascii=False, indent=2)[:4000])
    print(f"📎 {path}")
    print(f"KURASHIFT_RESULT:{json.dumps({k: v for k, v in result.items() if k != 'out'}, ensure_ascii=False)}")
    if result.get("out"):
        print(result["out"][-1500:])
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
