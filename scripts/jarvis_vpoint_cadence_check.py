#!/usr/bin/env python3
"""Jarvis Vポイント日常 cadence — 間隔ゲート・差分要約・処置提案ブロック。

パートナー確認の必須手順には入れない。前半末尾のついで表示用。

使い方:
  python scripts/jarvis_vpoint_cadence_check.py
  python scripts/jarvis_vpoint_cadence_check.py --mark-prompted
  python scripts/jarvis_vpoint_cadence_check.py --status
  python scripts/jarvis_vpoint_cadence_check.py --mark-action-waiting ID
  python scripts/jarvis_vpoint_cadence_check.py --mark-action-verify ID
  python scripts/jarvis_vpoint_cadence_check.py --mark-action-done ID
  python scripts/jarvis_vpoint_cadence_check.py --force
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_DIR = REPO / ".jarvis_state"
STATE_PATH = STATE_DIR / "vpoint_cadence.json"
EXAMPLE_PATH = STATE_DIR / "vpoint_cadence.example.json"
RESULT_PATH = STATE_DIR / "vpoint_audit_result.json"
PRIVATE_ENV = REPO / ".env.jarvis_private"
HISTORY_GLOB = "vpoint_tsite_history_*.json"

MAX_ACTIONS_IN_REPORT = 2
MATERIAL_BALANCE_DELTA = 500  # pt
DEFAULT_INTERVAL_DAYS = 2


def load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$", line)
        if m and not line.lstrip().startswith("#"):
            out[m.group(1)] = m.group(2).strip().strip("\"'")
    return out


def load_json(path: Path, default: dict | None = None) -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return default if default is not None else {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
        return dt.astimezone(JST)
    except ValueError:
        return None


def entry_hash(e: dict) -> str:
    return f"{e.get('date','')}|{e.get('desc','')}|{e.get('pt','')}"


def latest_history() -> dict | None:
    files = sorted(STATE_DIR.glob(HISTORY_GLOB), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files:
        data = load_json(p)
        if data:
            data["_path"] = str(p)
            return data
    return None


def ensure_state() -> dict:
    state = load_json(STATE_PATH)
    if not state:
        state = load_json(EXAMPLE_PATH, {"disabled": False, "interval_days": DEFAULT_INTERVAL_DAYS})
    state.setdefault("interval_days", DEFAULT_INTERVAL_DAYS)
    state.setdefault("open_actions", [])
    state.setdefault("last_key_hashes", [])
    return state


def tsite_ready(env: dict[str, str]) -> bool:
    """番号ログイン＋メールOTPで足りる。PASSWORD は任意。"""
    return bool(env.get("VPOINT_TSITE_ID"))


def compute_delta(state: dict, hist: dict | None, result: dict) -> dict:
    bal = None
    entries: list[dict] = []
    if hist:
        bal = hist.get("balance_pt")
        entries = list(hist.get("key_entries") or [])
    if bal is None:
        ct = result.get("credit_tsumitate") or {}
        bal = ct.get("vpoint_balance_2026_07_29")
        ph = ct.get("point_history") or {}
        if isinstance(ph.get("balance_pt"), int):
            bal = ph["balance_pt"]

    prev_bal = state.get("last_balance_pt")
    bal_delta = None
    if bal is not None and prev_bal is not None:
        bal_delta = int(bal) - int(prev_bal)

    prev_hashes = set(state.get("last_key_hashes") or [])
    new_entries = []
    for e in entries:
        h = entry_hash(e)
        if h not in prev_hashes:
            new_entries.append(e)

    tsumi_pt = None
    tsumi_label = None
    for e in entries:
        desc = str(e.get("desc") or "")
        if "投信積立カード決済特典" in desc:
            tsumi_pt = e.get("pt")
            if "インフィニット" in desc or "ＩＮＦ" in desc or "Infinite" in desc.upper():
                tsumi_label = "Infinite"
            elif "プリファード" in desc:
                tsumi_label = "プラチナプリファード"
            else:
                tsumi_label = desc[-20:]
            break

    material: list[str] = []
    if bal_delta is not None and abs(bal_delta) >= MATERIAL_BALANCE_DELTA:
        material.append(f"残高変動 {bal_delta:+d}pt")
    prev_tsumi = state.get("last_tsumitate_bonus_pt")
    if tsumi_pt is not None and prev_tsumi is not None and int(tsumi_pt) != int(prev_tsumi):
        material.append(f"積立特典 {prev_tsumi}→{tsumi_pt}pt")
    prev_label = state.get("last_tsumitate_label")
    if tsumi_label and prev_label and tsumi_label != prev_label:
        material.append(f"積立表記 {prev_label}→{tsumi_label}")
    for e in new_entries:
        desc = str(e.get("desc") or "")
        if "投信積立カード決済特典" in desc or "＋６％" in desc or "+6%" in desc:
            material.append(f"新規重要付与: {desc[:40]} {e.get('pt')}pt")

    verify_actions = [a for a in state.get("open_actions") or [] if a.get("status") == "verify_next"]
    if verify_actions:
        material.append(f"検証待ちアクション {len(verify_actions)}件")

    rate = (result.get("credit_tsumitate") or {}).get("effective_rate") or {}
    rate_status = rate.get("status") or rate.get("verdict") or ""
    merchant = result.get("merchant_high_rate") or {}
    rail_note = ""
    if hist and hist.get("verdicts"):
        rail_note = str((hist["verdicts"] or {}).get("merchant") or "")[:120]
    if not rail_note:
        rail_note = str(merchant.get("verdict") or "")[:120]

    return {
        "balance_pt": bal,
        "balance_delta": bal_delta,
        "new_entries": new_entries[:5],
        "tsumitate_bonus_pt": tsumi_pt,
        "tsumitate_label": tsumi_label,
        "material_reasons": material,
        "has_material": bool(material),
        "rate_status": rate_status,
        "rail_note": rail_note,
        "entry_hashes": [entry_hash(e) for e in entries] if entries else list(state.get("last_key_hashes") or []),
    }


def is_due(state: dict, now: datetime, force: bool, has_material: bool) -> tuple[bool, str]:
    if force:
        return True, "force"
    if has_material:
        return True, "material_diff"
    last = _parse_iso(state.get("last_prompted_at") or state.get("last_check_at"))
    if last is None:
        return True, "never_checked"
    interval = int(state.get("interval_days") or DEFAULT_INTERVAL_DAYS)
    if now - last >= timedelta(days=interval):
        return True, f"interval_{interval}d"
    return False, "cooldown"


def actions_for_report(state: dict) -> tuple[list[dict], list[dict]]:
    open_like = []
    verify = []
    for a in state.get("open_actions") or []:
        st = a.get("status") or "open"
        if st in ("open", "waiting_user"):
            open_like.append(a)
        elif st == "verify_next":
            verify.append(a)
    return open_like[:MAX_ACTIONS_IN_REPORT], verify


def format_block(
    *,
    due: bool,
    reason: str,
    delta: dict,
    state: dict,
    tsite: str,
    quiet: bool,
) -> str | None:
    if not due and quiet:
        return None
    if not due:
        return None

    bal = delta.get("balance_pt")
    bd = delta.get("balance_delta")
    bal_line = f"{bal}" if bal is not None else "—"
    if bd is not None:
        bal_line += f"（前回比 {bd:+d}）"

    new_lines = delta.get("new_entries") or []
    if new_lines:
        grant = " / ".join(f"{e.get('date')} {str(e.get('desc'))[:28]} {e.get('pt')}pt" for e in new_lines[:3])
    else:
        grant = "なし（スナップショット差分なし）"

    rate = delta.get("rate_status") or "—"
    if delta.get("tsumitate_bonus_pt") is not None:
        rate = f"積立特典直近{delta['tsumitate_bonus_pt']}pt（{delta.get('tsumitate_label') or '—'}） / {rate}"

    rail = delta.get("rail_note") or "—"
    open_a, verify_a = actions_for_report(state)

    lines = [
        "📎 Vポイント（ついで・差分）",
        f"- 残高: {bal_line}",
        f"- 新規付与: {grant}",
        f"- 判定: {rate} ／ 対象店: {rail}",
        f"- Tサイト: {tsite}",
    ]
    if open_a:
        lines.append("- 次の一手:")
        for a in open_a:
            lines.append(f"  · [{a.get('id')}] {a.get('title')} — {a.get('how')}")
    else:
        lines.append("- 次の一手: （open なし）")
    if verify_a:
        ids = ", ".join(a.get("id", "?") for a in verify_a)
        lines.append(f"- 検証待ち: {ids}（次回 Tサイト／明細で確認）")
    if delta.get("material_reasons"):
        lines.append(f"- 重大差分: {'; '.join(delta['material_reasons'])}")
    lines.append(f"- ゲート: {reason}（間隔{state.get('interval_days', DEFAULT_INTERVAL_DAYS)}日）")
    return "\n".join(lines)


def find_action(state: dict, action_id: str) -> dict | None:
    for a in state.get("open_actions") or []:
        if a.get("id") == action_id:
            return a
    return None


def set_action_status(state: dict, action_id: str, status: str, evidence: str | None = None) -> bool:
    a = find_action(state, action_id)
    if not a:
        return False
    a["status"] = status
    a["updated_at"] = datetime.now(JST).isoformat(timespec="seconds")
    if evidence:
        a["evidence"] = evidence
    return True


def apply_snapshot_to_state(state: dict, delta: dict, now: datetime) -> None:
    state["last_check_at"] = now.isoformat(timespec="seconds")
    if delta.get("balance_pt") is not None:
        state["last_balance_pt"] = delta["balance_pt"]
    if delta.get("entry_hashes"):
        state["last_key_hashes"] = delta["entry_hashes"]
    if delta.get("tsumitate_bonus_pt") is not None:
        state["last_tsumitate_bonus_pt"] = delta["tsumitate_bonus_pt"]
    if delta.get("tsumitate_label"):
        state["last_tsumitate_label"] = delta["tsumitate_label"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Jarvis Vポイント日常 cadence")
    ap.add_argument("--mark-prompted", action="store_true", help="表示した扱いにし last_prompted_at を更新")
    ap.add_argument("--status", action="store_true", help="due 判定のみ JSON")
    ap.add_argument("--force", action="store_true", help="間隔無視でブロック出力")
    ap.add_argument("--quiet", action="store_true", help="due でなければ何も出さない（既定と同じ）")
    ap.add_argument("--mark-action-waiting", metavar="ID", help="ユーザー作業中にする")
    ap.add_argument("--mark-action-verify", metavar="ID", help="次回検証待ちにする")
    ap.add_argument("--mark-action-done", metavar="ID", help="完了にする")
    ap.add_argument("--evidence", default="", help="アクション更新時のメモ")
    args = ap.parse_args()

    env = load_dotenv(PRIVATE_ENV)
    if env.get("JARVIS_VPOINT_CADENCE_DISABLE") == "1":
        print("📎 Vポイント（ついで）: 無効化（JARVIS_VPOINT_CADENCE_DISABLE=1）")
        return 0

    state = ensure_state()
    if state.get("disabled"):
        print("📎 Vポイント（ついで）: 無効化（vpoint_cadence.json disabled）")
        return 0

    now = datetime.now(JST)
    hist = latest_history()
    result = load_json(RESULT_PATH)
    delta = compute_delta(state, hist, result)
    due, reason = is_due(state, now, args.force, delta["has_material"])
    tsite = "ready_id" if tsite_ready(env) else "pending_user（VPOINT_TSITE_ID）"

    # action status updates (always allowed)
    for flag, status in (
        (args.mark_action_waiting, "waiting_user"),
        (args.mark_action_verify, "verify_next"),
        (args.mark_action_done, "done"),
    ):
        if flag:
            if not set_action_status(state, flag, status, args.evidence or None):
                print(f"⚠️ action id not found: {flag}", file=sys.stderr)
                return 1
            save_state(state)
            print(f"✅ action {flag} → {status}")
            return 0

    if args.status:
        print(
            json.dumps(
                {
                    "due": due,
                    "reason": reason,
                    "has_material": delta["has_material"],
                    "material_reasons": delta["material_reasons"],
                    "last_prompted_at": state.get("last_prompted_at"),
                    "interval_days": state.get("interval_days"),
                    "balance_pt": delta.get("balance_pt"),
                    "tsite": tsite,
                    "open_actions": [
                        {"id": a.get("id"), "status": a.get("status"), "title": a.get("title")}
                        for a in state.get("open_actions") or []
                        if a.get("status") != "done"
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    block = format_block(due=due, reason=reason, delta=delta, state=state, tsite=tsite, quiet=True)
    if block:
        print(block)
    elif args.force:
        print("📎 Vポイント（ついで・差分）: （空）")
    # due でなければ無出力（LINE export info と同様）

    if args.mark_prompted and due:
        apply_snapshot_to_state(state, delta, now)
        state["last_prompted_at"] = now.isoformat(timespec="seconds")
        save_state(state)
        print(f"\n✅ marked last_prompted_at={state['last_prompted_at']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
