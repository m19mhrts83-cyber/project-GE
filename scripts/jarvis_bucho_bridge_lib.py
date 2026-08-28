"""Jarvis ↔ 部長 Drive ボックス共通（admin 【with Grok bot】）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

REPO = Path(__file__).resolve().parents[1]
CFG_PATH = REPO / "config" / "kurashift_grok_bridge_folders.yaml"
STATE_DIR = REPO / ".jarvis_state"
INBOX_STATE_PATH = STATE_DIR / "grok_bridge_inbox.json"

SKIP_NAME_PREFIXES = ("00_", ".", ".keep")


def load_bridge_cfg() -> dict[str, Any]:
    if yaml is None:
        raise SystemExit("PyYAML required")
    if not CFG_PATH.is_file():
        raise FileNotFoundError(f"missing {CFG_PATH}")
    data = yaml.safe_load(CFG_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("bridge yaml must be a mapping")
    return data


def bridge_root(cfg: dict[str, Any] | None = None) -> Path:
    cfg = cfg or load_bridge_cfg()
    root = Path(str(cfg.get("local_root") or "")).expanduser()
    if not root.is_dir():
        raise FileNotFoundError(f"bridge root missing: {root}")
    return root


def folder(name: str, cfg: dict[str, Any] | None = None) -> Path:
    """name: inbox_from_grok | outbox_to_grok | shared_working | archive | outbox_to_teams_root"""
    cfg = cfg or load_bridge_cfg()
    folders = cfg.get("folders") or {}
    rel = folders.get(name)
    if not rel:
        raise KeyError(f"folders.{name} missing in bridge yaml")
    p = bridge_root(cfg) / str(rel)
    p.mkdir(parents=True, exist_ok=True)
    return p


def team_folder(team_id: str, cfg: dict[str, Any] | None = None) -> Path:
    """outbox_to_teams/{team_id}/ — L3 部長／統括／天気Bot 用"""
    cfg = cfg or load_bridge_cfg()
    teams = cfg.get("outbox_to_teams") or {}
    rel_name = teams.get(team_id)
    if not rel_name:
        raise KeyError(f"outbox_to_teams.{team_id} missing in bridge yaml")
    root_rel = (cfg.get("folders") or {}).get("outbox_to_teams_root", "outbox_to_teams")
    p = bridge_root(cfg) / str(root_rel) / str(rel_name)
    p.mkdir(parents=True, exist_ok=True)
    return p


def outbox_dir_for_target(target: str, cfg: dict[str, Any] | None = None) -> Path:
    """target → 書込先。hawk=20_outbox_to_grok、他=outbox_to_teams/{team}/"""
    cfg = cfg or load_bridge_cfg()
    targets = cfg.get("targets") or {}
    spec = targets.get(target)
    if not spec:
        raise KeyError(f"targets.{target} missing in bridge yaml")
    folder_key = spec.get("folder")
    if folder_key:
        return folder(str(folder_key), cfg)
    team = spec.get("team")
    if team:
        return team_folder(str(team), cfg)
    raise ValueError(f"targets.{target} has neither folder nor team")


def list_target_ids(cfg: dict[str, Any] | None = None) -> list[str]:
    cfg = cfg or load_bridge_cfg()
    targets = cfg.get("targets") or {}
    return sorted(str(k) for k in targets)


def is_queue_file(path: Path) -> bool:
    if not path.is_file():
        return False
    name = path.name
    if name.startswith(SKIP_NAME_PREFIXES) or name == ".keep.txt":
        return False
    return path.suffix.lower() in {".md", ".txt"}


def list_queue_files(dir_path: Path) -> list[Path]:
    if not dir_path.is_dir():
        return []
    files = [p for p in dir_path.iterdir() if is_queue_file(p)]
    return sorted(files, key=lambda p: p.stat().st_mtime)


def sanitize_title(title: str, max_len: int = 60) -> str:
    t = (title or "memo").strip()
    for ch in '/\\:*?"<>|\n\r\t':
        t = t.replace(ch, "_")
    t = "_".join(t.split())
    return (t[:max_len] or "memo").rstrip("._")
