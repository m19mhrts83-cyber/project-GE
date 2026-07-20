"""環境変数・car_loan.json の読み書き。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = REPO_ROOT / ".env.jarvis_private"
STATE_FILE = REPO_ROOT / ".jarvis_state" / "car_loan.json"


def load_env(path: Path = ENV_FILE) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.is_file():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip().strip('"').strip("'")
        env[key.strip()] = val
    return env


def load_state(path: Path = STATE_FILE) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(data: dict, path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def receipt_from_state(state_app_id: str, env: dict[str, str], state: dict) -> str:
    for app in state.get("applications", []):
        if app.get("id") == state_app_id and app.get("receipt_number"):
            return str(app["receipt_number"])
    return ""


def update_application_status(state_app_id: str, status: str, note: str = "") -> None:
    state = load_state()
    today = date.today().isoformat()
    for app in state.get("applications", []):
        if app.get("id") == state_app_id:
            app["status"] = status
            if status == "documents_submitted":
                app["documents_submitted_at"] = today
            if note:
                app["pre_result"] = note
            break
    save_state(state)
