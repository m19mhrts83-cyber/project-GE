#!/usr/bin/env python3
"""
Vポイント PDCA ボード — 獲得効率の「良かった点／要改善／次の一手」を整理する。

Plan  … open_actions（cadence）＝改善バックログ
Do   … ユーザー操作 ＋ Jarvis 会話（『〇〇 やった』）
Check … 月次付与サマリ／監査／Tサイト差分（定例＋必要時）
Act  … action を verify→done、次の一手を入れ替え

  python scripts/jarvis_vpoint_pdca.py
  python scripts/jarvis_vpoint_pdca.py --apply   # vpoint_monthly.json に pdca_board を書く
  python scripts/jarvis_vpoint_pdca.py --push
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE = REPO / ".jarvis_state"
MONTHLY = STATE / "vpoint_monthly.json"
CADENCE = STATE / "vpoint_cadence.json"
AUDIT = STATE / "vpoint_audit_result.json"
TEIKI = STATE / "teiki_barai_chance.json"
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"


def load(path: Path) -> dict[str, Any]:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def build_board(
    monthly: dict[str, Any],
    cadence: dict[str, Any],
    audit: dict[str, Any],
    teiki: dict[str, Any],
) -> dict[str, Any]:
    wins: list[dict[str, str]] = []
    gaps: list[dict[str, str]] = []
    freshness: list[str] = []

    ct = audit.get("credit_tsumitate") or {}
    mh = audit.get("merchant_high_rate") or {}
    rate = ct.get("effective_rate") or {}
    hist = ct.get("point_history") or {}

    # --- Wins ---
    if ct.get("monthly_yen_confirmed"):
        wins.append(
            {
                "id": "tsumitate_running",
                "title": "クレカ積立は毎月稼働",
                "detail": f"{ct.get('monthly_yen_confirmed'):,}円/月（Gmail・Vpassで確認済）",
            }
        )
    tsite = mh.get("tsite_evidence") or {}
    if tsite.get("mcdonalds_plus6pct_20260724") or tsite.get("saizeriya_plus6pct_20260724"):
        wins.append(
            {
                "id": "mobile_order_6pct",
                "title": "対象店＋6%の実績あり（正しいレール）",
                "detail": "マクド／サイゼ等はモバイルオーダーで＋6%付与を確認。iDではなく正しい経路の証拠",
            }
        )
    # 残高は最新 Tサイト履歴 → cadence → 監査内履歴の順
    bal = cadence.get("last_balance_pt")
    latest_hist = None
    hist_files = sorted(STATE.glob("vpoint_tsite_history_*.json"), reverse=True)
    if hist_files:
        try:
            latest_hist = json.loads(hist_files[0].read_text(encoding="utf-8"))
            if latest_hist.get("balance_pt") is not None:
                bal = latest_hist.get("balance_pt")
        except Exception:
            latest_hist = None
    if bal is None:
        bal = hist.get("balance_pt")
    if bal is not None:
        wins.append(
            {
                "id": "balance_visible",
                "title": "Vポイント残高を追えている",
                "detail": f"直近残高目安 {bal:,}pt（Tサイト／cadence）",
            }
        )
    if latest_hist and latest_hist.get("key_entries"):
        wins.append(
            {
                "id": "tsite_fresh",
                "title": "Tサイト履歴を取得済み",
                "detail": f"{hist_files[0].name} · 注目行 {len(latest_hist.get('key_entries') or [])}件",
            }
        )
    if (teiki.get("enrolled") == "yes") or teiki.get("last_draw"):
        wins.append(
            {
                "id": "teiki_enrolled",
                "title": "テイチャン参加・抽選まで自動化",
                "detail": "規約同意済。券があれば定例が抽選（手動不要）",
            }
        )

    # User intent: credit not iD — treat as hypothesis until meisai Check
    meisai = mh.get("meisai_sample") or mh.get("meisai_202608_sample") or {}
    id_note = str(meisai.get("note") or "")
    id_ratio = meisai.get("id_ratio")
    id_heavy = isinstance(id_ratio, (int, float)) and id_ratio >= 0.45
    id_mixed = isinstance(id_ratio, (int, float)) and 0.05 <= id_ratio < 0.45
    if id_ratio is None:
        # 比率が無いときだけ文言フォールバック
        if "ほぼ全て" in id_note and ("ｉＤ" in id_note or "iD" in id_note):
            id_heavy = True
        elif "ｉＤ" in id_note or "／ｉＤ" in id_note or "iD" in id_note:
            id_mixed = True
    if id_heavy:
        gaps.append(
            {
                "id": "id_rail_verify",
                "title": "決済レールがｉＤ優勢（高還元に不利）",
                "detail": (
                    "意図はクレジット払い。明細で／ｉＤが多い。"
                    "Wallet表示と本体がズレることがあるので、Visaタッチ徹底が必要"
                ),
                "priority": "high",
            }
        )
    elif id_mixed:
        gaps.append(
            {
                "id": "id_rail_verify",
                "title": "決済レールは改善中（ｉＤ混在）",
                "detail": (
                    f"直近明細の／ｉＤ比率は約{int(float(id_ratio)*100)}%。"
                    if isinstance(id_ratio, (int, float))
                    else "直近明細に／ｉＤが残る。"
                )
                + "セブン等でｉＤなしも確認。ファミマ等のｉＤ残をVisaタッチへ寄せる",
                "priority": "medium",
            }
        )
        wins.append(
            {
                "id": "id_rail_improved",
                "title": "ｉＤ一色からは改善",
                "detail": (
                    f"／ｉＤ比率 約{int(float(id_ratio)*100)}%（以前のほぼ全てｉＤより低下）。"
                    if isinstance(id_ratio, (int, float))
                    else "明細上のｉＤ優勢が緩和。"
                )
                + "マクドモバイルオーダー／セブンｉＤなし行あり",
            }
        )
    else:
        wins.append(
            {
                "id": "rail_ok",
                "title": "明細上の決済レールに大きな問題なし",
                "detail": "直近監査で iD 優勢の警告なし（再確認は月次）",
            }
        )

    if rate.get("status") in ("confirmed_1pct_not_6pct", "not_yet_verifiable_as_6pct"):
        gaps.append(
            {
                "id": "tsumitate_1pct",
                "title": "クレカ積立は実績1%（最大6%未達）",
                "detail": "9万円→900pt。年間カード利用帯＋Olive資産特典の条件が未達または未反映の可能性",
                "priority": "high",
            }
        )

    open_actions = [
        a for a in (cadence.get("open_actions") or []) if isinstance(a, dict) and a.get("status") == "open"
    ]
    for a in open_actions:
        aid = str(a.get("id") or "")
        if any(g["id"] == aid or g["id"].endswith(aid) for g in gaps):
            continue
        # map known ids
        if aid == "visa_touch_not_id" and any(g["id"] == "id_rail_verify" for g in gaps):
            continue
        if aid == "tsumitate_rate_band" and any(g["id"] == "tsumitate_1pct" for g in gaps):
            continue
        gaps.append(
            {
                "id": aid,
                "title": str(a.get("title") or aid),
                "detail": str(a.get("why") or a.get("how") or ""),
                "priority": "medium",
                "how": str(a.get("how") or ""),
            }
        )

    # Freshness
    audited = str(audit.get("audited_at") or "")
    if audited:
        freshness.append(f"深い監査: {audited}")
    else:
        freshness.append("深い監査: なし")
    rc = monthly.get("last_result_c") or {}
    gs = rc.get("grant_summary") if isinstance(rc.get("grant_summary"), dict) else {}
    if gs.get("target_month"):
        freshness.append(
            f"付与サマリ: {gs.get('target_month')} · {gs.get('total_pt')}pt · {gs.get('source_note') or ''}"
        )
    if not list(STATE.glob("vpoint_tsite_history_*.json")):
        freshness.append("Tサイト履歴スナップ: 無し → 『Tサイト取って』で精度↑")
        gaps.append(
            {
                "id": "tsite_refresh",
                "title": "Tサイト履歴が無い／古い",
                "detail": "月次付与サマリが監査フォールバックになりやすい。OTP付き取込がCheckの要",
                "priority": "high",
                "how": "Jarvisに『Tサイト取って』",
            }
        )

    # Next 2 actions (PDCA Do) — high 優先、同優先内は既定順
    next_actions: list[dict[str, str]] = []
    priority_order = [
        "tsite_refresh",
        "tsumitate_1pct",
        "tsumitate_rate_band",
        "id_rail_verify",
        "visa_touch_not_id",
        "eraberu_tokuten",
        "nisa_eval_band",
    ]
    pri_rank = {"high": 0, "medium": 1, "low": 2}

    def gap_sort_key(g: dict[str, Any]) -> tuple:
        pid = str(g.get("id") or "")
        order = priority_order.index(pid) if pid in priority_order else 99
        return (pri_rank.get(str(g.get("priority") or "medium"), 1), order)

    for g in sorted(gaps, key=gap_sort_key):
        pid = str(g.get("id") or "")
        how = g.get("how") or ""
        if pid == "id_rail_verify":
            how = how or "ファミマ等のｉＤ残を Visaタッチで1回→『試した』（Walletは勝手に変えない）。セブンのｉＤなしは維持"
        if pid == "tsumitate_1pct":
            how = how or "年間利用帯・資産特典を確認。付与行が900以外／Infinite表記になったら一声"
        if pid == "tsite_refresh":
            how = how or "『Tサイト取って』"
        next_actions.append({"id": pid, "title": g["title"], "how": how})
        if len(next_actions) >= 2:
            break
    if len(next_actions) < 2:
        for a in open_actions:
            aid = str(a.get("id") or "")
            if any(n["id"] == aid for n in next_actions):
                continue
            next_actions.append(
                {"id": aid, "title": str(a.get("title") or aid), "how": str(a.get("how") or "")}
            )
            if len(next_actions) >= 2:
                break

    return {
        "at": now_iso(),
        "approach": "status_first_then_chat",
        "loop": {
            "plan": "open_actions（cadence）＝改善バックログ",
            "do": "ユーザー操作＋Jarvis会話（『〇〇 やった』／『試した』）",
            "check": "月次付与サマリ＋cadence差分＋必要時の深い監査／Tサイト",
            "act": "verify→done、次の一手入れ替え、pdca_board 更新",
        },
        "wins": wins,
        "gaps": gaps,
        "next_actions": next_actions[:2],
        "freshness": freshness,
        "user_intent_note": (
            (
                f"クレジット払い意図あり。直近明細の／ｉＤ比率は約{int(float(id_ratio)*100)}%"
                f"（改善中・混在）。表示名だけでは断定しない"
            )
            if isinstance(id_ratio, (int, float))
            else "クレジット払い意図あり。明細の／ｉＤ有無で Check（表示名だけでは断定しない）"
        ),
        "href": "/vpoint#pdca",
    }


def format_block(board: dict[str, Any]) -> str:
    lines = [
        "---",
        "📎 Vポイント PDCA（獲得効率）",
        f"- 更新: {board.get('at')}",
        f"- 方針: ステータス把握 → 会話で改善（{board.get('approach')}）",
        "- 良かった点:",
    ]
    for w in board.get("wins") or []:
        lines.append(f"  · {w.get('title')} — {w.get('detail')}")
    if not board.get("wins"):
        lines.append("  · （まだ少ない）")
    lines.append("- 要改善:")
    for g in board.get("gaps") or []:
        lines.append(f"  · [{g.get('priority') or '—'}] {g.get('title')} — {g.get('detail')}")
    lines.append("- 次の一手（最大2）:")
    for n in board.get("next_actions") or []:
        lines.append(f"  · {n.get('title')} → {n.get('how')}")
    lines.append("- データ鮮度:")
    for f in board.get("freshness") or []:
        lines.append(f"  · {f}")
    if board.get("user_intent_note"):
        lines.append(f"- 注: {board['user_intent_note']}")
    lines.append("---")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Vポイント PDCA ボード")
    ap.add_argument("--apply", action="store_true", help="monthly state に保存")
    ap.add_argument("--push", action="store_true")
    args = ap.parse_args()

    monthly = load(MONTHLY)
    cadence = load(CADENCE)
    audit = load(AUDIT)
    teiki = load(TEIKI)
    board = build_board(monthly, cadence, audit, teiki)
    print(format_block(board))
    print()
    print(json.dumps(board, ensure_ascii=False, indent=2))

    if args.apply:
        monthly["pdca_board"] = board
        save(MONTHLY, monthly)
        print("\n✅ wrote pdca_board → vpoint_monthly.json")

    if args.push and args.apply:
        py = str(PY) if PY.is_file() else sys.executable
        subprocess.run(
            [py, str(REPO / "scripts" / "jarvis_dashboard_push.py"), "--watch-only"],
            cwd=str(REPO),
            check=False,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
