#!/usr/bin/env python3
"""
LINE 公式エクスポート .txt の inbox 監視 → 振り分け → 5.やり取り.md 追記 → processed 退避。

正本 inbox:
  000_共通/LINE公式エクスポート/inbox/
  （環境変数 LINE_EXPORT_INBOX_DIR で上書き可）

使い方:
  python line_export_inbox_to_yoritoori.py
  python line_export_inbox_to_yoritoori.py --dry-run
  python line_export_inbox_to_yoritoori.py --file /path/to/chat.txt --route-id tcell_caramel_g
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from pathlib import Path

import yaml

from line_export_to_yoritoori import ExportTarget, import_line_export_file
from line_to_yoritoori_clip import load_env as _clip_load_env

_clip_load_env()

_ONEDRIVE_COMMON = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C2_ルーティン作業/26_パートナー社への相談/000_共通"
)
_REPO_COMMON = (
    Path(__file__).resolve().parent.parent.parent
    / "C2_ルーティン作業"
    / "26_パートナー社への相談"
    / "000_共通"
)

DEFAULT_INBOX_PROCESSED_JSON = Path.home() / ".cursor" / "line_export_inbox_processed.json"
ROUTINE_MARKER = "LINE公式エクスポート取り込み（定常）"


@dataclass
class ExportRoute:
    id: str
    folder: str
    display_name: str
    filename_hints: list[str]
    group: bool = False
    group_label: str = ""

    def to_target(self) -> ExportTarget:
        return ExportTarget(
            folder=self.folder,
            display_name=self.display_name,
            group=self.group,
            group_label=self.group_label,
        )


@dataclass
class InboxRunStats:
    total: int = 0
    imported: int = 0
    repaired: int = 0
    skipped: int = 0
    failed: int = 0
    by_folder: dict[str, int] = field(default_factory=dict)
    failed_files: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


def default_common_dir() -> Path:
    env = (os.environ.get("LINE_EXPORT_COMMON_DIR") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    if _ONEDRIVE_COMMON.is_dir():
        return _ONEDRIVE_COMMON.resolve()
    return _REPO_COMMON.resolve()


def default_inbox_dir() -> Path:
    env = (os.environ.get("LINE_EXPORT_INBOX_DIR") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return default_common_dir() / "LINE公式エクスポート" / "inbox"


def export_root_dir(inbox: Path) -> Path:
    return inbox.parent


def default_routes_path() -> Path:
    env = (os.environ.get("LINE_EXPORT_ROUTES_YAML") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    p = default_common_dir() / "line_export_routes.yaml"
    if p.is_file():
        return p.resolve()
    ex = default_common_dir() / "line_export_routes.example.yaml"
    return ex.resolve()


def load_routes(path: Path) -> list[ExportRoute]:
    if not path.is_file():
        raise FileNotFoundError(f"ルート定義がありません: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw = data.get("routes") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        return []
    routes: list[ExportRoute] = []
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
        routes.append(
            ExportRoute(
                id=rid,
                folder=folder,
                display_name=str(item.get("display_name") or folder).strip(),
                filename_hints=[str(h).strip() for h in hints if str(h).strip()],
                group=bool(item.get("group")),
                group_label=str(item.get("group_label") or "").strip(),
            )
        )
    return routes


def match_route(filename: str, routes: list[ExportRoute]) -> tuple[ExportRoute | None, list[str]]:
    """最初にマッチした route と、複数マッチした id 一覧。"""
    name_lower = filename.lower()
    hits: list[ExportRoute] = []
    for route in routes:
        for hint in route.filename_hints:
            if hint.lower() in name_lower:
                hits.append(route)
                break
    if not hits:
        return None, []
    if len(hits) > 1:
        return hits[0], [h.id for h in hits]
    return hits[0], [hits[0].id]


def load_inbox_state(path: Path) -> dict:
    if not path.is_file():
        return {"files": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("files"), dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"files": {}}


def save_inbox_state(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def file_content_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def list_inbox_files(inbox: Path) -> list[Path]:
    if not inbox.is_dir():
        return []
    out: list[Path] = []
    for pat in ("*.txt", "*.text"):
        out.extend(inbox.glob(pat))
    return sorted({p.resolve() for p in out if p.is_file()})


def unique_dest(dest_dir: Path, name: str) -> Path:
    dest = dest_dir / name
    if not dest.exists():
        return dest
    stem = Path(name).stem
    suffix = Path(name).suffix
    n = 2
    while True:
        candidate = dest_dir / f"{stem}_{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def render_routine_block(stats: InboxRunStats) -> str:
    lines = [
        "---",
        f"📎 {ROUTINE_MARKER}",
        f"- inbox 処理: {stats.total}件（追記 {stats.imported} / 修復 {stats.repaired} / スキップ {stats.skipped} / failed {stats.failed}）",
    ]
    if stats.by_folder:
        parts = [f"{k} +{v}" if v else f"{k} 0" for k, v in sorted(stats.by_folder.items())]
        lines.append(f"- 内訳: {' / '.join(parts)}")
    else:
        lines.append("- 内訳: なし")
    if stats.failed_files:
        lines.append(f"- failed: {', '.join(stats.failed_files)}")
        lines.append(
            "- 対応: line_export_routes.yaml に filename_hints を追加するか "
            "`--route-id` で再実行"
        )
    else:
        lines.append("- failed: なし")
    lines.append("---")
    return "\n".join(lines)


def process_file(
    path: Path,
    *,
    route: ExportRoute,
    stats: InboxRunStats,
    state: dict,
    state_path: Path,
    export_root: Path,
    dry_run: bool,
    plain: bool,
    no_move: bool,
    leave_in_inbox: bool,
    repair_placeholders: bool = True,
    also_append: bool = False,
) -> None:
    stats.total += 1
    content_hash = file_content_hash(path)
    prev = state.get("files", {}).get(content_hash)
    if prev and prev.get("status") in ("imported", "repaired", "failed"):
        stats.skipped += 1
        stats.messages.append(f"スキップ（処理済み hash）: {path.name}")
        return

    result = import_line_export_file(
        path,
        route.to_target(),
        plain=plain,
        dry_run=dry_run,
        repair_placeholders=repair_placeholders,
        also_append=also_append,
    )

    if result.status == "skipped_duplicate":
        stats.skipped += 1
        stats.messages.append(f"スキップ（本文重複）: {path.name} → {route.folder}")
        if not dry_run:
            state.setdefault("files", {})[content_hash] = {
                "status": "skipped_duplicate",
                "file": path.name,
                "folder": route.folder,
                "ts": datetime.now().isoformat(timespec="seconds"),
            }
            save_inbox_state(state_path, state)
        return

    if result.status in ("error", "empty"):
        stats.failed += 1
        stats.failed_files.append(path.name)
        stats.messages.append(f"failed: {path.name} — {result.message}")
        if not dry_run and not leave_in_inbox:
            failed_dir = export_root / "failed"
            failed_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(unique_dest(failed_dir, path.name)))
            state.setdefault("files", {})[content_hash] = {
                "status": "failed",
                "file": path.name,
                "message": result.message,
                "ts": datetime.now().isoformat(timespec="seconds"),
            }
            save_inbox_state(state_path, state)
        return

    if result.status == "repaired":
        stats.repaired += 1
        stats.by_folder[route.folder] = stats.by_folder.get(route.folder, 0) + 1
        stats.messages.append(
            f"修復: {path.name} → {route.folder} — {result.decision or result.message}"
        )
        if not dry_run:
            if not no_move and not leave_in_inbox:
                day = datetime.now().strftime("%Y-%m-%d")
                proc_dir = export_root / "processed" / day
                proc_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(unique_dest(proc_dir, path.name)))
            state.setdefault("files", {})[content_hash] = {
                "status": "repaired",
                "file": path.name,
                "folder": route.folder,
                "repaired_count": result.repaired_count,
                "ts": datetime.now().isoformat(timespec="seconds"),
            }
            save_inbox_state(state_path, state)
        return

    if result.status == "imported":
        stats.imported += 1
        stats.by_folder[route.folder] = stats.by_folder.get(route.folder, 0) + 1
        stats.messages.append(
            f"追記: {path.name} → {route.folder} — {result.decision or result.message}"
        )
        if not dry_run:
            if not no_move and not leave_in_inbox:
                day = datetime.now().strftime("%Y-%m-%d")
                proc_dir = export_root / "processed" / day
                proc_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(unique_dest(proc_dir, path.name)))
            state.setdefault("files", {})[content_hash] = {
                "status": "imported",
                "file": path.name,
                "folder": route.folder,
                "ts": datetime.now().isoformat(timespec="seconds"),
            }
            save_inbox_state(state_path, state)


def run_inbox(
    *,
    inbox_dir: Path | None = None,
    routes_path: Path | None = None,
    state_path: Path | None = None,
    dry_run: bool = False,
    plain: bool = False,
    no_move: bool = False,
    leave_in_inbox: bool = False,
    route_id: str | None = None,
    single_file: Path | None = None,
    repair_placeholders: bool = True,
    also_append: bool = False,
) -> InboxRunStats:
    inbox = (inbox_dir or default_inbox_dir()).expanduser().resolve()
    export_root = export_root_dir(inbox)
    routes = load_routes(routes_path or default_routes_path())
    routes_by_id = {r.id: r for r in routes}

    sp = state_path or Path(
        os.environ.get("LINE_EXPORT_INBOX_PROCESSED_PATH", str(DEFAULT_INBOX_PROCESSED_JSON))
    )
    state = load_inbox_state(sp)
    stats = InboxRunStats()

    if single_file:
        files = [single_file.expanduser().resolve()]
    else:
        inbox.mkdir(parents=True, exist_ok=True)
        files = list_inbox_files(inbox)

    for path in files:
        if not path.is_file():
            continue
        if route_id:
            route = routes_by_id.get(route_id)
            if route is None:
                stats.failed += 1
                stats.failed_files.append(path.name)
                stats.messages.append(f"unknown route-id: {route_id}")
                continue
            amb: list[str] = []
        else:
            route, amb = match_route(path.name, routes)
            if len(amb) > 1:
                print(
                    f"# 警告: 複数ルート候補 {amb} — 先頭 {route.id if route else '?'} を使用: {path.name}",
                    file=sys.stderr,
                )
        if route is None:
            stats.total += 1
            stats.failed += 1
            stats.failed_files.append(path.name)
            stats.messages.append(f"ルート未一致: {path.name}")
            if not dry_run and not leave_in_inbox and single_file is None:
                failed_dir = export_root / "failed"
                failed_dir.mkdir(parents=True, exist_ok=True)
                ch = file_content_hash(path)
                shutil.move(str(path), str(unique_dest(failed_dir, path.name)))
                state.setdefault("files", {})[ch] = {
                    "status": "failed",
                    "file": path.name,
                    "message": "route_not_matched",
                    "ts": datetime.now().isoformat(timespec="seconds"),
                }
                save_inbox_state(sp, state)
            continue

        process_file(
            path,
            route=route,
            stats=stats,
            state=state,
            state_path=sp,
            export_root=export_root,
            dry_run=dry_run,
            plain=plain,
            no_move=no_move,
            leave_in_inbox=leave_in_inbox,
            repair_placeholders=repair_placeholders,
            also_append=also_append,
        )

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="LINE 公式エクスポート inbox → 5.やり取り.md")
    parser.add_argument("--inbox-dir", type=Path, default=None)
    parser.add_argument("--routes-yaml", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--plain", action="store_true")
    parser.add_argument("--no-move", action="store_true")
    parser.add_argument("--leave-in-inbox", action="store_true")
    parser.add_argument("--route-id", default="", help="全ファイルをこのルート id で処理")
    parser.add_argument("--file", type=Path, default=None, help="inbox 外の .txt を1件処理")
    parser.add_argument("--no-repair", action="store_true", help="プレースホルダー in-place 修復をしない")
    parser.add_argument("--also-append", action="store_true", help="修復後も全文を追記する")
    args = parser.parse_args()

    try:
        stats = run_inbox(
            inbox_dir=args.inbox_dir,
            routes_path=args.routes_yaml,
            dry_run=bool(args.dry_run),
            plain=bool(args.plain),
            no_move=bool(args.no_move),
            leave_in_inbox=bool(args.leave_in_inbox),
            route_id=(args.route_id or "").strip() or None,
            single_file=args.file,
            repair_placeholders=not args.no_repair,
            also_append=bool(args.also_append),
        )
    except FileNotFoundError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1

    for msg in stats.messages:
        print(msg, file=sys.stderr)
    print(render_routine_block(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
