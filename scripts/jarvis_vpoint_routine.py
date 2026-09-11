#!/usr/bin/env python3
"""
Vポイント定例ルーティン — 自動できること／Jarvis確認が必要なことを切り分けて実行。

【自動（OTP・画面操作なし／または Vpass のみ）】
  A. ウィンドウC（25日〜月末）: 既存 Tサイト履歴／監査から付与サマリを生成 → /vpoint
  B. cadence 差分（既存スナップショット）: open_actions を整理
  C. テイチャン: interval 到来時に Vpass で確認＋券があれば抽選（失敗したら促し）

【自動にしない（Jarvis ↔ ユーザー）】
  - Tサイト新規スクレイプ（メールOTP）
  - Wallet／Visaタッチ実機確認
  - 選べる特典・NISA評価額帯の設定変更
  - Vpass 深い明細監査の初回／再監査（Chrome 承認が絡む）

使い方:
  python scripts/jarvis_vpoint_routine.py --dry-run
  python scripts/jarvis_vpoint_routine.py --apply --push
  python scripts/jarvis_vpoint_routine.py --force-window-c --apply --push
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_DIR = REPO / ".jarvis_state"
PRIVATE_ENV = REPO / ".env.jarvis_private"
MONTHLY_PATH = STATE_DIR / "vpoint_monthly.json"
CADENCE_PATH = STATE_DIR / "vpoint_cadence.json"
TEIKI_PATH = STATE_DIR / "teiki_barai_chance.json"
AUDIT_PATH = STATE_DIR / "vpoint_audit_result.json"
HISTORY_GLOB = "vpoint_tsite_history_*.json"
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"

# 付与サマリ更新窓（月次ウィンドウC）
WINDOW_C_START_DAY = 25


def load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        import re

        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$", line)
        if m and not line.lstrip().startswith("#"):
            out[m.group(1)] = m.group(2).strip().strip("\"'")
    return out


def load_json(path: Path) -> dict[str, Any]:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def prev_month_key(dt: datetime) -> str:
    y, m = dt.year, dt.month
    if m == 1:
        return f"{y - 1}-12"
    return f"{y}-{m - 1:02d}"


def in_window_c(dt: datetime) -> bool:
    return dt.day >= WINDOW_C_START_DAY


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def latest_tsite_mtime() -> datetime | None:
    files = list(STATE_DIR.glob(HISTORY_GLOB))
    if not files:
        return None
    newest = max(files, key=lambda p: p.stat().st_mtime)
    return datetime.fromtimestamp(newest.stat().st_mtime, tz=JST)


def history_has_month(monthly: dict[str, Any], target: str) -> bool:
    for h in monthly.get("grant_history") or []:
        if isinstance(h, dict) and h.get("target_month") == target and h.get("total_pt") is not None:
            return True
    rc = monthly.get("last_result_c") or {}
    gs = rc.get("grant_summary") if isinstance(rc.get("grant_summary"), dict) else {}
    return gs.get("target_month") == target and gs.get("total_pt") is not None


def run_py(args: list[str], *, timeout: int = 300) -> dict[str, Any]:
    cmd = [str(PY), *args]
    env = os.environ.copy()
    for k, v in load_dotenv(PRIVATE_ENV).items():
        env.setdefault(k, v)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-1200:],
            "stderr_tail": (proc.stderr or "")[-600:],
        }
    except subprocess.TimeoutExpired as e:
        return {"ok": False, "error": f"timeout: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def build_jarvis_asks(
    *,
    env: dict[str, str],
    monthly: dict[str, Any],
    cadence: dict[str, Any],
    teiki: dict[str, Any],
    now: datetime,
    grant_built: bool,
    grant_source: str,
) -> list[dict[str, str]]:
    """プログラム化できない／人手確認が必要な項目。"""
    asks: list[dict[str, str]] = []

    tsite_ready = bool(env.get("VPOINT_TSITE_ID"))
    tsite_mt = latest_tsite_mtime()
    if not tsite_ready:
        asks.append(
            {
                "id": "tsite_id",
                "level": "ask",
                "text": "VPOINT_TSITE_ID 未設定。`.env.jarvis_private` に V会員番号を追記してください。",
            }
        )
    elif tsite_mt is None:
        asks.append(
            {
                "id": "tsite_refresh",
                "level": "ask",
                "text": "Tサイト履歴スナップがありません。OTP付きで『Tサイト取って』と Jarvis に依頼してください（付与サマリ精度が上がります）。",
            }
        )
    elif now - tsite_mt > timedelta(days=40):
        asks.append(
            {
                "id": "tsite_stale",
                "level": "suggest",
                "text": f"Tサイト履歴が古い（最終 {tsite_mt.date()}）。ウィンドウC前後に『Tサイト取って』で更新を。",
            }
        )

    if "フォールバック" in (grant_source or "") or "監査" in (grant_source or ""):
        asks.append(
            {
                "id": "grant_fallback",
                "level": "suggest",
                "text": "今月の付与サマリは監査フォールバック／古いデータ依存です。Tサイト更新後に `--force` で再生成できます。",
            }
        )

    audit_mt = (
        datetime.fromtimestamp(AUDIT_PATH.stat().st_mtime, tz=JST)
        if AUDIT_PATH.is_file()
        else None
    )
    if audit_mt is None or now - audit_mt > timedelta(days=45):
        asks.append(
            {
                "id": "deep_audit",
                "level": "suggest",
                "text": "深いVポイント監査（Vpass明細の／ｉＤ比率など）が古い／無し。『Vポイント監査して』で再突合できます（Walletは勝手に変えません）。",
            }
        )

    for a in (cadence.get("open_actions") or [])[:6]:
        if not isinstance(a, dict) or a.get("status") != "open":
            continue
        aid = str(a.get("id") or "")
        title = str(a.get("title") or aid)
        how = str(a.get("how") or "").strip()
        asks.append(
            {
                "id": f"action:{aid}",
                "level": "ask",
                "text": f"要対応: {title}。次の一手: {how or '—'}（終わったら『{aid} やった』と一声）",
            }
        )

    if not teiki.get("disabled"):
        for s in teiki.get("services") or []:
            if not isinstance(s, dict):
                continue
            st = str(s.get("status") or "")
            if st in ("awaiting_first_charge", "awaiting_registration", "candidate"):
                asks.append(
                    {
                        "id": f"teiki:{s.get('id')}",
                        "level": "suggest",
                        "text": f"テイチャン: {s.get('title') or s.get('id')}（status={st}）。{s.get('note') or ''}",
                    }
                )
        tickets = teiki.get("ticket_count")
        if isinstance(tickets, int) and tickets > 0:
            asks.append(
                {
                    "id": "teiki_draw",
                    "level": "ask",
                    "text": f"テイチャン抽選券が {tickets} 枚残っています。定例が失敗していれば『テイチャン回して』。",
                }
            )

    if in_window_c(now) and monthly.get("last_check_c") != month_key(now) and not grant_built:
        asks.append(
            {
                "id": "window_c_pending",
                "level": "ask",
                "text": "ウィンドウC未実施。定例失敗時は『Vポイント月次やって』と依頼してください。",
            }
        )

    # 重複 id を落とす
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for a in asks:
        if a["id"] in seen:
            continue
        seen.add(a["id"])
        out.append(a)
    return out[:12]


def main() -> int:
    ap = argparse.ArgumentParser(description="Vポイント定例（自動＋Jarvis促し）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true", help="state 更新・子スクリプト実行")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--force-window-c", action="store_true", help="窓外でも付与サマリ更新")
    ap.add_argument("--skip-teiki", action="store_true", help="テイチャンブラウザをスキップ")
    ap.add_argument("--skip-cadence", action="store_true")
    ap.add_argument("--target-month", default="", help="付与サマリ対象 YYYY-MM（既定=前月）")
    args = ap.parse_args()

    now = datetime.now(JST)
    env = load_dotenv(PRIVATE_ENV)
    report: dict[str, Any] = {
        "now_jst": now.isoformat(),
        "window_c": in_window_c(now),
        "auto": {},
        "manual": {},
    }

    if env.get("JARVIS_VPOINT_MONTHLY_DISABLE") == "1" or env.get(
        "JARVIS_VPOINT_ROUTINE_DISABLE"
    ) == "1":
        report["skipped"] = "disabled"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    monthly = load_json(MONTHLY_PATH)
    if monthly.get("disabled"):
        report["skipped"] = "vpoint_monthly disabled"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    cadence = load_json(CADENCE_PATH)
    teiki = load_json(TEIKI_PATH)
    target = (args.target_month or "").strip() or prev_month_key(now)
    report["target_month"] = target

    do_window = args.force_window_c or in_window_c(now)
    grant_built = False
    grant_source = ""

    # --- Auto A: grant summary ---
    need_grant = do_window and (
        args.force_window_c
        or monthly.get("last_check_c") != month_key(now)
        or not history_has_month(monthly, target)
    )
    report["auto"]["grant_summary"] = {
        "planned": need_grant,
        "reason": "window_c" if do_window else "outside_window",
    }
    if need_grant:
        if args.dry_run or not args.apply:
            report["auto"]["grant_summary"]["status"] = "dry_run_or_no_apply"
        else:
            # mark-done only inside real window; force-window-c outside still builds summary
            cmd = [
                str(REPO / "scripts" / "jarvis_vpoint_monthly_check.py"),
                "--build-summary-only",
                "--target-month",
                target,
            ]
            if in_window_c(now) or args.force_window_c:
                # also stamp last_check_c when in window (or forced as monthly run)
                if in_window_c(now):
                    cmd.append("--mark-done")
            r = run_py(cmd, timeout=120)
            report["auto"]["grant_summary"]["result"] = {
                "ok": r.get("ok"),
                "returncode": r.get("returncode"),
            }
            if r.get("ok"):
                grant_built = True
                monthly = load_json(MONTHLY_PATH)
                rc = monthly.get("last_result_c") or {}
                gs = rc.get("grant_summary") or {}
                grant_source = str(gs.get("source_note") or "")
                report["auto"]["grant_summary"]["total_pt"] = gs.get("total_pt")
                report["auto"]["grant_summary"]["source_note"] = grant_source

    # --- Auto B: cadence (state-only, no browser) ---
    if not args.skip_cadence and not cadence.get("disabled"):
        if args.dry_run or not args.apply:
            report["auto"]["cadence"] = {"status": "dry_run_or_no_apply"}
        else:
            # 間隔ゲート付き差分更新。--mark-prompted はパートナー確認用なので付けない
            r = run_py(
                [
                    str(REPO / "scripts" / "jarvis_vpoint_cadence_check.py"),
                    "--force",
                ],
                timeout=60,
            )
            report["auto"]["cadence"] = {
                "ok": r.get("ok"),
                "stdout_empty": not (r.get("stdout_tail") or "").strip(),
            }
            cadence = load_json(CADENCE_PATH)

    # --- Auto C: teiki when due ---
    teiki_due = False
    if not args.skip_teiki and not teiki.get("disabled"):
        last = parse_iso(str(teiki.get("last_check_at") or ""))
        interval = int(teiki.get("interval_days") or 7)
        if last is None or now - last >= timedelta(days=interval):
            teiki_due = True
        report["auto"]["teiki"] = {"due": teiki_due, "interval_days": interval}
        if teiki_due:
            if args.dry_run or not args.apply:
                report["auto"]["teiki"]["status"] = "dry_run_or_no_apply"
            else:
                r = run_py(
                    [
                        str(REPO / "scripts" / "jarvis_teiki_barai_chance.py"),
                        "--run",
                        "--push",
                    ],
                    timeout=300,
                )
                report["auto"]["teiki"]["result"] = {
                    "ok": r.get("ok"),
                    "stderr_tail": r.get("stderr_tail"),
                }
                if not r.get("ok"):
                    report["auto"]["teiki"]["fallback"] = (
                        "ブラウザ失敗 → Jarvis促し（『テイチャン回して』）"
                    )
                teiki = load_json(TEIKI_PATH)

    # --- Manual prompts ---
    # refresh grant_source if we didn't build
    if not grant_source:
        rc = monthly.get("last_result_c") or {}
        gs = rc.get("grant_summary") or {}
        grant_source = str(gs.get("source_note") or "")

    asks = build_jarvis_asks(
        env=env,
        monthly=monthly,
        cadence=cadence,
        teiki=teiki,
        now=now,
        grant_built=grant_built,
        grant_source=grant_source,
    )
    report["manual"]["jarvis_asks"] = asks
    report["manual"]["split"] = {
        "auto_ok": [
            "付与サマリ生成（既存履歴／監査フォールバック）",
            "cadence open_actions の差分整理",
            "テイチャン確認・抽選（Vpass・interval到来時）",
            "ダッシュボード /vpoint 反映",
        ],
        "needs_jarvis_user": [
            "Tサイト履歴の新規取得（メールOTP）",
            "Visaタッチ実機確認・Wallet設定",
            "選べる特典／NISA評価額帯の設定変更",
            "Vpass深い明細監査の再実施",
            "テイチャン各サービスの公式サイトでのカード変更",
        ],
    }

    if args.apply and not args.dry_run:
        monthly = load_json(MONTHLY_PATH)
        monthly["last_routine_at"] = now_iso()
        monthly["jarvis_asks"] = asks
        monthly["routine_split"] = report["manual"]["split"]
        # PDCA ボード（良かった点／要改善／次の一手）
        pdca_r = run_py(
            [str(REPO / "scripts" / "jarvis_vpoint_pdca.py"), "--apply"],
            timeout=60,
        )
        report["auto"]["pdca"] = {"ok": pdca_r.get("ok")}
        monthly = load_json(MONTHLY_PATH)
        report["manual"]["pdca_board"] = monthly.get("pdca_board")
        save_json(MONTHLY_PATH, monthly)

        # human-readable block for chat / logs
        lines = [
            "---",
            "📎 Vポイント定例",
            f"- 対象付与月: {target}",
            f"- ウィンドウC: {'該当' if in_window_c(now) else '対象外'}",
            f"- 付与サマリ自動: {'実施' if grant_built else ('予定のみ' if need_grant else 'スキップ')}",
        ]
        if asks:
            lines.append("- Jarvis確認が必要なこと:")
            for a in asks[:8]:
                lines.append(f"  · [{a['level']}] {a['text']}")
        else:
            lines.append("- Jarvis確認: なし（自動範囲のみ）")
        lines.append("---")
        report["chat_block"] = "\n".join(lines)
        # PDCA ブロックも末尾に（stdout に二重でも可）
        if monthly.get("pdca_board"):
            pdca_out = run_py([str(REPO / "scripts" / "jarvis_vpoint_pdca.py")], timeout=30)
            if pdca_out.get("stdout_tail"):
                # format_block は先頭〜なので再実行ではなく board から短く
                board = monthly["pdca_board"]
                plines = ["", "📎 PDCA 要約"]
                for w in (board.get("wins") or [])[:3]:
                    plines.append(f"  ✅ {w.get('title')}")
                for g in (board.get("gaps") or [])[:3]:
                    plines.append(f"  ⚠️ {g.get('title')}")
                for n in board.get("next_actions") or []:
                    plines.append(f"  → {n.get('title')}: {n.get('how')}")
                report["chat_block"] += "\n" + "\n".join(plines)
        print(report["chat_block"])
        print()

    if args.push and args.apply and not args.dry_run:
        report["push"] = run_py(
            [str(REPO / "scripts" / "jarvis_dashboard_push.py"), "--watch-only"],
            timeout=180,
        )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
