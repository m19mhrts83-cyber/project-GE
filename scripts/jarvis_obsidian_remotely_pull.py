#!/usr/bin/env python3
"""[廃止] Obsidian Remotely Save 橋（OneDrive）→ Google Drive ボルトへプル。

2026-08-02: 同期本線は Google Drive Sync。通常は実行しない（state disabled）。
正: .cursor/rules/jarvis-obsidian-gdrive-sync.mdc

旧経路（残置）:
  iPhone が Remotely Save で OneDrive `Apps/remotely-save/500_Obsidian` に上げた変更を、
  Mac 正本ボルト（Google Drive `500_Obsidian_r1`）へ取り込む。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_DIR = REPO / ".jarvis_state"
STATE_PATH = STATE_DIR / "obsidian_remotely_pull.json"
EXAMPLE_PATH = STATE_DIR / "obsidian_remotely_pull.example.json"

DEFAULT_BROKER = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/Apps/remotely-save/500_Obsidian"
)
DEFAULT_VAULT = (
    Path.home()
    / "Library/CloudStorage/GoogleDrive-admin@livingsupport-matsu.co.jp"
    / "マイドライブ/500_Obsidian_r1"
)

# 橋がこの日数より古い最新ファイルしか無い → iPhone プッシュ促し
STALE_DAYS = 3
# 報告に出す取り込みファイル名の上限
SAMPLE_LIMIT = 8

SKIP_DIR_NAMES = {
    ".obsidian",
    ".trash",
    ".git",
    "node_modules",
    "__pycache__",
}
SKIP_PATH_PREFIXES = (
    "99_token,api key/",
    "99_token,api key\\",
)


def now_jst() -> datetime:
    return datetime.now(JST)


def load_state() -> dict:
    if STATE_PATH.is_file():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    if EXAMPLE_PATH.is_file():
        try:
            return json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {
        "disabled": False,
        "last_pull_at": None,
        "last_result": None,
        "broker_path": str(DEFAULT_BROKER),
        "vault_path": str(DEFAULT_VAULT),
    }


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def disabled_by_env_or_state(state: dict) -> bool:
    if os.environ.get("JARVIS_OBSIDIAN_REMOTELY_PULL_DISABLE", "").strip() == "1":
        return True
    return bool(state.get("disabled"))


def resolve_paths(state: dict) -> tuple[Path, Path]:
    broker = Path(
        os.environ.get("JARVIS_OBSIDIAN_BROKER", "")
        or state.get("broker_path")
        or DEFAULT_BROKER
    ).expanduser()
    vault = Path(
        os.environ.get("JARVIS_OBSIDIAN_VAULT", "")
        or state.get("vault_path")
        or DEFAULT_VAULT
    ).expanduser()
    return broker, vault


def should_skip(rel: Path) -> bool:
    parts = rel.parts
    if any(p in SKIP_DIR_NAMES for p in parts):
        return True
    s = rel.as_posix()
    return any(s.startswith(pref.replace("\\", "/")) for pref in SKIP_PATH_PREFIXES)


def iter_broker_files(broker: Path) -> list[Path]:
    out: list[Path] = []
    if not broker.is_dir():
        return out
    for p in broker.rglob("*"):
        if not p.is_file():
            continue
        try:
            rel = p.relative_to(broker)
        except ValueError:
            continue
        if should_skip(rel):
            continue
        out.append(p)
    return out


def newest_mtime(files: list[Path]) -> datetime | None:
    if not files:
        return None
    mt = max(f.stat().st_mtime for f in files)
    return datetime.fromtimestamp(mt, tz=JST)


def plan_pull(broker: Path, vault: Path) -> tuple[list[tuple[Path, Path, str]], dict]:
    """Return (actions, stats). actions: (src, dest, reason)."""
    actions: list[tuple[Path, Path, str]] = []
    stats = {
        "broker_files": 0,
        "missing": 0,
        "newer": 0,
        "same_or_older": 0,
        "errors": 0,
    }
    files = iter_broker_files(broker)
    stats["broker_files"] = len(files)
    for src in files:
        rel = src.relative_to(broker)
        dest = vault / rel
        try:
            sm = src.stat()
        except OSError:
            stats["errors"] += 1
            continue
        if not dest.exists():
            actions.append((src, dest, "missing"))
            stats["missing"] += 1
            continue
        try:
            dm = dest.stat()
        except OSError:
            stats["errors"] += 1
            continue
        # OneDrive 側が新しい（2秒以上）ときだけ採用
        if sm.st_mtime > dm.st_mtime + 2:
            if sm.st_size != dm.st_size or src.read_bytes() != dest.read_bytes():
                actions.append((src, dest, "newer"))
                stats["newer"] += 1
            else:
                stats["same_or_older"] += 1
        else:
            stats["same_or_older"] += 1
    return actions, stats


def apply_actions_rel(
    broker: Path, actions: list[tuple[Path, Path, str]]
) -> list[str]:
    done: list[str] = []
    for src, dest, _reason in actions:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        done.append(src.relative_to(broker).as_posix())
    return done


def wake_obsidian(vault: Path) -> str:
    """Obsidian を前面化（自動同期が有効なら追従しやすい）。失敗しても続行。"""
    name = vault.name
    uri = f"obsidian://open?vault={name}"
    try:
        subprocess.run(["open", uri], check=False, capture_output=True, timeout=10)
        return f"opened {uri}"
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"skip open ({e})"


def format_block(
    *,
    broker: Path,
    vault: Path,
    stats: dict,
    applied: list[str],
    dry_run: bool,
    stale: bool,
    newest: datetime | None,
    wake_note: str,
) -> str:
    lines = [
        "📎 Obsidianプル（Remotely Save橋）",
        f"- 橋: `{broker}`",
        f"- 正本: `{vault}`",
        f"- 橋ファイル数: {stats['broker_files']}",
        f"- 取り込み候補: missing={stats['missing']} / newer={stats['newer']} "
        f"（スキップ同齢={stats['same_or_older']}）",
    ]
    skipped_stale = int(stats.get("skipped_stale_missing") or 0)
    if skipped_stale:
        lines.append(
            f"- 注意: 橋が古いため missing {skipped_stale} 件の復元は見送り（newer のみ対象）"
        )
    if newest:
        lines.append(f"- 橋の最新更新: {newest.strftime('%Y-%m-%d %H:%M')}")
    else:
        lines.append("- 橋の最新更新: （ファイルなし）")

    n = stats["missing"] + stats["newer"]
    if dry_run:
        lines.append(f"- 実行: dry-run（{n} 件は未反映）")
    elif n == 0:
        lines.append("- 実行: 取り込み0件（橋に新しい差分なし）")
    else:
        lines.append(f"- 実行: {len(applied)} 件を正本へコピー")
        for rel in applied[:SAMPLE_LIMIT]:
            lines.append(f"  · {rel}")
        if len(applied) > SAMPLE_LIMIT:
            lines.append(f"  · …他 {len(applied) - SAMPLE_LIMIT} 件")

    lines.append(f"- Obsidian起動: {wake_note}")

    if stale:
        lines.append(
            f"- 判定: ⚠️ 橋が {STALE_DAYS} 日以上更新なし。"
            "iPhone の Obsidian で Remotely Save 同期（プッシュ）が必要です。"
        )
    elif n > 0 and not dry_run:
        lines.append("- 判定: ✅ 正本へ取り込み済み")
    elif n > 0 and dry_run:
        lines.append("- 判定: ℹ️ 取り込み候補あり（--apply で反映）")
    else:
        lines.append("- 判定: ✅ 差分なし（または橋が空）")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Obsidian Remotely Save bridge → Drive vault pull")
    ap.add_argument("--dry-run", action="store_true", help="コピーせず候補だけ報告")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="候補を正本へコピー（既定。--dry-run が無いときも適用）",
    )
    ap.add_argument("--mark-done", action="store_true", help="state に最終実行を記録")
    ap.add_argument("--status", action="store_true", help="state のみ表示")
    ap.add_argument("--no-wake", action="store_true", help="Obsidian URI 起動をしない")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    state = load_state()
    if args.status:
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0

    if disabled_by_env_or_state(state):
        if args.json:
            print(json.dumps({"disabled": True}, ensure_ascii=False))
        # 無効時は無出力（パートナー確認を汚さない）
        return 0

    broker, vault = resolve_paths(state)
    if not broker.is_dir():
        block = (
            "📎 Obsidianプル（Remotely Save橋）\n"
            f"- 判定: ⚠️ 橋フォルダがありません: `{broker}`\n"
            "- Remotely Save の OneDrive 同期先を確認してください。"
        )
        print(block)
        return 1
    if not vault.is_dir():
        block = (
            "📎 Obsidianプル（Remotely Save橋）\n"
            f"- 判定: ⚠️ 正本ボルトがありません: `{vault}`"
        )
        print(block)
        return 1

    actions, stats = plan_pull(broker, vault)
    files = iter_broker_files(broker)
    newest = newest_mtime(files)
    stale = False
    if newest is None:
        stale = True
    else:
        stale = newest < now_jst() - timedelta(days=STALE_DAYS)

    # 橋が古いときは「missing の一括復元」をしない（移行残骸の巻き戻し防止）。
    # iPhone プッシュ後に新しい mtime の差分（newer）だけ取り込む。
    if stale:
        actions = [a for a in actions if a[2] == "newer"]
        skipped_missing = stats["missing"]
        stats["skipped_stale_missing"] = skipped_missing
    else:
        stats["skipped_stale_missing"] = 0

    dry_run = bool(args.dry_run)
    do_apply = not dry_run

    applied: list[str] = []
    if do_apply and actions:
        applied = apply_actions_rel(broker, actions)

    wake_note = "skip"
    if not args.no_wake:
        wake_note = wake_obsidian(vault)

    block = format_block(
        broker=broker,
        vault=vault,
        stats=stats,
        applied=applied,
        dry_run=dry_run,
        stale=stale,
        newest=newest,
        wake_note=wake_note,
    )
    print(block)

    if args.mark_done or (do_apply and not dry_run):
        state["last_pull_at"] = now_jst().isoformat(timespec="seconds")
        state["last_result"] = {
            "pulled": len(applied),
            "missing": stats["missing"],
            "newer": stats["newer"],
            "stale": stale,
            "newest_broker": newest.isoformat(timespec="seconds") if newest else None,
            "dry_run": dry_run,
        }
        state["broker_path"] = str(broker)
        state["vault_path"] = str(vault)
        save_state(state)

    if args.json:
        print(
            json.dumps(
                {
                    "pulled": applied,
                    "stats": stats,
                    "stale": stale,
                    "newest": newest.isoformat() if newest else None,
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
