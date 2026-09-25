#!/usr/bin/env python3
"""KURASHIFT 株式ウォッチ — 発注前プレビュー＋対外確認ゲート。

Phase2 の入口。**実発注はしない**。プレビューを作り、オーナー確認（Todoist
Theme株式）を経て、手動発注アシスト手順を出すだけ。立花API自動発注は
config の `order.live_api` が true になるまで実装しない（このスクリプトは
ブローカー API を一切呼ばない）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a

  # 1) プレビュー作成（承認待ち。アプリのボタン／CLI どちらでも）
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_stock_order.py --preview --symbol 8035.T

  # 2) オーナーが Todoist Theme株式で内容を確認したあとだけ確定（対外確認ゲート）
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_stock_order.py \
    --confirm <ORDER_ID> --i-confirm-order

  # 3) 取り消し・一覧
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_stock_order.py --cancel <ORDER_ID>
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_stock_order.py --list

`--i-confirm-order` はオーナー確認済みの表明。GHA / Mac worker は付けない
（アプリからキューできるのは preview まで）。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from jarvis_trade_common import sb_client
from jarvis_kurashift_stock_watch import (
    compute_levels,
    eval_symbol,
    kurashift_urls,
    load_config,
    load_state,
    now_iso,
    save_state,
    todoist_comment,
    todoist_create,
)

REPO = Path(__file__).resolve().parents[1]
ORDER_MODE = "live"
OPEN_STATUSES = ("preview", "confirmed")


class GuardError(RuntimeError):
    """必須ガードに落ちた。プレビュー/確定を中断する。"""


def _cfg() -> dict[str, Any]:
    return load_config()


def _order_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    return dict(cfg.get("order") or {})


def watch_for_symbol(state: dict[str, Any], symbol: str) -> dict[str, Any]:
    sym = (symbol or "").strip().upper()
    watch = (state.get("watches") or {}).get(sym)
    if not watch:
        # .T 有無の揺れを吸収
        alt = sym + ".T" if not sym.endswith(".T") else sym[:-2]
        watch = (state.get("watches") or {}).get(alt)
        sym = alt if watch else sym
    if not watch:
        raise GuardError(f"監視対象ではありません: {symbol}（Theme承認で監視ONにしてください）")
    if not watch.get("active", True):
        raise GuardError(
            f"監視OFFの銘柄です: {sym}（Theme 承認後に --activate-theme で ON）"
        )
    return watch


def existing_open_orders(sb: Any, symbol: str | None = None) -> list[dict[str, Any]]:
    q = (
        sb.table("trade_orders")
        .select("id,symbol,side,qty,limit_price,status,payload,created_at")
        .eq("mode", ORDER_MODE)
        .in_("status", list(OPEN_STATUSES))
    )
    if symbol:
        q = q.eq("symbol", symbol)
    res = q.order("created_at", desc=True).limit(50).execute()
    return list(res.data or [])


def committed_amount_jpy(sb: Any) -> float:
    total = 0.0
    for o in existing_open_orders(sb):
        p = o.get("payload") or {}
        total += float(p.get("amount_jpy") or 0)
    return total


def kill_switch_on(sb: Any) -> bool:
    try:
        res = (
            sb.table("trade_risk_state")
            .select("kill_switch,kill_reason")
            .eq("id", ORDER_MODE)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return bool(rows and rows[0].get("kill_switch"))
    except Exception:
        return False


def jp_tick_size(price: float) -> float:
    """東証の呼値単位（株式・ETF 共通の概略）。"""
    if price <= 3000:
        return 1.0
    if price <= 5000:
        return 5.0
    if price <= 30000:
        return 10.0
    if price <= 100000:
        return 50.0
    if price <= 300000:
        return 100.0
    if price <= 1000000:
        return 1000.0
    if price <= 3000000:
        return 5000.0
    if price <= 10000000:
        return 10000.0
    return 50000.0


def tick_round(price: float, *, up: bool) -> float:
    tick = jp_tick_size(price)
    steps = price / tick
    n = math.ceil(steps) if up else math.floor(steps)
    return round(n * tick, 4)


def signals_of(watch: dict[str, Any], levels: dict[str, Any], thr: dict[str, Any]) -> list[dict[str, Any]]:
    return eval_symbol(deepcopy(watch), levels, thr)


def resolve_side(signals: list[dict[str, Any]], requested: str, oc: dict[str, Any]) -> str:
    kinds = {s["kind"] for s in signals}
    buy_kinds = set(oc.get("buy_signal_kinds") or ["near_bottom", "upside_ready"])
    sell_kinds = set(oc.get("sell_signal_kinds") or ["sell_signal"])
    side = (requested or "").strip().lower() or ("buy" if kinds & buy_kinds else "sell")
    if side == "buy" and not (kinds & buy_kinds):
        raise GuardError(f"買いサインがありません（signals={sorted(kinds) or 'なし'}）")
    if side == "sell" and not (kinds & sell_kinds):
        raise GuardError(f"売りサインがありません（signals={sorted(kinds) or 'なし'}）")
    if side not in ("buy", "sell"):
        raise GuardError(f"side が不正です: {requested}")
    return side


def build_preview(
    *,
    state: dict[str, Any],
    sb: Any,
    cfg: dict[str, Any],
    symbol: str,
    requested_side: str,
    qty_arg: int | None,
) -> dict[str, Any]:
    oc = _order_cfg(cfg)
    if not oc.get("enabled", True):
        raise GuardError("発注プレビューは config order.enabled=false で停止中です")
    thr = cfg.get("thresholds") or {}
    watch = watch_for_symbol(state, symbol)
    sym = watch.get("symbol") or symbol
    core = {str(s).upper() for s in (oc.get("core_symbols") or [])}
    if sym.upper() in core:
        raise GuardError(f"NISAコア相当のため対象外です: {sym}")

    levels = compute_levels(_closes(sb, sym), thr)
    if not levels:
        raise GuardError(f"日足不足でプレビューできません: {sym}")
    sigs = signals_of(watch, levels, thr)
    side = resolve_side(sigs, requested_side, oc)

    unit = int(oc.get("min_unit") or 100)
    buffer_pct = float(oc.get("limit_buffer_pct") or 0.0) / 100.0
    close = float(levels["close"])
    if side == "buy":
        limit = tick_round(close * (1.0 + buffer_pct), up=True)
    else:
        limit = tick_round(close * (1.0 - buffer_pct), up=False)
    if limit <= 0:
        raise GuardError("指値が算出できません")

    per_name = float(oc.get("per_name_max_jpy") or 0)
    total_cap = float(oc.get("total_capital_jpy") or 0)

    odd_lot = False
    guards_extra: dict[str, Any] | None = None
    if side == "buy":
        committed_name = sum(
            float((o.get("payload") or {}).get("amount_jpy") or 0)
            for o in existing_open_orders(sb, sym)
        )
        budget = min(per_name - committed_name, total_cap - committed_amount_jpy(sb))
        allow_odd = bool(oc.get("allow_odd_lots", True))
        if qty_arg:
            qty = int(qty_arg)
            if qty % unit != 0:
                if not allow_odd:
                    raise GuardError(f"買い数量は{unit}株単位で指定してください: {qty}")
                odd_lot = True
        elif budget >= limit * unit:
            qty = int(budget // (limit * unit)) * unit
        elif allow_odd:
            qty = int(budget // limit)
            odd_lot = qty > 0
        else:
            qty = 0
        if qty <= 0:
            raise GuardError(
                f"予算が1株にも足りません（残枠{budget:,.0f}円 / 1単元{limit * unit:,.0f}円）"
            )
        if odd_lot:
            guards_extra = {
                "code": "odd_lot",
                "ok": True,
                "detail": "単元未満（かぶミニ等）。指値可否を立花で確認",
            }
    else:
        if not qty_arg:
            raise GuardError("売りは --qty で数量指定が必要です（保有数量は手動確認）")
        qty = int(qty_arg)
        if qty <= 0:
            raise GuardError("数量が不正です")

    amount = qty * limit
    if side == "buy":
        if amount > per_name:
            raise GuardError(f"1銘柄上限 {per_name:,.0f}円 を超えます（{amount:,.0f}円）")
        if committed_amount_jpy(sb) + amount > total_cap:
            raise GuardError(f"運用枠 {total_cap:,.0f}円 を超えます")
    if existing_open_orders(sb, sym):
        raise GuardError(f"未確定の注文プレビューが既にあります: {sym}（二重発注防止）")
    if kill_switch_on(sb):
        raise GuardError("kill_switch が ON です（新規建て停止中）")

    guards = [
        {"code": "order_enabled", "ok": True, "detail": "プレビュー機能有効"},
        {"code": "watch_active", "ok": True, "detail": watch.get("theme_title") or sym},
        {"code": "not_core", "ok": True, "detail": "NISAコア対象外"},
        {"code": "signal_present", "ok": True, "detail": ",".join(sorted({s["kind"] for s in sigs}))},
        {"code": "budget_ok", "ok": True, "detail": f"{qty}×{limit:,.0f}={amount:,.0f}円"},
        {"code": "no_open_order", "ok": True, "detail": "重複なし"},
        {"code": "kill_switch_off", "ok": True, "detail": "停止していない"},
    ]
    if guards_extra:
        guards.append(guards_extra)

    return {
        "kind": "stock_order_preview",
        "phase": "preview",
        "symbol": sym,
        "name": watch.get("name") or sym,
        "theme_id": watch.get("theme_id"),
        "theme_title": watch.get("theme_title"),
        "side": side,
        "qty": qty,
        "unit": unit,
        "odd_lot": odd_lot,
        "limit_price": limit,
        "close": close,
        "trade_date": levels.get("trade_date"),
        "amount_jpy": amount,
        "bottom_hint": watch.get("bottom_hint") or levels.get("bottom_hint"),
        "signals": [s["kind"] for s in sigs],
        "signal_messages": [s["message"] for s in sigs],
        "guards": guards,
        "broker": oc.get("broker") or "tachibana",
        "money_path": oc.get("money_path"),
        "otp_note": oc.get("otp_note"),
        "live_api": bool(oc.get("live_api")),
        "created_at": now_iso(),
        "created_by": "jarvis_kurashift_stock_order",
    }


def _closes(sb: Any, symbol: str, limit: int = 90) -> list[dict[str, Any]]:
    res = (
        sb.table("trade_prices")
        .select("trade_date,open,high,low,close,volume")
        .eq("symbol", symbol)
        .order("trade_date", desc=True)
        .limit(limit)
        .execute()
    )
    rows = list(res.data or [])
    rows.reverse()
    return rows


def side_label(side: str) -> str:
    return "買い" if side == "buy" else "売り"


def assist_steps(preview: dict[str, Any]) -> list[str]:
    ticker = str(preview.get("symbol") or "").replace(".T", "")
    lot_note = "（単元未満・かぶミニ等。指値可否を立花で確認）" if preview.get("odd_lot") else ""
    return [
        f"立花e支店にログイン（取引パスワード）: {preview.get('money_path')}",
        f"銘柄 {ticker}（{preview.get('name')}）を検索",
        f"{side_label(str(preview.get('side')))} {preview.get('qty')}株 / 指値 {preview.get('limit_price')}円 / 有効期限 当日{lot_note}",
        "注文内容を最終確認して送信（送信は本人。Jarvis は OTP・送信を代行しない）",
        "約定後、約定数量・単価を Todoist Theme株式にコメント（ポジション連動は次タスク）",
    ]


def preview_body(preview: dict[str, Any], cfg: dict[str, Any]) -> str:
    sym = preview["symbol"]
    ticker = str(sym).replace(".T", "")
    lot = "単元未満（かぶミニ等）" if preview.get("odd_lot") else f"{preview['unit']}株単元"
    lines = [
        f"サマリ: 発注プレビュー {side_label(preview['side'])} {ticker} {preview['name']}",
        f"数量: {preview['qty']}株（{lot}）",
        f"指値: {preview['limit_price']}円 / 想定金額: {preview['amount_jpy']:,.0f}円",
        f"前日終値: {preview['close']:.1f}円（{preview['trade_date']}）",
        f"サイン: {', '.join(preview.get('signals') or []) or '—'}",
        f"資金経路: {preview.get('money_path')}",
        f"注意: {preview.get('otp_note')}",
        "確認: この内容で発注アシストしてよい？（オーナー確認）",
        "アウトプット:",
    ]
    for u in kurashift_urls(cfg, preview.get("theme_id")):
        label = "Theme" if "/themes/" in u else "stock-watch"
        lines.append(f"- [{label}]({u})")
    lines.append("- 確定コマンド（オーナー確認後のみ）: `--confirm <ORDER_ID> --i-confirm-order`")
    return "\n".join(lines)


def todoist_notify_preview(
    *,
    state: dict[str, Any],
    cfg: dict[str, Any],
    preview: dict[str, Any],
    task_id: str | None,
    dry_run: bool,
) -> str | None:
    lane = str((cfg.get("notify") or {}).get("todoist_lane") or "theme_stock")
    body = preview_body(preview, cfg)
    title_key = str(preview.get("theme_title") or preview["symbol"])
    if task_id:
        todoist_comment(task_id=str(task_id), comment=body, dry_run=dry_run)
        return str(task_id)
    created = todoist_create(
        lane=lane,
        title=f"[発注preview] {preview['name']} {side_label(preview['side'])} {preview['qty']}",
        status="オーナー確認",
        note="KURASHIFT 発注前プレビュー（実発注なし・手動アシスト）",
        comment=body,
        dry_run=dry_run,
    )
    tid = created.get("id") or created.get("task_id")
    if tid:
        state.setdefault("todoist_tasks_by_theme", {})[title_key] = str(tid)
    return str(tid) if tid else None


def cmd_preview(
    cfg: dict[str, Any], state: dict[str, Any], args: argparse.Namespace
) -> dict[str, Any]:
    if not args.symbol:
        raise GuardError("--symbol が必要です")
    sb = sb_client()
    preview = build_preview(
        state=state,
        sb=sb,
        cfg=cfg,
        symbol=args.symbol,
        requested_side=args.side,
        qty_arg=args.qty,
    )
    steps = assist_steps(preview)
    preview["steps"] = steps
    row = {
        "mode": ORDER_MODE,
        "symbol": preview["symbol"],
        "side": preview["side"],
        "qty": preview["qty"],
        "limit_price": preview["limit_price"],
        "status": "preview",
        "broker": preview["broker"],
        "reason": (
            f"発注プレビュー {side_label(preview['side'])} {preview['qty']}@{preview['limit_price']}"
            f"（{', '.join(preview.get('signals') or [])}）"
        ),
        "payload": preview,
    }
    if args.dry_run:
        print("# dry-run: trade_orders へ書き込みません")
        return {"preview": preview, "order_id": None}
    res = sb.table("trade_orders").insert(row).execute()
    order = (res.data or [row])[0]
    order_id = str(order.get("id"))
    task_id = (state.get("todoist_tasks_by_theme") or {}).get(
        str(preview.get("theme_title") or preview["symbol"])
    )
    if not args.no_notify:
        try:
            tid = todoist_notify_preview(
                state=state, cfg=cfg, preview=preview, task_id=task_id, dry_run=False
            )
            if tid:
                sb.table("trade_orders").update(
                    {"payload": {**preview, "todoist_task_id": tid}}
                ).eq("id", order_id).execute()
        except Exception as e:  # 通知失敗でもプレビューは残す
            print(f"# todoist notify soft-fail: {e}", file=sys.stderr)
    return {"preview": preview, "order_id": order_id, "steps": steps}


def _load_order(sb: Any, order_id: str) -> dict[str, Any]:
    res = (
        sb.table("trade_orders")
        .select("id,status,symbol,side,qty,limit_price,payload")
        .eq("id", order_id)
        .eq("mode", ORDER_MODE)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise GuardError(f"注文プレビューが見つかりません: {order_id}")
    return rows[0]


def cmd_confirm(
    cfg: dict[str, Any], state: dict[str, Any], args: argparse.Namespace
) -> dict[str, Any]:
    if not args.i_confirm_order:
        raise GuardError("--i-confirm-order が必要です（オーナー確認の表明）")
    oc = _order_cfg(cfg)
    if oc.get("live_api"):
        raise GuardError("order.live_api=true は未実装です。手動アシストのみ")
    sb = sb_client()
    order = _load_order(sb, args.confirm)
    if order.get("status") != "preview":
        raise GuardError(f"プレビュー状態ではありません: {order.get('status')}")
    payload = dict(order.get("payload") or {})

    thr = cfg.get("thresholds") or {}
    levels = compute_levels(_closes(sb, str(order["symbol"])), thr)
    if not levels:
        raise GuardError("確認時に日足が取得できません")
    close_now = float(levels["close"])
    close_prev = float(payload.get("close") or close_now)
    stale_pct = float(oc.get("stale_price_pct") or 3.0)
    if close_prev > 0 and abs(close_now - close_prev) / close_prev * 100.0 > stale_pct:
        raise GuardError(
            f"価格が乖離しました（{close_prev:.1f}→{close_now:.1f}）。再プレビューしてください"
        )
    if kill_switch_on(sb):
        raise GuardError("kill_switch が ON です（新規建て停止中）")

    steps = assist_steps(payload)
    payload = {
        **payload,
        "phase": "confirmed",
        "confirmed_at": now_iso(),
        "confirmed_by": "owner",
        "close_at_confirm": close_now,
        "steps": steps,
    }
    if args.dry_run:
        print("# dry-run: 確定しません")
        return {"order_id": args.confirm, "confirmed": False, "steps": steps}
    sb.table("trade_orders").update(
        {"status": "confirmed", "payload": payload}
    ).eq("id", args.confirm).execute()

    body = "\n".join(
        [
            f"サマリ: 発注アシスト確定（対外確認ゲート通過）{order['symbol']} "
            f"{side_label(str(order['side']))} {order['qty']}@{order['limit_price']}",
            "確認: オーナー確認済み（--i-confirm-order）",
            "手順:",
            *[f"{i + 1}. {s}" for i, s in enumerate(steps)],
        ]
    )
    task_id = payload.get("todoist_task_id")
    try:
        if task_id:
            todoist_comment(task_id=str(task_id), comment=body, dry_run=False)
    except Exception as e:
        print(f"# todoist notify soft-fail: {e}", file=sys.stderr)
    return {"order_id": args.confirm, "confirmed": True, "steps": steps, "live_api": False}


def cmd_cancel(cfg: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    sb = sb_client()
    order = _load_order(sb, args.cancel)
    if order.get("status") not in ("preview", "confirmed"):
        raise GuardError(f"取り消せません: {order.get('status')}")
    if args.dry_run:
        print("# dry-run: 取り消しません")
        return {"order_id": args.cancel, "cancelled": False}
    sb.table("trade_orders").update({"status": "cancelled"}).eq(
        "id", args.cancel
    ).execute()
    payload = order.get("payload") or {}
    task_id = payload.get("todoist_task_id")
    try:
        if task_id:
            todoist_comment(
                task_id=str(task_id),
                comment=f"サマリ: 発注プレビュー取り消し {order['symbol']}",
                dry_run=False,
            )
    except Exception as e:
        print(f"# todoist notify soft-fail: {e}", file=sys.stderr)
    return {"order_id": args.cancel, "cancelled": True}


def cmd_list(sb: Any) -> dict[str, Any]:
    orders = existing_open_orders(sb)
    for o in orders:
        p = o.get("payload") or {}
        o["summary"] = (
            f"{o['symbol']} {side_label(str(o['side']))} {o['qty']}@{o['limit_price']}"
            f" ≈{float(p.get('amount_jpy') or 0):,.0f}円 [{o['status']}]"
        )
        o.pop("payload", None)
    return {"open": orders, "live_api": False}


def main() -> int:
    ap = argparse.ArgumentParser(description="KURASHIFT 発注前プレビュー＋対外確認ゲート")
    ap.add_argument("--preview", action="store_true", help="発注プレビューを作成")
    ap.add_argument("--symbol", default="", help="対象銘柄（Yahoo 記号）")
    ap.add_argument("--side", default="", choices=["", "buy", "sell"])
    ap.add_argument("--qty", type=int, default=None)
    ap.add_argument("--confirm", default="", help="確定する trade_orders.id")
    ap.add_argument("--cancel", default="", help="取り消す trade_orders.id")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--i-confirm-order", action="store_true", help="オーナー確認済みの表明")
    ap.add_argument("--no-notify", action="store_true", help="Todoist 通知を出さない")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = _cfg()
    if not cfg.get("enabled", True):
        print("📎 stock_order: disabled in config")
        return 0

    try:
        if args.confirm:
            out = cmd_confirm(cfg, load_state(), args)
        elif args.cancel:
            out = cmd_cancel(cfg, args)
        elif args.list:
            out = cmd_list(sb_client())
        elif args.preview:
            state = load_state()
            out = cmd_preview(cfg, state, args)
            if not args.dry_run:
                save_state(state)
        else:
            ap.error("--preview / --confirm / --cancel / --list のいずれかが必要です")
            return 2
    except GuardError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print("📎 KURASHIFT 発注プレビュー（実発注なし）")
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
