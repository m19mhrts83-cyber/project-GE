#!/usr/bin/env python3
"""KURASHIFT Theme helpers: preview + status-based draft proposals.

  python scripts/jarvis_kurashift_theme.py --preview --theme-id UUID
  python scripts/jarvis_kurashift_theme.py --propose-from-status --dry-run
  python scripts/jarvis_kurashift_theme.py --propose-from-status
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def emit_result(obj: dict) -> None:
    print("KURASHIFT_RESULT:" + json.dumps(obj, ensure_ascii=False))


def sb_client() -> Any:
    from supabase import create_client

    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY required")
    return create_client(url, key)


def latest_portfolio(sb: Any) -> list[dict[str, Any]]:
    accounts = {
        r["id"]: r
        for r in (
            sb.table("portfolio_accounts")
            .select("id, name, kind, active")
            .eq("active", True)
            .execute()
            .data
            or []
        )
    }
    snaps = (
        sb.table("portfolio_snapshots")
        .select("account_id, as_of, value_jpy, source")
        .order("as_of", desc=True)
        .limit(80)
        .execute()
        .data
        or []
    )
    latest: dict[str, dict[str, Any]] = {}
    for s in snaps:
        aid = s["account_id"]
        if aid not in latest:
            latest[aid] = {
                **s,
                "name": (accounts.get(aid) or {}).get("name") or aid,
                "kind": (accounts.get(aid) or {}).get("kind"),
            }
    return sorted(
        latest.values(), key=lambda x: float(x.get("value_jpy") or 0), reverse=True
    )


def recent_research(sb: Any, limit: int = 8) -> list[dict[str, Any]]:
    return (
        sb.table("trade_research")
        .select("topic, summary, source, fetched_at")
        .order("fetched_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )


def open_theme_titles(sb: Any) -> set[str]:
    rows = (
        sb.table("kurashift_themes")
        .select("title, status")
        .in_("status", ["draft", "consulting", "approved", "executing"])
        .execute()
        .data
        or []
    )
    return {str(r["title"]) for r in rows}


INDEX_RB_TITLE = "インデックス年1リバランス検討"


def index_rb_proposal(by_id: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    row = by_id.get("sbi_index")
    v = float((row or {}).get("value_jpy") or 0)
    as_of = (row or {}).get("as_of")
    return {
        "title": INDEX_RB_TITLE,
        "hypothesis": (
            f"SBIインデックス評価 {v:,.0f}円。"
            if row
            else "SBIインデックスのスナップ未取得。"
        )
        + "国債比率保持は現状なし。年1回の配分確認を Theme カードとして残す。",
        "amount_jpy": None,
        "duration_note": "年1（Core）",
        "funding_path": "SBI内リバランス（未承認では実行しない）",
        "payload": {
            "layer": "Core",
            "kind": "annual_index_rb",
            "account_id": "sbi_index",
            "as_of": as_of,
            "value_jpy": v if row else None,
        },
    }


def build_proposals(
    portfolio: list[dict[str, Any]],
    research: list[dict[str, Any]],
    *,
    include_index_rb: bool = False,
) -> list[dict[str, Any]]:
    by_id = {p["account_id"]: p for p in portfolio}
    total = sum(float(p.get("value_jpy") or 0) for p in portfolio)
    proposals: list[dict[str, Any]] = []

    if include_index_rb:
        rb = index_rb_proposal(by_id)
        if rb:
            proposals.append(rb)

    # Bloomo sleeve review
    if "bloomo" not in by_id or float((by_id.get("bloomo") or {}).get("value_jpy") or 0) == 0:
        proposals.append(
            {
                "title": "Bloomo 残高取得と固定／動的スリーブ設計",
                "hypothesis": (
                    "Bloomo スナップが未取得または0。"
                    "Web正で残高を取り、固定70–80%／動的20–30%の枠を Theme 化。"
                ),
                "amount_jpy": None,
                "duration_note": "初期セットアップ",
                "funding_path": "Bloomo Web（Playwright Phase2）",
                "payload": {"layer": "Theme", "kind": "bloomo_setup"},
            }
        )
    else:
        bv = float(by_id["bloomo"].get("value_jpy") or 0)
        dyn = round(bv * 0.25)
        proposals.append(
            {
                "title": "Bloomo 動的スリーブの見直し",
                "hypothesis": (
                    f"Bloomo 評価 {bv:,.0f}円。動的枠目安25%≒{dyn:,.0f}円。"
                    "マーケット／ユーザー推移を見て配分変更を提案（承認後完走）。"
                ),
                "amount_jpy": dyn,
                "duration_note": "四半期または材料時",
                "funding_path": "Bloomo 内配分（固定スリーブは触らない）",
                "payload": {
                    "layer": "Theme",
                    "kind": "bloomo_dynamic",
                    "suggested_dynamic_jpy": dyn,
                },
            }
        )

    # Insurance coverage gap
    for aid, title in (
        ("prudential_life", "プルデンシャル生命（真治）の評価登録"),
        ("prudential_life_chikage", "プルデンシャル生命（千景）の評価登録"),
        ("sony_life_chikage", "ソニー生命（千景）の評価確認"),
    ):
        row = by_id.get(aid)
        if row is None or float(row.get("value_jpy") or 0) == 0:
            proposals.append(
                {
                    "title": title,
                    "hypothesis": (
                        "Core 網羅のため名義別評価が必要。手登録または取得スクリプトでスナップを更新。"
                    ),
                    "amount_jpy": None,
                    "duration_note": "一度きり〜月次",
                    "funding_path": "評価登録のみ（売買なし）",
                    "payload": {"layer": "Core", "kind": "insurance_gap", "account_id": aid},
                }
            )

    # Research-driven theme (first distinctive topic)
    seen_topics: set[str] = set()
    for r in research:
        topic = (r.get("topic") or "").strip() or "macro"
        if topic in seen_topics:
            continue
        seen_topics.add(topic)
        summary = (r.get("summary") or "").strip().replace("\n", " ")
        proposals.append(
            {
                "title": f"リサーチ起点: {topic}",
                "hypothesis": (
                    f"{summary[:240]}{'…' if len(summary) > 240 else ''}"
                    if summary
                    else f"分野 {topic} の直近リサーチを Theme 仮説の材料にする。"
                ),
                "amount_jpy": None,
                "duration_note": "要相談（余力と LP を食わない範囲）",
                "funding_path": "未定（相談で経路を決める）",
                "payload": {
                    "layer": "Theme",
                    "kind": "research",
                    "topic": topic,
                    "source": r.get("source"),
                    "fetched_at": r.get("fetched_at"),
                },
            }
        )
        if len(seen_topics) >= 2:
            break

    # Cash-ish surplus hint
    if total > 0:
        proposals.append(
            {
                "title": "資産合計を踏まえた余力の確認",
                "hypothesis": (
                    f"把握済み評価合計 {total:,.0f}円。"
                    "生活防衛・固定積立・α貯蓄を守ったうえで Theme に回せる額を Jarvis と確認。"
                ),
                "amount_jpy": None,
                "duration_note": "提案前チェック",
                "funding_path": "相談レーン",
                "payload": {"layer": "LifePlan", "kind": "surplus_check", "total_jpy": total},
            }
        )

    return proposals


def insert_proposal(sb: Any, p: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    row = {
        "title": p["title"],
        "hypothesis": p["hypothesis"],
        "amount_jpy": p.get("amount_jpy"),
        "duration_note": p.get("duration_note"),
        "funding_path": p.get("funding_path"),
        "status": "draft",
        "payload": {**(p.get("payload") or {}), "proposed_at": now_iso()},
        "updated_at": now_iso(),
    }
    if dry_run:
        return {"dry_run": True, **row}
    res = sb.table("kurashift_themes").insert(row).execute()
    return (res.data or [row])[0]


def propose_from_status(
    *, dry_run: bool, limit: int, include_index_rb: bool
) -> dict[str, Any]:
    sb = sb_client()
    portfolio = latest_portfolio(sb)
    research = recent_research(sb)
    existing = open_theme_titles(sb)
    proposals = build_proposals(
        portfolio, research, include_index_rb=include_index_rb
    )[:limit]
    created: list[dict[str, Any]] = []
    skipped: list[str] = []

    for p in proposals:
        if p["title"] in existing:
            skipped.append(p["title"])
            continue
        created.append(insert_proposal(sb, p, dry_run=dry_run))

    out = {
        "action": "propose_from_status",
        "portfolio_accounts": len(portfolio),
        "research_rows": len(research),
        "include_index_rb": include_index_rb,
        "created": len(created),
        "skipped_existing": skipped,
        "themes": [
            {"id": c.get("id"), "title": c.get("title"), "status": c.get("status")}
            for c in created
        ],
        "dry_run": dry_run,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    emit_result(out)
    return out


def ensure_index_rb(*, dry_run: bool) -> dict[str, Any]:
    sb = sb_client()
    portfolio = latest_portfolio(sb)
    by_id = {p["account_id"]: p for p in portfolio}
    existing = open_theme_titles(sb)
    rb = index_rb_proposal(by_id)
    if rb["title"] in existing:
        out = {
            "action": "ensure_index_rb",
            "created": 0,
            "skipped_existing": [rb["title"]],
            "dry_run": dry_run,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        emit_result(out)
        return out
    created = insert_proposal(sb, rb, dry_run=dry_run)
    out = {
        "action": "ensure_index_rb",
        "created": 1,
        "themes": [{"id": created.get("id"), "title": created.get("title"), "status": created.get("status")}],
        "dry_run": dry_run,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    emit_result(out)
    return out


def preview(theme_id: str, dry_run: bool) -> dict[str, Any]:
    out: dict[str, Any] = {
        "action": "theme_preview",
        "theme_id": theme_id,
        "note": "提案プレビューのみ。実弾・振替は承認ジョブが別途必要。",
        "live": False,
    }
    if theme_id and not dry_run:
        sb = sb_client()
        row = (
            sb.table("kurashift_themes")
            .select("*")
            .eq("id", theme_id)
            .limit(1)
            .execute()
            .data
        )
        out["theme"] = (row or [None])[0]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    emit_result(out)
    return out


def execute_assist(theme_id: str, *, dry_run: bool) -> dict[str, Any]:
    """承認後の完走骨格。実弾は絶対に動かさない（手順メモ＋status更新のみ）。"""
    sb = sb_client()
    rows = (
        sb.table("kurashift_themes")
        .select("*")
        .eq("id", theme_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    theme = rows[0] if rows else None
    if not theme:
        out = {"action": "theme_execute_assist", "error": "theme not found", "theme_id": theme_id}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        emit_result(out)
        return out

    status = theme.get("status")
    if status not in ("approved", "executing"):
        out = {
            "action": "theme_execute_assist",
            "error": f"status must be approved|executing (got {status})",
            "theme_id": theme_id,
            "live": False,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        emit_result(out)
        return out

    payload = theme.get("payload") if isinstance(theme.get("payload"), dict) else {}
    kind = str(payload.get("kind") or "")
    steps: list[dict[str, str]] = []
    if kind == "annual_index_rb":
        steps = [
            {"id": "1", "do": "SBI証券で現行配分（全世界／先進国／国内等）をメモ"},
            {"id": "2", "do": "目標配分との差分を計算（国債比率は維持しない方針）"},
            {"id": "3", "do": "売買プレビューをローカル Jarvis に貼り最終承認"},
            {"id": "4", "do": "承認後のみ手動または専用スクリプトで発注（本ジョブでは発注しない）"},
        ]
    elif kind in ("bloomo_dynamic", "bloomo_setup"):
        steps = [
            {"id": "1", "do": "Bloomo Web で固定／動的スリーブ比率を確認"},
            {"id": "2", "do": "動的枠の変更案をプレビュー（固定スリーブは触らない）"},
            {"id": "3", "do": "OTP／生体が必要なら Messages DB / 端末で完了"},
            {"id": "4", "do": "本ジョブでは自動売買しない。変更後に評価スナップを週次で再取得"},
        ]
    else:
        steps = [
            {"id": "1", "do": f"種別 {kind or 'unknown'} の手順を Jarvis と確認"},
            {"id": "2", "do": "資金経路・金額・期限をレビューノートに残す"},
            {"id": "3", "do": "実弾は別承認後のみ"},
        ]

    note = (
        f"完走アシスト {now_iso()}\n"
        + "\n".join(f"{s['id']}. {s['do']}" for s in steps)
        + "\n※ live=false（自動発注なし）"
    )
    new_payload = {
        **payload,
        "execute_assist_at": now_iso(),
        "execute_steps": steps,
        "live": False,
    }

    if not dry_run:
        sb.table("kurashift_themes").update(
            {
                "status": "executing",
                "review_note": ((theme.get("review_note") or "") + "\n" + note).strip(),
                "payload": new_payload,
                "updated_at": now_iso(),
            }
        ).eq("id", theme_id).execute()

    out = {
        "action": "theme_execute_assist",
        "theme_id": theme_id,
        "kind": kind,
        "steps": steps,
        "status": "executing",
        "live": False,
        "dry_run": dry_run,
        "note": "実弾・振替は行っていません。手順を review_note に追記しました。",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    emit_result(out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--propose-from-status", action="store_true")
    ap.add_argument("--ensure-index-rb", action="store_true")
    ap.add_argument("--execute-assist", action="store_true")
    ap.add_argument("--include-index-rb", action="store_true")
    ap.add_argument("--theme-id", default="")
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.propose_from_status:
        propose_from_status(
            dry_run=args.dry_run,
            limit=args.limit,
            include_index_rb=args.include_index_rb,
        )
        return 0
    if args.ensure_index_rb:
        ensure_index_rb(dry_run=args.dry_run)
        return 0
    if args.execute_assist:
        if not args.theme_id:
            raise SystemExit("--theme-id required for --execute-assist")
        execute_assist(args.theme_id, dry_run=args.dry_run)
        return 0
    if args.preview:
        preview(args.theme_id, args.dry_run)
        return 0
    raise SystemExit(
        "specify --propose-from-status | --ensure-index-rb | --preview | --execute-assist"
    )


if __name__ == "__main__":
    raise SystemExit(main())
