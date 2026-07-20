"""銀行アダプタ登録。"""
from __future__ import annotations

from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"


def load_bank_config(bank_id: str) -> dict:
    if bank_id.startswith("mufg"):
        bank_id = "mufg_jaccs"
    if "resona" in bank_id:
        bank_id = "resona"
    path = CONFIG_DIR / f"{bank_id}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"銀行設定がありません: {bank_id} ({path})")
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_banks() -> list[str]:
    return [p.stem for p in sorted(CONFIG_DIR.glob("*.yaml")) if not p.name.startswith("_")]


def expand_path(p: str) -> Path:
    return Path(p.replace("~/", str(Path.home()) + "/")).expanduser()
