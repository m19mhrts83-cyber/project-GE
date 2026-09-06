#!/usr/bin/env python3
"""KURASHIFT Tier3 — 高スコア自動問合せ（YAML enabled 時のみ実送信）。

正本: config/kurashift_re_inquiry_auto.yaml → tier3_auto_send.enabled
仕様:
  - 1仲介会社1日1通制限 ＆ 最高スコア優先選定（Company Rate Limit）
  - 即死級ネガティブキーワード除外（再建築不可・借地権・事故物件等）
  - 送信間隔ランダムジッター（60-120秒の待機でスパム誤判定を物理回避）
  - 朝刊サマリー自動出力（専用LINE通知 ＆ Jarvis Box outbox_to_teams/re/書込）

既定は dry-run（候補一覧のみ）。実送信は:
  --i-confirm-send かつ YAML enabled: true

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_tier3_auto_send.py
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_tier3_auto_send.py --i-confirm-send
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_kurashift_re_inquiry import (  # noqa: E402
    build_preview,
    sb_client,
    send_inquiry,
)
from jarvis_kurashift_re_inquiry_rules import (  # noqa: E402
    evaluate_inquiry_candidate,
    filter_tier3_by_company_rate_limit,
    find_instant_death_keyword,
    load_config,
    score_of,
)


def _today_sent_count(sb: Any) -> int:
    try:
        r = (
            sb.table("kurashift_re_deals")
            .select("id, inquiry_sent_at, summary_json")
            .in_(
                "inquiry_status",
                ["awaiting_reply", "awaiting_grok", "has_reply", "sending"],
            )
            .limit(500)
            .execute()
        )
    except Exception:
        return 0
    today = date.today().isoformat()
    n = 0
    for d in r.data or []:
        sent = d.get("inquiry_sent_at")
        if not sent:
            sj = d.get("summary_json") if isinstance(d.get("summary_json"), dict) else {}
            sent = sj.get("inquiry_sent_at")
        if sent and str(sent)[:10] == today:
            n += 1
    return n


def list_tier3_candidates(
    sb: Any, cfg: dict[str, Any]
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    r = (
        sb.table("kurashift_re_deals")
        .select("*")
        .in_("status", ["info", "viewing", "passed"])
        .limit(300)
        .execute()
    )
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for deal in r.data or []:
        # 即死キーワードを二重防御
        if find_instant_death_keyword(deal, cfg):
            continue
        ev = evaluate_inquiry_candidate(deal, cfg)
        if ev.get("tier3_eligible") or ev.get("tier3"):
            out.append((deal, ev))
    return out


def send_line_notification(text: str) -> bool:
    """松野様専用LINEへプッシュ通知（設定されている場合）。"""
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    to_id = (
        os.environ.get("LINE_TO_USER_ID", "").strip()
        or os.environ.get("LINE_TO_GROUP_ID", "").strip()
    )
    if not token or not to_id:
        return False
    payload = json.dumps(
        {"to": to_id, "messages": [{"type": "text", "text": text[:5000]}]},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.line.me/v2/bot/message/push",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.getcode() < 300
    except Exception as e:
        print(f"  [LINE通知送信エラー]: {e}")
        return False


def write_jarvis_box_report(title: str, body: str) -> bool:
    """Jarvis Box (admin Drive 【with Grok bot】/outbox_to_teams/re/) へ朝刊MDを配置。"""
    try:
        from jarvis_bucho_bridge_lib import outbox_dir_for_target

        outbox = outbox_dir_for_target("re")
        if outbox and outbox.is_dir():
            today_str = date.today().isoformat()
            filename = f"{today_str}_朝刊_第一問合せ実績.md"
            target_file = outbox / filename
            content = (
                f"# Jarvis → Grok (不動産チーム)\n"
                f"target: re\n"
                f"priority: normal\n"
                f"action: memo\n"
                f"title: {title}\n"
                f"---\n"
                f"{body}\n"
            )
            target_file.write_text(content, encoding="utf-8")
            print(f"  [Jarvis Box書込完了]: {target_file}")
            return True
    except Exception as e:
        # GitHub Actions環境などDriveマウントが無い場合はスキップしてログ出力
        print(f"  [Jarvis Box書込スキップ (ローカルDrive非マウント等)]: {e}")
    return False


def build_morning_report(
    *,
    today_str: str,
    sent_items: list[dict[str, Any]],
    skipped_by_company: list[dict[str, Any]],
    daily_cap: int,
    already_sent: int,
    is_dry_run: bool,
) -> str:
    status_header = "【試行・確認】" if is_dry_run else "【完了】"
    lines = [
        f"☀️ 【KURASHIFT 朝刊】第一問合せ自動送信レポート {status_header}",
        f"日付: {today_str}",
        f"送信実績: {len(sent_items)}件（本日累計: {already_sent + len(sent_items)}/{daily_cap}件）",
        "",
        "■ 本日自動送信した案件:",
    ]
    if sent_items:
        for idx, item in enumerate(sent_items, 1):
            lines.append(
                f"{idx}. [{item.get('score')}点] {item.get('title')[:35]}… "
                f"→ 宛先: {item.get('to')}"
            )
    else:
        lines.append("（本日の自動送信対象はありませんでした）")

    if skipped_by_company:
        lines.append("")
        lines.append(f"■ 1社1通制限で保留（同一業者の最高スコアを優先）: {len(skipped_by_company)}件")
        for s in skipped_by_company[:5]:
            lines.append(f"  · [{s.get('score')}点] {str(s.get('title'))[:30]}…")

    lines.extend([
        "",
        "■ 次のアクション:",
        "夕方18:00に業者から届いた資料・番地情報をもとに、GrokBot（S1/S5/S3/S7）がハザード・路線価・ペルソナ詳細調査を自動実行します。",
    ])
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Tier3 auto inquiry (gated by YAML)")
    ap.add_argument(
        "--i-confirm-send",
        action="store_true",
        help="YAML enabled のときだけ実送信",
    )
    ap.add_argument("--limit", type=int, default=0, help="送信上限（0=日次 cap 残り）")
    ap.add_argument(
        "--dry-run-send",
        action="store_true",
        help="enabled 時も send_inquiry(dry_run=True) で止める",
    )
    ap.add_argument(
        "--no-jitter",
        action="store_true",
        help="送信間隔ジッター（待機）を無効化",
    )
    ap.add_argument(
        "--jitter-min",
        type=int,
        default=0,
        help="ジッター最小秒数（指定無き場合はYAML設定）",
    )
    ap.add_argument(
        "--jitter-max",
        type=int,
        default=0,
        help="ジッター最大秒数（指定無き場合はYAML設定）",
    )
    args = ap.parse_args()

    cfg = load_config()
    t3_cfg = cfg.get("tier3_auto_send") or {}
    enabled = bool(t3_cfg.get("enabled"))
    daily_cap = int(cfg.get("daily_send_cap") or 5)

    jitter_cfg = t3_cfg.get("anti_spam_jitter") or {}
    jitter_min = args.jitter_min if args.jitter_min > 0 else int(jitter_cfg.get("min_seconds", 60))
    jitter_max = args.jitter_max if args.jitter_max > 0 else int(jitter_cfg.get("max_seconds", 120))
    if jitter_max < jitter_min:
        jitter_max = jitter_min

    sb = sb_client()
    raw_candidates = list_tier3_candidates(sb, cfg)
    # 1社1通制限・最高スコア優先選定
    accepted_candidates, skipped_by_company = filter_tier3_by_company_rate_limit(
        raw_candidates, cfg
    )

    already = _today_sent_count(sb)
    remain = max(0, daily_cap - already)
    limit = args.limit if args.limit > 0 else remain
    will_try_count = min(limit, len(accepted_candidates))

    print("📎 KURASHIFT Tier3 安全自動送信（クラウド自走版）")
    print(f"- YAML enabled: {enabled}")
    print(f"- daily_cap: {daily_cap} / 本日送信済: {already} / 残り枠: {remain}")
    print(f"- 候補全件: {len(raw_candidates)}件 → 1社1通フィルタ後: {len(accepted_candidates)}件 (同社保留: {len(skipped_by_company)}件)")
    print(f"- 今回送信予定: {will_try_count}件 (ジッター設定: {jitter_min}〜{jitter_max}秒)")

    for deal, ev in accepted_candidates[:10]:
        print(
            f"  · [スコア={score_of(deal):.1f}] {(deal.get('title') or '')[:50]} "
            f"badges={ev.get('badges')}"
        )

    if not args.i_confirm_send:
        print("\n[Dry-Run プレビュー完了] 送信するには --i-confirm-send を指定してください。")
        print(
            "KURASHIFT_RESULT:"
            + json.dumps(
                {
                    "enabled": enabled,
                    "candidates": len(accepted_candidates),
                    "skipped_by_company": len(skipped_by_company),
                    "dry_run": True,
                },
                ensure_ascii=False,
            )
        )
        return 0

    if not enabled:
        print(
            "❌ tier3_auto_send.enabled が false です。"
            "config/kurashift_re_inquiry_auto.yaml を確認してください。"
        )
        return 2

    sent_items: list[dict[str, Any]] = []
    sent_count = 0
    skipped_count = 0
    errors_count = 0

    targets = accepted_candidates[:limit]
    for idx, (deal, ev) in enumerate(targets):
        deal_id = str(deal["id"])
        deal_title = str(deal.get("title") or deal_id)
        score = score_of(deal)

        try:
            prev = build_preview(deal)
        except Exception as e:
            print(f"  [プレビュー作成失敗] {deal_title[:40]}: {e}")
            errors_count += 1
            continue

        to_email = (prev.get("to") or "").strip()
        channel = prev.get("inquiry_channel") or ev.get("inquiry_channel")
        if not to_email or "@" not in to_email:
            print(f"  [宛先なしスキップ] {deal_title[:40]}")
            skipped_count += 1
            continue

        dry = bool(args.dry_run_send)
        r = send_inquiry(
            sb,
            deal_id,
            to_email=to_email,
            subject=None,
            body=None,
            confirm=True,
            dry_run=dry,
            inquiry_channel=str(channel) if channel else None,
        )

        if r.get("ok"):
            if r.get("skipped"):
                skipped_count += 1
                print(f"  [送信スキップ] {r.get('skipped')}: {deal_title[:40]}")
            else:
                sent_count += 1
                mode = "dry" if dry else "sent"
                print(f"  ✅ [{mode}] {deal_title[:40]} → {to_email}")
                sent_items.append({
                    "id": deal_id,
                    "title": deal_title,
                    "score": score,
                    "to": to_email,
                    "channel": channel,
                })

                # スパム防止ランダムジッター（次がある場合のみ）
                if not dry and not args.no_jitter and idx < len(targets) - 1:
                    sleep_sec = random.randint(jitter_min, jitter_max)
                    print(f"  ⏳ [スパム防止待機] 次の送信まで {sleep_sec} 秒待機中...")
                    time.sleep(sleep_sec)
        else:
            errors_count += 1
            print(f"  ❌ [送信失敗] {r.get('error')}: {deal_title[:40]}")

    # 朝刊レポート生成
    today_str = date.today().isoformat()
    report_text = build_morning_report(
        today_str=today_str,
        sent_items=sent_items,
        skipped_by_company=skipped_by_company,
        daily_cap=daily_cap,
        already_sent=already,
        is_dry_run=bool(args.dry_run_send),
    )

    print("\n" + "=" * 50)
    print(report_text)
    print("=" * 50 + "\n")

    # LINE通知 ＆ Jarvis Box出力
    line_ok = send_line_notification(report_text)
    if line_ok:
        print("  📱 [LINE通知]: 送信成功")
    box_ok = write_jarvis_box_report(
        title=f"朝刊_第一問合せ実績_{today_str}",
        body=report_text,
    )

    print(
        "KURASHIFT_RESULT:"
        + json.dumps(
            {
                "enabled": enabled,
                "sent": sent_count,
                "skipped": skipped_count,
                "skipped_by_company": len(skipped_by_company),
                "errors": errors_count,
                "line_notified": line_ok,
                "box_written": box_ok,
            },
            ensure_ascii=False,
        )
    )
    return 0 if errors_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
