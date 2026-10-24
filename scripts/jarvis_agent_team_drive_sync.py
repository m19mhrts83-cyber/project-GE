#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AIエージェントチーム — Drive「★AIエージェントチーム」へ文書・成果物・ルールを写す（片方向）。

  ~/selenium_env/venv/bin/python scripts/jarvis_agent_team_drive_sync.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_agent_team_drive_sync.py

正本は git（docs/AIエージェントチーム/・.cursor/rules/・config/）。Drive は閲覧用の写し。
- 社員フォルダ: 直下の文書（CLAUDE／AGENTS／README／TASK／PROGRESS／flow など）と
  docs/・output/・tests/・config/ の文書。input/・logs/・scripts/ は写さない
- ルール: Drive 直下 91_ルール/（家ルール例・Cursor ルール・チーム設定・運用コマンド一覧）
- 内容が同じファイルは書かない。Drive にしか無いファイル（outbox/ など）は消さない
- 秘密っぽい名前（env／secret／token／credential）と大きいファイル（20MB 超）は写さない
- 同期衝突の「名前 2.md」等を見つけたら #ops に知らせる（消さない）

repo は書き換えないので launchd の日次実行に使える（install_agent_team_drive_sync_launchd.sh）。
状態マーカー・ボード・ハブ番号付き MD は jarvis_agent_team_status_sync.py 側が写す。
"""
from __future__ import annotations

import argparse
import filecmp
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "docs" / "AIエージェントチーム"
REG = HUB / "agents_registry.yaml"
DRIVE_HUB = (
    Path.home()
    / "Library/CloudStorage/GoogleDrive-admin@livingsupport-matsu.co.jp"
    / "マイドライブ"
    / "★AIエージェントチーム"
)
RULES_DIR = Path("91_ルール")
LOG = "📎 agent_team drive sync"

DOC_EXT = {".md", ".html", ".csv", ".txt", ".pdf", ".png", ".jpg", ".jpeg", ".svg", ".mmd", ".yaml", ".yml"}
AGENT_SUBDIRS = ("docs", "output", "tests", "config")
SECRET_NAME_RE = re.compile(r"(^\.env|env\.|secret|token|credential|password)", re.I)
MAX_BYTES = 20 * 1024 * 1024

# Drive 91_ルール/ に写すもの（repo 相対 → Drive 内の置き場）
RULE_FILES = {
    "config/claude_code_home_CLAUDE.example.md": "家ルール_Claude_Code.md",
    "config/codex_home_AGENTS.example.md": "家ルール_Codex.md",
    "config/agent_team_permissions.yaml": "config/agent_team_permissions.yaml",
    "config/agent_team_ops.yaml": "config/agent_team_ops.yaml",
    "config/agent_team_genres.yaml": "config/agent_team_genres.yaml",
    "config/slack_ai_team_hub.yaml": "config/slack_ai_team_hub.yaml",
    "docs/運用コマンド一覧.md": "運用コマンド一覧.md",
}
RULE_GLOBS = {".cursor/rules": ("*.mdc", "Cursorルール")}


def wanted(path: Path) -> bool:
    if path.suffix.lower() not in DOC_EXT:
        return False
    if SECRET_NAME_RE.search(path.name):
        return False
    try:
        return path.stat().st_size <= MAX_BYTES
    except OSError:
        return False


def copy_if_changed(src: Path, dst: Path, *, dry: bool, stats: dict[str, int]) -> None:
    if dst.is_file() and filecmp.cmp(src, dst, shallow=False):
        stats["same"] += 1
        return
    stats["copied"] += 1
    if dry:
        print(f"# dry-run copy {src.relative_to(REPO)} → {dst.relative_to(DRIVE_HUB)}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def agent_files(folder: Path) -> list[Path]:
    files = [p for p in folder.iterdir() if p.is_file() and wanted(p)]
    for sub in AGENT_SUBDIRS:
        d = folder / sub
        if d.is_dir():
            files += [p for p in d.rglob("*") if p.is_file() and wanted(p)]
    return files



# Drive の同期衝突で生まれる「名前 2.md」「名前 7.yaml」など（2026-10-24 に 38 件たまっていた）
CONFLICT_RE = re.compile(r" \d+\.(md|mdc|yaml|yml|json|txt)$")


def find_conflicts(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and CONFLICT_RE.search(p.name))


def report_conflicts(conflicts: list[Path], *, dry: bool) -> None:
    """競合ファイルがあれば一覧を出し、#ops へ短く知らせる（統合・削除はしない）。"""
    if not conflicts:
        return
    rels = [str(p.relative_to(DRIVE_HUB)) for p in conflicts]
    print(f"{LOG}: ⚠️ Drive 競合ファイル {len(rels)} 件", file=sys.stderr)
    for r in rels[:20]:
        print(f"  - {r}", file=sys.stderr)
    if dry:
        return
    text = (
        f"【ops】Drive ★AIエージェントチーム 競合ファイル {len(rels)} 件\n"
        + "\n".join(f"・{r}" for r in rels[:8])
        + ("\n…" if len(rels) > 8 else "")
        + "\n正は git。重複側を消して統合を（Miss Lemon／Jarvis に依頼可）"
    )
    try:
        subprocess.run(
            [sys.executable, str(REPO / "scripts" / "jarvis_slack_webhook_post.py"), "--channel", "ops", "--text", text],
            check=False,
            timeout=60,
        )
    except Exception as e:  # 通知失敗で同期自体は落とさない
        print(f"{LOG}: #ops 通知失敗: {e}", file=sys.stderr)

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not DRIVE_HUB.is_dir():
        print(f"{LOG}: Drive が見つからない（Google Drive 未起動？）: {DRIVE_HUB}", file=sys.stderr)
        return 1

    stats = {"copied": 0, "same": 0}
    agents = (yaml.safe_load(REG.read_text(encoding="utf-8")) or {}).get("agents") or {}
    for aid, a in sorted(agents.items(), key=lambda x: str(x[0])):
        rel = Path(str(a.get("path") or ""))
        folder = HUB / rel
        if not rel.parts or not folder.is_dir():
            continue
        for src in agent_files(folder):
            copy_if_changed(src, DRIVE_HUB / src.relative_to(HUB), dry=args.dry_run, stats=stats)

    for src_rel, dst_rel in RULE_FILES.items():
        src = REPO / src_rel
        if src.is_file():
            copy_if_changed(src, DRIVE_HUB / RULES_DIR / dst_rel, dry=args.dry_run, stats=stats)
    for src_dir, (pattern, dst_sub) in RULE_GLOBS.items():
        for src in sorted((REPO / src_dir).glob(pattern)):
            if not SECRET_NAME_RE.search(src.name) and src.stat().st_size <= MAX_BYTES:
                copy_if_changed(src, DRIVE_HUB / RULES_DIR / dst_sub / src.name, dry=args.dry_run, stats=stats)

    guide = DRIVE_HUB / RULES_DIR / "00_このフォルダ.md"
    text = (
        "# 91_ルール（Drive）\n\n"
        "閲覧用の写し。正本は git（`config/`・`.cursor/rules/`・`docs/運用コマンド一覧.md`）。"
        "ここを直しても git には戻らない。写しは `scripts/jarvis_agent_team_drive_sync.py`（毎日 6:10）。\n\n"
        "- `家ルール_Claude_Code.md` … Mac の `~/.claude/CLAUDE.md` の元\n"
        "- `家ルール_Codex.md` … Codex 用の同型\n"
        "- `Cursorルール/` … Jarvis（Cursor）が読む `.mdc`\n"
        "- `config/` … 権限・合図・Slack ハブ設定\n"
        "- `運用コマンド一覧.md` … 各仕組みの起動・停止コマンド\n"
    )
    if not args.dry_run and (not guide.is_file() or guide.read_text(encoding="utf-8") != text):
        guide.parent.mkdir(parents=True, exist_ok=True)
        guide.write_text(text, encoding="utf-8")

    print(f"{LOG}: copied={stats['copied']} unchanged={stats['same']} → {DRIVE_HUB}")
    report_conflicts(find_conflicts(DRIVE_HUB), dry=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
