#!/usr/bin/env python3
"""KURASHIFT 物件自動クリーンアップ（候補一覧の鮮度維持・自然流出）。

仕様:
  - 候補一覧（status: info / viewing）から、賞味期限切れの案件を自動で「見送り（passed）」へ退避
  - 理由:
      1. 受付終了 / 商談中（即時退避）
      2. 30日以上未問合せ放置（自然退避）
      3. 14日以上放置 かつ 低スコア (<3.0)（早期退避）
  - 安全保護（絶対に退避しない対象）:
      - 問合せ中・送信済・返信あり（inquiry_status != none）
      - 明示的フォロー中（pursue: true）
      - GrokBot「聞く」判定物件（grok.listen_value == "聞く"）
  - 退避先は status = "passed"（見送りタブに残るため、過去データ・相場参照は100%可能）

実行:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_cleanup.py
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_cleanup.py --apply
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_kurashift_deal_events import insert_deal_event  # noqa: E402
from jarvis_kurashift_re_inquiry import sb_client  # noqa: E402

UKETSUKE_SHURYO_MARKERS = ("※受付終了※", "＊受付終了＊", "*受付終了*", "商談中")

INQUIRY_ACTIVE_STATUSES = frozenset({
    "sending",
    "awaiting_reply",
    "awaiting_grok",
    "has_reply",
    "sent",
})


def is_active_inquiry(deal: dict[str, Any]) -> bool:
    inq = str(deal.get("inquiry_status") or "").strip()
    if not inq:
        sj = deal.get("summary_json") or {}
        if isinstance(sj, dict):
            inq = str(sj.get("inquiry_status") or "").strip()
    return inq in INQUIRY_ACTIVE_STATUSES


def is_grok_listen(deal: dict[str, Any]) -> bool:
    sj = deal.get("summary_json") or {}
    if not isinstance(sj, dict):
        return False
    grok = sj.get("grok") or {}
    if isinstance(grok, dict):
        return str(grok.get("listen_value") or "").strip() == "聞く"
    return False


def is_pursued(deal: dict[str, Any]) -> bool:
    sj = deal.get("summary_json") or {}
    if not isinstance(sj, dict):
        return False
    return bool(sj.get("pursue") or sj.get("user_confirmed"))


def check_cleanup_reason(
    deal: dict[str, Any],
    now: datetime.datetime,
    stale_days: int = 30,
    low_score_days: int = 14,
    low_score_threshold: float = 3.0,
) -> tuple[str | None, str | None]:
    """案件が自動整理対象か判定。(reason_code, reason_label) を返す。"""
    # 安全ガード
    if is_active_inquiry(deal):
        return None, None
    if is_pursued(deal):
        return None, None
    if is_grok_listen(deal):
        return None, None

    title = str(deal.get("title") or "")
    if any(m in title for m in UKETSUKE_SHURYO_MARKERS):
        return "uketsuke_shuryo", "受付終了・商談中"

    dt_str = deal.get("updated_at") or deal.get("created_at")
    age = 999
    if dt_str:
        try:
            dt = datetime.datetime.fromisoformat(str(dt_str).replace("Z", "+00:00"))
            age = (now - dt).days
        except Exception:
            pass

    score = float(deal.get("match_score") or 0.0)

    if age >= stale_days:
        return "stale_30d", f"{stale_days}日経過（自然退避）"

    if age >= low_score_days and score < low_score_threshold:
        return "low_score_14d", f"低スコア({score:.1f}点)・{low_score_days}日経過"

    return None, None


def run_cleanup(
    sb: Any,
    *,
    dry_run: bool = True,
    stale_days: int = 30,
    low_score_days: int = 14,
    low_score_threshold: float = 3.0,
    limit: int = 200,
) -> dict[str, Any]:
    now = datetime.datetime.now(datetime.timezone.utc)
    now_iso = now.isoformat()

    # 対象: 候補一覧に表示される status (info, viewing)
    res = (
        sb.table("kurashift_re_deals")
        .select(
            "id, title, status, inquiry_status, match_score, updated_at, created_at, summary_json"
        )
        .in_("status", ["info", "viewing"])
        .order("match_score", desc=False)
        .limit(500)
        .execute()
    )
    deals = res.data or []

    cleanup_targets: list[tuple[dict[str, Any], str, str]] = []
    reason_counts: dict[str, int] = {}

    for deal in deals:
        reason, label = check_cleanup_reason(
            deal,
            now,
            stale_days=stale_days,
            low_score_days=low_score_days,
            low_score_threshold=low_score_threshold,
        )
        if reason and label:
            cleanup_targets.append((deal, reason, label))
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

    targets_to_process = cleanup_targets[:limit] if limit > 0 else cleanup_targets

    print("📎 KURASHIFT 物件自動整理（クリーンアップ）")
    print(f"- 実行モード: {'[DRY-RUN 試行]' if dry_run else '[APPLY 本番適用]'}")
    print(f"- 候補全件: {len(deals)}件中、整理対象: {len(cleanup_targets)}件 (今回処理: {len(targets_to_process)}件)")
    for r_code, count in reason_counts.items():
        print(f"  · {r_code}: {count}件")

    if targets_to_process:
        print("\n■ 整理対象のサンプル (最大10件):")
        for deal, reason, label in targets_to_process[:10]:
            sc = deal.get("match_score")
            sc_str = f"{sc:.1f}点" if sc is not None else "なし"
            print(f"  · [{reason}] {deal.get('status')} / {sc_str} / {deal.get('title')[:45]}…")

    applied_count = 0
    errors: list[str] = []

    if not dry_run and targets_to_process:
        for deal, reason, label in targets_to_process:
            deal_id = deal["id"]
            prev_status = str(deal.get("status") or "info")
            sj = deal.get("summary_json") or {}
            if not isinstance(sj, dict):
                sj = {}
            else:
                sj = dict(sj)

            sj["pursue_exclude"] = True
            sj["auto_cleanup_at"] = now_iso
            sj["auto_cleanup_reason"] = reason

            try:
                sb.table("kurashift_re_deals").update({
                    "status": "passed",
                    "summary_json": sj,
                    "updated_at": now_iso,
                }).eq("id", deal_id).execute()

                insert_deal_event(
                    sb,
                    deal_id=deal_id,
                    event_type="review_pass",
                    actor="system",
                    from_status=prev_status,
                    to_status="passed",
                    summary=f"自動整理（{label}）",
                    payload={"action": "auto_cleanup", "reason": reason},
                    occurred_at=now_iso,
                )
                applied_count += 1
            except Exception as e:
                errors.append(f"{deal_id}: {e}")

        print(f"\n✅ 整理完了: {applied_count}件を見送り（passed）へ退避しました。")
        if errors:
            print(f"⚠️ エラー件数: {len(errors)}件")

    return {
        "ok": len(errors) == 0,
        "dry_run": dry_run,
        "scanned_deals": len(deals),
        "target_count": len(cleanup_targets),
        "applied_count": applied_count,
        "reason_counts": reason_counts,
        "errors": errors,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="KURASHIFT stale deal auto cleanup")
    ap.add_argument("--apply", action="store_true", help="実際に DB を更新して退避")
    ap.add_argument("--stale-days", type=int, default=30, help="放置日数（既定30日）")
    ap.add_argument("--low-score-days", type=int, default=14, help="低スコア放置日数（既定14日）")
    ap.add_argument("--low-score-threshold", type=float, default=3.0, help="低スコア閾値（既定3.0点）")
    ap.add_argument("--limit", type=int, default=200, help="1回の最大処理件数（既定200件）")
    args = ap.parse_args()

    sb = sb_client()
    res = run_cleanup(
        sb,
        dry_run=not args.apply,
        stale_days=args.stale_days,
        low_score_days=args.low_score_days,
        low_score_threshold=args.low_score_threshold,
        limit=args.limit,
    )
    print("KURASHIFT_RESULT:" + json.dumps(res, ensure_ascii=False))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
