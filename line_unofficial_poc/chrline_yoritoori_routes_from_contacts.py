#!/usr/bin/env python3
"""連絡先一覧.yaml から line_direct_chat_mid 付きパートナーを CHRLINE ターゲットとして読む。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ONEDRIVE_CONTACTS = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C2_ルーティン作業/26_パートナー社への相談/000_共通/連絡先一覧.yaml"
)
_REPO_CONTACTS = (
    _REPO_ROOT
    / "215_kamiooya"
    / "C2_ルーティン作業"
    / "26_パートナー社への相談"
    / "000_共通"
    / "連絡先一覧.yaml"
)
_ONEDRIVE_PARTNER_BASE = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C2_ルーティン作業/26_パートナー社への相談"
)


@dataclass(frozen=True)
class DirectChatTarget:
    yoritoori_md: Path
    org_label: str
    chat_mid: str
    peer_label: str


def default_contacts_yaml() -> Path:
    env = (__import__("os").environ.get("YORITOORI_CONTACTS_YAML") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    if _ONEDRIVE_CONTACTS.is_file():
        return _ONEDRIVE_CONTACTS.resolve()
    return _REPO_CONTACTS.resolve()


def _partner_yoritoori_md(folder: str) -> Path | None:
    folder = (folder or "").strip()
    if not folder:
        return None
    p = _ONEDRIVE_PARTNER_BASE / folder / "5.やり取り.md"
    if p.is_file():
        return p.resolve()
    p2 = _REPO_ROOT / "215_kamiooya" / "C2_ルーティン作業" / "26_パートナー社への相談" / folder / "5.やり取り.md"
    return p2.resolve() if p2.is_file() else None


def load_direct_chat_targets(
    contacts_path: Path | None = None,
    *,
    exclude_mids: set[str] | None = None,
) -> list[DirectChatTarget]:
    """line_direct_chat_mid が設定されたパートナーの 1:1 ターゲット一覧。"""
    path = contacts_path or default_contacts_yaml()
    if not path.is_file():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return []
    partners = data.get("partners") if isinstance(data, dict) else data
    if not isinstance(partners, list):
        return []

    skip = {m.strip() for m in (exclude_mids or set()) if m}
    out: list[DirectChatTarget] = []
    seen_mids: set[str] = set()

    for p in partners:
        if not isinstance(p, dict):
            continue
        mid = str(p.get("line_direct_chat_mid") or "").strip()
        if not mid or mid in skip or mid in seen_mids:
            continue
        folder = str(p.get("folder") or "").strip()
        md = _partner_yoritoori_md(folder)
        if md is None:
            continue
        name = str(p.get("name") or folder or "LINE").strip()
        line_label = str(p.get("line") or "").strip()
        peer = line_label.split("/")[0].strip() if line_label else name
        org = name
        out.append(
            DirectChatTarget(
                yoritoori_md=md,
                org_label=org,
                chat_mid=mid,
                peer_label=peer or name,
            )
        )
        seen_mids.add(mid)
    return out
