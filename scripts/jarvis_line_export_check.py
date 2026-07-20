#!/usr/bin/env python3
"""
Jarvis: LINE 公式エクスポート（Phase C）— ルート別の最終取込からの経過日数を判定し、促しブロックを出力。

使い方:
  python scripts/jarvis_line_export_check.py
  python scripts/jarvis_line_export_check.py --json
  python scripts/jarvis_line_export_check.py --mark-prompted
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from jarvis_line_export_state import load_state, mark_prompted, save_state

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
ONEDRIVE_PARTNER = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C2_ルーティン作業/26_パートナー社への相談"
)
LINE_HEALTH_PATH = REPO / "line_unofficial_poc" / ".line_auth" / ".chrline_line_health_last.json"
INBOX_PROCESSED_JSON = Path.home() / ".cursor" / "line_export_inbox_processed.json"

SUGGEST_DAYS = 14
ASK_DAYS = 30
PROMPT_COOLDOWN_DAYS = 7
DEFAULT_INTERVAL_DAYS = 30

HEADING_DATE_RE = re.compile(r"^### (\d{4}/\d{2}/\d{2})")


@dataclass
class ExportRoute:
    id: str
    folder: str
    display_name: str
    group_label: str
    filename_hints: list[str] = field(default_factory=list)


@dataclass
class RouteCheck:
    route_id: str
    label: str
    days_since: int | None
    last_import_at: str | None
    level: str  # info | suggest | ask
    reasons: list[str] = field(default_factory=list)
    placeholder_blocks: int = 0
    skip_prompt: bool = False


def partner_base() -> Path:
    env = (__import__("os").environ.get("LINE_EXPORT_COMMON_DIR") or "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        if p.is_dir():
            return p if p.name != "000_共通" else p.parent
    if ONEDRIVE_PARTNER.is_dir():
        return ONEDRIVE_PARTNER.resolve()
    return (REPO / "215_kamiooya" / "C2_ルーティン作業" / "26_パートナー社への相談").resolve()


def routes_yaml_path() -> Path:
    common = partner_base() / "000_共通"
    p = common / "line_export_routes.yaml"
    if p.is_file():
        return p.resolve()
    ex = common / "line_export_routes.example.yaml"
    if ex.is_file():
        return ex.resolve()
    return p


def load_routes() -> list[ExportRoute]:
    path = routes_yaml_path()
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw = data.get("routes") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        return []
    out: list[ExportRoute] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        rid = str(item.get("id") or "").strip()
        folder = str(item.get("folder") or "").strip()
        if not rid or not folder:
            continue
        hints = item.get("filename_hints") or []
        if isinstance(hints, str):
            hints = [hints]
        out.append(
            ExportRoute(
                id=rid,
                folder=folder,
                display_name=str(item.get("display_name") or folder).strip(),
                group_label=str(item.get("group_label") or "").strip(),
                filename_hints=[str(h).strip() for h in hints if str(h).strip()],
            )
        )
    return out


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


def _parse_md_date(s: str) -> datetime | None:
    try:
        return datetime.strptime(s, "%Y/%m/%d").replace(tzinfo=JST)
    except ValueError:
        return None


def export_root_dir() -> Path:
    return partner_base() / "000_共通" / "LINE公式エクスポート"


def _latest_from_processed_folder(route: ExportRoute) -> datetime | None:
    root = export_root_dir() / "processed"
    if not root.is_dir():
        return None
    best: datetime | None = None
    hints = [h.lower() for h in route.filename_hints]
    for day_dir in root.iterdir():
        if not day_dir.is_dir():
            continue
        for f in day_dir.iterdir():
            if not f.is_file():
                continue
            name = f.name.lower()
            if hints and not any(h in name for h in hints):
                continue
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=JST)
            except OSError:
                continue
            if best is None or mtime > best:
                best = mtime
    return best


def _latest_from_inbox_json(route: ExportRoute) -> datetime | None:
    if not INBOX_PROCESSED_JSON.is_file():
        return None
    try:
        data = json.loads(INBOX_PROCESSED_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, dict):
        return None
    best: datetime | None = None
    for meta in files.values():
        if not isinstance(meta, dict):
            continue
        if meta.get("folder") != route.folder:
            continue
        if meta.get("status") not in ("imported", "repaired", "skipped_duplicate"):
            continue
        dt = _parse_iso(str(meta.get("ts") or ""))
        if dt and (best is None or dt > best):
            best = dt
    return best


def _md_path(route: ExportRoute) -> Path:
    return partner_base() / route.folder / "5.やり取り.md"


def _health_folder_key(route: ExportRoute) -> str:
    if route.folder.startswith("815_"):
        return route.folder.split("/")[-1]
    return route.folder.split("/")[0]


def _load_line_health() -> dict:
    if not LINE_HEALTH_PATH.is_file():
        return {}
    try:
        return json.loads(LINE_HEALTH_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _latest_from_md(route: ExportRoute) -> datetime | None:
    md = _md_path(route)
    if not md.is_file():
        return None
    markers = ("公式エクスポート", "LINE公式エクスポート")
    label_bits = [route.group_label, route.display_name, route.folder.split("/")[-1]]
    label_bits = [b for b in label_bits if b]
    best: datetime | None = None
    try:
        text = md.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        if not any(m in line for m in markers):
            continue
        if label_bits and not any(b in line for b in label_bits):
            continue
        m = HEADING_DATE_RE.match(line.strip())
        if not m:
            continue
        dt = _parse_md_date(m.group(1))
        if dt and (best is None or dt > best):
            best = dt
    return best


def resolve_last_import(route: ExportRoute, state: dict) -> tuple[datetime | None, str]:
    route_state = (state.get("routes") or {}).get(route.id) or {}
    candidates: list[tuple[datetime, str]] = []
    for source, dt in (
        ("state", _parse_iso(route_state.get("last_import_at"))),
        ("inbox_json", _latest_from_inbox_json(route)),
        ("processed", _latest_from_processed_folder(route)),
        ("md", _latest_from_md(route)),
    ):
        if dt is not None:
            candidates.append((dt, source))
    if not candidates:
        return None, "none"
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0]


def _days_since(dt: datetime | None, now: datetime) -> int | None:
    if dt is None:
        return None
    return max(0, (now.date() - dt.date()).days)


def _prompt_cooldown_active(route_state: dict, now: datetime) -> bool:
    last = _parse_iso(route_state.get("last_prompted_at"))
    if last is None:
        return False
    return (now.date() - last.date()).days < PROMPT_COOLDOWN_DAYS


def check_route(route: ExportRoute, *, now: datetime, state: dict, health: dict) -> RouteCheck:
    route_state = (state.get("routes") or {}).get(route.id) or {}
    last_dt, source = resolve_last_import(route, state)
    days = _days_since(last_dt, now)
    interval = int(route_state.get("interval_days") or DEFAULT_INTERVAL_DAYS)
    ask_threshold = max(ASK_DAYS, interval)
    suggest_threshold = min(SUGGEST_DAYS, max(7, ask_threshold // 2))

    health_key = _health_folder_key(route)
    by_folder = health.get("by_folder") or {}
    placeholders = int(by_folder.get(health_key, 0) or 0)
    textual_rate = health.get("textual_rate_pct")
    queue_total = int(health.get("queue_total", 0) or 0)

    label = route.group_label or route.display_name
    reasons: list[str] = []
    level = "info"

    if days is None:
        reasons.append("取込記録なし")
        level = "suggest"
    elif days >= ask_threshold:
        reasons.append(f"前回から {days} 日（{ask_threshold} 日以上）")
        level = "ask"
    elif days >= suggest_threshold:
        reasons.append(f"前回から {days} 日")
        level = "suggest"

    if placeholders > 0:
        reasons.append(f"MDプレースホルダー {placeholders} 件")
        level = "ask"
    elif textual_rate == 0.0 and days is not None and days >= suggest_threshold:
        reasons.append("CHRLINE 本文復号 0%")
        if level == "info":
            level = "suggest"
        if days >= ask_threshold:
            level = "ask"

    if queue_total >= 30 and health_key in ("104_LEAF", "103_Tcell", "東海飲み会幹事やりとり"):
        reasons.append(f"retry キュー {queue_total} 件（全体）")
        if level == "info" and days is not None and days >= suggest_threshold:
            level = "suggest"

    skip = _prompt_cooldown_active(route_state, now) and level in ("suggest", "ask")

    return RouteCheck(
        route_id=route.id,
        label=label,
        days_since=days,
        last_import_at=last_dt.isoformat(timespec="seconds") if last_dt else None,
        level=level,
        reasons=reasons,
        placeholder_blocks=placeholders,
        skip_prompt=skip,
    )


def run_check(*, now: datetime | None = None) -> dict:
    now = now or datetime.now(JST)
    state = load_state()
    if state.get("disabled"):
        return {"disabled": True, "routes": [], "prompts": [], "monthly_window": _monthly_window(now)}

    routes = load_routes()
    health = _load_line_health()
    checks = [check_route(r, now=now, state=state, health=health) for r in routes]
    prompts = [c for c in checks if c.level in ("suggest", "ask") and not c.skip_prompt]
    return {
        "disabled": False,
        "generated_at": now.isoformat(timespec="seconds"),
        "monthly_window": _monthly_window(now),
        "routes": [c.__dict__ for c in checks],
        "prompts": [c.__dict__ for c in prompts],
        "line_health": {
            "textual_rate_pct": health.get("textual_rate_pct"),
            "queue_total": health.get("queue_total"),
        },
    }


def _monthly_window(now: datetime) -> bool:
    return 1 <= now.day <= 5


def render_block(result: dict) -> str:
    if result.get("disabled"):
        return ""
    prompts = result.get("prompts") or []
    if not prompts and not result.get("monthly_window"):
        return ""

    lines = ["---", "📎 LINE 公式エクスポート"]
    if not prompts:
        lines.append("- 現時点、強い促し対象はありません（経過日数・プレースホルダーを確認済み）")
        lines.append(
            "- 手順: LINE → トーク履歴を送信 → EmailMe（matsuno.estate@gmail.com）または inbox に .txt 保存"
        )
        return "\n".join(lines)

    has_ask = any(p.get("level") == "ask" for p in prompts)
    if has_ask:
        lines.append("- **推奨**: 以下のトークはエクスポート反映をお願いします（CHRLINE だけでは本文が不足しがちです）")
    else:
        lines.append("- **任意**: 本文が必要ならエクスポートをお願いします")

    for p in prompts:
        label = p.get("label") or p.get("route_id")
        days = p.get("days_since")
        day_part = f"前回取込から **{days} 日**" if days is not None else "取込記録なし"
        if p.get("level") == "ask" and days is not None and days >= ASK_DAYS:
            day_part += "（**1ヶ月超**）"
        reason = " / ".join(p.get("reasons") or [])
        lines.append(f"  - **{label}**: {day_part} — {reason}")

    lines.extend(
        [
            "- 手順: LINE アプリ → 設定 → トーク → **トーク履歴を送信** → EmailMe または Mac で inbox へ",
            "  - inbox: `000_共通/LINE公式エクスポート/inbox/`",
            "- 反映後「保存した」と一声ください → パートナー確認で取込します",
            "---",
        ]
    )
    return "\n".join(lines)


def bootstrap_state_from_md() -> int:
    """MD/processed から last_import_at を state に初回同期。"""
    state = load_state()
    routes = load_routes()
    updated = 0
    for route in routes:
        last_dt, _ = resolve_last_import(route, state)
        if last_dt is None:
            continue
        entry = state.setdefault("routes", {}).setdefault(route.id, {})
        if entry.get("last_import_at"):
            continue
        entry["route_id"] = route.id
        entry["folder"] = route.folder
        entry["last_import_at"] = last_dt.isoformat(timespec="seconds")
        entry["last_import_source"] = "bootstrap"
        updated += 1
    if updated:
        save_state(state)
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="LINE 公式エクスポート促し判定")
    parser.add_argument("--json", action="store_true", help="JSON のみ stdout")
    parser.add_argument("--mark-prompted", action="store_true", help="表示した促しの last_prompted_at を更新")
    parser.add_argument("--bootstrap", action="store_true", help="MD/processed から state を初回同期")
    args = parser.parse_args()

    if args.bootstrap:
        n = bootstrap_state_from_md()
        if not args.json:
            print(f"# bootstrap: {n} ルートを state に同期", file=sys.stderr)
        return 0

    result = run_check()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    block = render_block(result)
    if block:
        print(block)
    if args.mark_prompted and result.get("prompts"):
        mark_prompted([p["route_id"] for p in result["prompts"]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
