#!/usr/bin/env python3
"""Gmail OAuth token のスコープ・refresh 有無を一覧し、再認証が必要なものを示す。

  cd ~/git-repos && ~/selenium_env/venv/bin/python scripts/jarvis_gmail_token_health.py
  cd ~/git-repos && ~/selenium_env/venv/bin/python scripts/jarvis_gmail_token_health.py --mark-prompted
  cd ~/git-repos && ~/selenium_env/venv/bin/python scripts/jarvis_gmail_token_health.py --quiet-ok

相乗り: 朝オープン（morning_mac_refresh）／パートナー確認前半末尾。
停止: JARVIS_GMAIL_TOKEN_HEALTH_DISABLE=1 または state disabled。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya/C1_cursor/1b_Cursorマニュアル"
STATE_PATH = REPO / ".jarvis_state" / "gmail_token_health.json"
JST = timezone(timedelta(hours=9))

sys.path.insert(0, str(MANUAL))

from gmail_api_scopes import (  # noqa: E402
    GMAIL_SCOPES_215,
    granted_scopes_from_token_record,
    token_satisfies_215_scopes,
    token_satisfies_read_modify_scopes,
)

TOKENS = (
    ("admin", "token_livingsupport.json"),
    ("estate", "token_estate.json"),
    ("m19m", "token_m19m.json"),
    ("jarvis", "token_jarvis.json"),
    ("m19m_legacy", "token.json"),
    ("calendar", "token_calendar.json"),
)

REAUTH_CMD = (
    "cd ~/git-repos/215_kamiooya/C1_cursor/1b_Cursorマニュアル && "
    "export YORITOORI_BASE_PATH="
    '"$HOME/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/'
    'C2_ルーティン作業/26_パートナー社への相談" && '
    "export GMAIL_TOKEN_PATHS={token} && "
    "~/selenium_env/venv/bin/python gmail_to_yoritoori.py --include-read"
)

REAUTH_ESTATE_SEND = (
    "cd ~/git-repos/215_kamiooya/C1_cursor/1b_Cursorマニュアル && "
    "~/selenium_env/venv/bin/python reauth_estate_gmail_send.py"
)

# 促しすぎ防止（重大 NG は短め）
PROMPT_COOLDOWN_HOURS_OK = 24
PROMPT_COOLDOWN_HOURS_NG = 6


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _now() -> datetime:
    return datetime.now(JST)


def _load_state() -> dict:
    if not STATE_PATH.is_file():
        return {
            "disabled": False,
            "last_checked_at": None,
            "last_prompted_at": None,
            "last_issues": [],
            "ng_events": [],
        }
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"disabled": False}


def _save_state(data: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
        return dt.astimezone(JST)
    except Exception:
        return None


def collect_health() -> tuple[list[str], list[str], bool]:
    """Returns (lines, issues, estate_send_missing)."""
    lines: list[str] = ["📎 Gmail token ヘルス"]
    issues: list[str] = []
    estate_send_missing = False

    for label, name in TOKENS:
        path = MANUAL / name
        if not path.is_file():
            lines.append(f"- {label} ({name}): なし")
            continue
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            lines.append(f"- {label}: 読取失敗 ({e})")
            issues.append(label)
            continue
        granted = sorted(granted_scopes_from_token_record(d))
        refresh = bool(d.get("refresh_token"))
        if label == "calendar":
            ok = "https://www.googleapis.com/auth/calendar.events" in granted
            status = "OK" if ok else "要再認証"
            lines.append(
                f"- {label} ({name}): {status} · refresh={'あり' if refresh else 'なし'}"
            )
            if not ok:
                issues.append(label)
                lines.append(
                    "    再認証: google_calendar_create.py "
                    "--auth-console --login-hint admin@livingsupport-matsu.co.jp"
                )
            continue
        full = token_satisfies_215_scopes(d)
        read_mod = token_satisfies_read_modify_scopes(d)
        status = (
            "OK"
            if full
            else (
                "read/modifyのみ（取込可・送信は要再同意）"
                if read_mod
                else "要再認証"
            )
        )
        lines.append(
            f"- {label} ({name}): {status} · refresh={'あり' if refresh else 'なし'} · scopes={len(granted)}"
        )
        missing = set(GMAIL_SCOPES_215) - set(granted)
        if missing:
            for m in sorted(missing):
                lines.append(f"    不足: {m.split('/')[-1]}")
            if label == "estate" and not full:
                estate_send_missing = True
                issues.append("estate_send")
                lines.append(
                    "    ※取込は readonly でも可。パートナー送信にはフルスコープ再同意が必要。"
                )
                lines.append(f"    → {REAUTH_ESTATE_SEND}")
            elif not full:
                issues.append(label)
        if not refresh:
            issues.append(label)

    if issues:
        lines.append("")
        lines.append("⚠️ 再認証（ブラウザで対象アカウントを選んで許可）:")
        for label, name in TOKENS:
            if label in issues and (MANUAL / name).is_file():
                lines.append(REAUTH_CMD.format(token=name))
        if estate_send_missing or "estate_send" in issues:
            lines.append("")
            lines.append("⚠️ estate 送信用（readonly+modify+send を一度に付与）:")
            lines.append(REAUTH_ESTATE_SEND)
            lines.append(
                "   ※必ず reauth_estate_gmail_send.py（取込の狭い再同意では send が戻らない）"
            )
        lines.append("")
        lines.append(
            "ヒント: GCP OAuth は本番公開済みなら7日切れは起きにくい。"
            " 取込は token に付いている最小スコープで動く（readonly 単独でもブラウザ不要）。"
            " 送信はフルスコープ必須。保存時は既存 gmail.send を落とさない。"
        )
    else:
        lines.append("")
        lines.append("判定: 取込・送信に必要な token は OK")

    return lines, issues, estate_send_missing


def _should_suppress(state: dict, issues: list[str], *, force: bool) -> bool:
    if force:
        return False
    last = _parse_iso(state.get("last_prompted_at"))
    if not last:
        return False
    hours = PROMPT_COOLDOWN_HOURS_NG if issues else PROMPT_COOLDOWN_HOURS_OK
    return (_now() - last) < timedelta(hours=hours) and list(
        state.get("last_issues") or []
    ) == list(issues)


def _record_ng_event(state: dict, issues: list[str]) -> None:
    """社員化判断用に NG 履歴を残す（7日窓）。"""
    if not issues:
        return
    events = list(state.get("ng_events") or [])
    events.append(
        {
            "at": _now().isoformat(timespec="seconds"),
            "issues": list(issues),
        }
    )
    cutoff = _now() - timedelta(days=7)
    kept = []
    for ev in events:
        at = _parse_iso(ev.get("at") if isinstance(ev, dict) else None)
        if at and at >= cutoff:
            kept.append(ev)
    state["ng_events"] = kept[-20:]
    state["ng_count_7d"] = len(kept)


def main() -> int:
    ap = argparse.ArgumentParser(description="Gmail token ヘルスチェック")
    ap.add_argument(
        "--mark-prompted",
        action="store_true",
        help="促し日時を state に記録（朝・パートナー確認相乗り）",
    )
    ap.add_argument(
        "--quiet-ok",
        action="store_true",
        help="問題なしのとき出力しない（パートナー確認向け）",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="cooldown / disable を無視して出力",
    )
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if _truthy("JARVIS_GMAIL_TOKEN_HEALTH_DISABLE") and not args.force:
        if args.json:
            print(json.dumps({"disabled": True, "issues": []}, ensure_ascii=False))
        return 0

    state = _load_state()
    if state.get("disabled") and not args.force:
        if args.json:
            print(json.dumps({"disabled": True, "issues": []}, ensure_ascii=False))
        return 0

    lines, issues, estate_send_missing = collect_health()
    state["last_checked_at"] = _now().isoformat(timespec="seconds")
    _record_ng_event(state, issues)

    if args.json:
        print(
            json.dumps(
                {
                    "issues": issues,
                    "estate_send_missing": estate_send_missing,
                    "ng_count_7d": state.get("ng_count_7d", 0),
                    "lines": lines,
                },
                ensure_ascii=False,
            )
        )
        if args.mark_prompted:
            state["last_prompted_at"] = _now().isoformat(timespec="seconds")
            state["last_issues"] = list(issues)
            _save_state(state)
        else:
            _save_state(state)
        return 1 if issues else 0

    if _should_suppress(state, issues, force=args.force):
        _save_state(state)
        return 1 if issues else 0

    if args.quiet_ok and not issues:
        if args.mark_prompted:
            state["last_prompted_at"] = _now().isoformat(timespec="seconds")
            state["last_issues"] = []
            _save_state(state)
        else:
            _save_state(state)
        return 0

    print("\n".join(lines))
    if args.mark_prompted:
        state["last_prompted_at"] = _now().isoformat(timespec="seconds")
        state["last_issues"] = list(issues)
    _save_state(state)
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
