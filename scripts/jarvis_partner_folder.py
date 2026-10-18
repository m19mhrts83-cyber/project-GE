#!/usr/bin/env python3
"""パートナー社フォルダ採番ヘルパー（P接頭辞＋旧形式互換）。

正本: P101_ホームプランナー（Partner）
互換: 101_ホームプランナー（移行期・古いパス／state）

物件ハブ A1_… と AI社員 311（数字のみ）はこのモジュールの対象外。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

# パス区切り付き抽出（215_神大家… 等の親フォルダ誤検出を防ぐ）
FOLDER_RE = re.compile(r"[/\\](?P<code>P?\d{3}_[^/\\]+)[/\\]")
# フォルダ名単体（dir.name）
FOLDER_NAME_RE = re.compile(r"^P?\d{3}_.+$")
# 3桁コード本体（P付きでも無しでも）
CODE_RE = re.compile(r"^P?(\d{3})_(.+)$")

# よく使う固定フォルダ（新形式が正。resolve_* は旧形式も返す）
LEAF_FOLDER = "P104_LEAF"
TCELL_FOLDER = "P103_Tcell"
KANJI_FOLDER = "P823_名古屋幹事グループ"
OPENCHAT_FOLDER = "P815_神大家オプチャ"

# パス中の誤検出（215_神・大家さん倶楽部 / 000_共通）
_FALSE_POSITIVE_PREFIXES = ("215_", "000_", "P000_")


def is_partner_folder_name(name: str) -> bool:
    """`P101_…` / `101_…` 形式か（A1_ / 000_共通 / 215_親 は False）。"""
    s = (name or "").strip()
    if not FOLDER_NAME_RE.match(s):
        return False
    if s.startswith(_FALSE_POSITIVE_PREFIXES):
        return False
    return True


def normalize_folder(name: str) -> str:
    """旧 `101_…` → `P101_…`。既に P 付き／非対象はそのまま。"""
    s = (name or "").strip()
    if not s:
        return s
    m = CODE_RE.match(s)
    if not m:
        return s
    return f"P{m.group(1)}_{m.group(2)}"


def legacy_folder(name: str) -> str:
    """`P101_…` → `101_…`。既に旧形式ならそのまま。"""
    s = (name or "").strip()
    if not s:
        return s
    m = CODE_RE.match(s)
    if not m:
        return s
    return f"{m.group(1)}_{m.group(2)}"


def folder_aliases(name: str) -> list[str]:
    """照合用に新旧両方（重複なし・入力順優先）。"""
    s = (name or "").strip()
    if not s:
        return []
    out: list[str] = []
    for cand in (s, normalize_folder(s), legacy_folder(s)):
        if cand and cand not in out:
            out.append(cand)
    return out


def codes_from_path(path: Path | str) -> list[str]:
    """パス文字列からパートナーフォルダ候補を抽出（出現順・誤検出除外）。"""
    return [
        m.group("code")
        for m in FOLDER_RE.finditer(str(path))
        if is_partner_folder_name(m.group("code"))
    ]


def partner_hint_from_path(path: Path | str) -> str:
    """パス中のパートナーフォルダ（末尾優先＝26_配下）。無ければ親名。"""
    p = Path(path)
    codes = codes_from_path(p)
    if codes:
        return codes[-1]
    parent = p.parent.name if p.parent.name else ""
    if is_partner_folder_name(parent):
        return parent
    return parent


def lookup_partner_by_folder(
    folder: str,
    partners: Iterable[dict],
) -> dict | None:
    """連絡先 partners から folder（旧新どちらでも）で1件。"""
    aliases = set(folder_aliases(folder))
    for p in partners:
        if not isinstance(p, dict):
            continue
        f = str(p.get("folder") or "").strip()
        if f and f in aliases:
            return p
        # YAML が新・候補が旧、または逆
        if f and set(folder_aliases(f)) & aliases:
            return p
    return None


def is_openchat_folder(name: str) -> bool:
    """815 神大家オプチャ（新旧）。"""
    n = (name or "").strip()
    return n.startswith(("815_", "P815_"))


def is_kanji_folder(name: str) -> bool:
    """823 幹事（新旧）。"""
    n = (name or "").strip()
    return n.startswith(("823", "P823")) and "幹事" in n


def resolve_existing_dir(base: Path, folder: str) -> Path | None:
    """base/folder を新旧で試し、存在するディレクトリを返す。"""
    for cand in folder_aliases(folder):
        d = base / cand
        if d.is_dir():
            return d
    return None


def default_partner_base() -> Path:
    """OneDrive 26_パートナー社への相談。"""
    return (
        Path.home()
        / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
        / "C2_ルーティン作業/26_パートナー社への相談"
    )


def resolve_openchat_base(base: Path | None = None) -> Path:
    """P815_神大家オプチャ（無ければ旧815）。存在しなくても新形式パスを返す。"""
    root = base or default_partner_base()
    return resolve_existing_dir(root, OPENCHAT_FOLDER) or (root / OPENCHAT_FOLDER)
