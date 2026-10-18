#!/usr/bin/env python3
"""パートナー社フォルダを 101_… → P101_… へ一括移行（dry-run 既定）。

手順:
  1. OneDrive 26_ 直下の ^\\d{3}_ フォルダを P 付きへ rename
  2. 連絡先 YAML / line_export / open_chat / config / state の文字列置換
  3. マッピング表を stdout に出す

  python scripts/jarvis_partner_folder_p_prefix_migrate.py
  python scripts/jarvis_partner_folder_p_prefix_migrate.py --apply
  python scripts/jarvis_partner_folder_p_prefix_migrate.py --apply --skip-fs  # 設定のみ
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PARTNER_BASE = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    / "C2_ルーティン作業/26_パートナー社への相談"
)
LEGACY_DIR_RE = re.compile(r"^(\d{3})_(.+)$")
# AI社員パス（docs/AIエージェントチーム/…/311_…）は置換しない
SKIP_REPLACE_PATH_PARTS = (
    "AIエージェントチーム",
    "docs/AIエージェントチーム",
)

# 置換対象ファイル（存在するときだけ）
CONFIG_TARGETS: list[Path] = [
    PARTNER_BASE / "000_共通" / "連絡先一覧.yaml",
    PARTNER_BASE / "000_共通" / "連絡先一覧.md",
    PARTNER_BASE / "000_共通" / "line_export_routes.yaml",
    PARTNER_BASE / "000_共通" / "line_export_routes.example.yaml",
    REPO / "line_unofficial_poc" / "open_chat_routes.yaml",
    REPO / "line_unofficial_poc" / "open_chat_routes.example.yaml",
    REPO / "config" / "todoist_projects.yaml",
    REPO / "config" / "dashboard_lanes.yaml",
    REPO / "apps" / "jarvis-dashboard" / "config" / "partner_contacts.json",
    REPO / "apps" / "jarvis-dashboard" / "data" / "folder_links.json",
    REPO / "apps" / "jarvis-dashboard" / "data" / "glucon_sources.json",
    REPO / ".jarvis_state" / "line_export_reminder.json",
]

# ルール・ドキュメント（例示の更新）
DOC_TARGETS: list[Path] = [
    REPO / ".cursor" / "rules" / "partner-folder-numbering.mdc",
    REPO / ".cursor" / "rules" / "jarvis-property-hub-a-series.mdc",
    Path(
        "/Users/matsunomasaharu2/Library/CloudStorage/OneDrive-個人用"
        "/215_神・大家さん倶楽部/.cursor/rules/partner-folder-numbering.mdc"
    ),
]


def discover_renames(base: Path) -> list[tuple[Path, Path]]:
    """旧 → 新 の (src, dest) 一覧。"""
    out: list[tuple[Path, Path]] = []
    if not base.is_dir():
        return out
    for p in sorted(base.iterdir()):
        if not p.is_dir():
            continue
        m = LEGACY_DIR_RE.match(p.name)
        if not m:
            continue
        # 000_共通・物件ハブ A1_ は対象外（A は正規表現で既に除外）
        if m.group(1) == "000":
            continue
        dest = p.parent / f"P{m.group(1)}_{m.group(2)}"
        out.append((p, dest))
    return out


def build_replace_map(renames: list[tuple[Path, Path]]) -> list[tuple[str, str]]:
    """長い名前から置換（NFC/NFD 両対応・長さ降順）。

    設定ファイルは NFC（815_神大家オプチャ）、macOS FS は NFD になりやすい。
    置換後のフォルダ名は NFC（P815_…）に揃える。
    """
    pairs: list[tuple[str, str]] = []
    seen_old: set[str] = set()
    for src, dest in renames:
        new_nfc = unicodedata.normalize("NFC", dest.name)
        for old in (
            src.name,
            unicodedata.normalize("NFC", src.name),
            unicodedata.normalize("NFD", src.name),
        ):
            if not old or old in seen_old or old == new_nfc:
                continue
            if unicodedata.normalize("NFC", old) == new_nfc:
                continue
            seen_old.add(old)
            pairs.append((old, new_nfc))
    pairs.sort(key=lambda x: len(x[0]), reverse=True)
    return pairs


def should_skip_file(path: Path) -> bool:
    s = str(path)
    return any(part in s for part in SKIP_REPLACE_PATH_PARTS)


def apply_text_replacements(
    path: Path,
    pairs: list[tuple[str, str]],
    *,
    dry_run: bool,
) -> int:
    """ファイル内の旧フォルダ名を新に置換。変更行数相当＝置換回数。"""
    if not path.is_file() or should_skip_file(path):
        return 0
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"⚠ read fail: {path}: {e}", file=sys.stderr)
        return 0
    new = text
    count = 0
    for old, new_name in pairs:
        if old in new:
            n = new.count(old)
            new = new.replace(old, new_name)
            count += n
    if count == 0 or new == text:
        return 0
    if dry_run:
        print(f"  [dry] text {count}× {path}")
        return count
    path.write_text(new, encoding="utf-8")
    print(f"  ✅ text {count}× {path}")
    return count


def rename_dirs(
    renames: list[tuple[Path, Path]],
    *,
    dry_run: bool,
) -> int:
    ok = 0
    for src, dest in renames:
        if dest.exists():
            print(f"  ⚠ skip (dest exists): {src.name} → {dest.name}", file=sys.stderr)
            continue
        if dry_run:
            print(f"  [dry] mv {src.name} → {dest.name}")
            ok += 1
            continue
        src.rename(dest)
        print(f"  ✅ mv {src.name} → {dest.name}")
        ok += 1
    return ok


def patch_night_triage_queue(pairs: list[tuple[str, str]], *, dry_run: bool) -> int:
    """night_triage/queue.json の folder フィールドのみ（巨大 JSON）。"""
    path = REPO / ".jarvis_state" / "night_triage" / "queue.json"
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠ queue.json: {e}", file=sys.stderr)
        return 0
    mapping = dict(pairs)
    count = 0

    def walk(obj: object) -> None:
        nonlocal count
        if isinstance(obj, dict):
            f = obj.get("folder")
            if isinstance(f, str) and f in mapping:
                obj["folder"] = mapping[f]
                count += 1
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(data)
    if count == 0:
        return 0
    if dry_run:
        print(f"  [dry] queue.json folder×{count}")
        return count
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  ✅ queue.json folder×{count}")
    return count


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="実際に rename / 書込")
    ap.add_argument("--skip-fs", action="store_true", help="フォルダ rename をスキップ")
    ap.add_argument("--skip-text", action="store_true", help="設定テキスト置換をスキップ")
    ap.add_argument(
        "--base",
        type=Path,
        default=PARTNER_BASE,
        help="26_パートナー社への相談 パス",
    )
    args = ap.parse_args()
    dry = not args.apply

    print(f"📎 partner P-prefix migrate ({'APPLY' if args.apply else 'DRY-RUN'})")
    print(f"  base: {args.base}")

    renames = discover_renames(args.base)
    if not renames:
        print("  （リネーム対象なし — 既に P 付きか、パス無し）")
    else:
        print(f"  フォルダ候補: {len(renames)} 件")
        for src, dest in renames:
            print(f"    {src.name} → {dest.name}")

    pairs = build_replace_map(renames)
    # フォルダが既に P 付きでも、設定に旧名が残っている場合用の固定マップ
    # discover が空でも最低限の既知リストで置換できるよう、実ディレクトリから再スキャン
    if not pairs:
        # 既に P 付きなら、設定側の旧名置換用に dest から legacy を逆算
        if args.base.is_dir():
            for p in sorted(args.base.iterdir()):
                if p.is_dir() and p.name.startswith("P") and LEGACY_DIR_RE.match(p.name[1:]):
                    legacy = p.name[1:]
                    pairs.append((legacy, p.name))
            pairs.sort(key=lambda x: len(x[0]), reverse=True)

    n_fs = 0
    if not args.skip_fs and renames:
        print("— filesystem —")
        n_fs = rename_dirs(renames, dry_run=dry)

    n_text = 0
    if not args.skip_text and pairs:
        print("— config / docs text —")
        for path in CONFIG_TARGETS + DOC_TARGETS:
            n_text += apply_text_replacements(path, pairs, dry_run=dry)
        n_text += patch_night_triage_queue(pairs, dry_run=dry)

    print("— summary —")
    print(f"  dirs: {n_fs}  text_hits: {n_text}  mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    if dry:
        print("  本番適用: --apply を付けて再実行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
