"""Jarvis: LINE 公式エクスポート（Phase C）リマインダー用 state。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_PATH = REPO / ".jarvis_state" / "line_export_reminder.json"
EXAMPLE_PATH = REPO / ".jarvis_state" / "line_export_reminder.example.json"


def _now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def default_state() -> dict:
    return {
        "disabled": False,
        "routes": {},
    }


def load_state() -> dict:
    if STATE_PATH.is_file():
        try:
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("disabled", False)
                data.setdefault("routes", {})
                return data
        except (json.JSONDecodeError, OSError):
            pass
    if EXAMPLE_PATH.is_file():
        try:
            data = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("disabled", False)
                data.setdefault("routes", {})
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return default_state()


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def record_import(*, route_id: str, folder: str, source: str = "inbox") -> None:
    """取込成功時に last_import_at を更新。"""
    rid = (route_id or "").strip()
    if not rid:
        return
    state = load_state()
    routes = state.setdefault("routes", {})
    entry = routes.setdefault(rid, {})
    entry["route_id"] = rid
    entry["folder"] = folder
    entry["last_import_at"] = _now_iso()
    entry["last_import_source"] = source
    save_state(state)


def mark_prompted(route_ids: list[str]) -> None:
    state = load_state()
    routes = state.setdefault("routes", {})
    ts = _now_iso()
    for rid in route_ids:
        rid = (rid or "").strip()
        if not rid:
            continue
        routes.setdefault(rid, {})["last_prompted_at"] = ts
    save_state(state)
