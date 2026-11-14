# -*- coding: utf-8 -*-
"""公開リポに入れないファイルを非公開リポ project-GE-private と行き来させる（Mac 用・2026-11-14）。

公開リポ（~/git-repos）では config/private_paths.txt の場所を .gitignore で外している。
ファイル自体は Mac の同じ場所に置いたままにして、スクリプトのパスは変えない。
非公開リポの clone（既定 ~/git-repos-private/project-GE-private）に同じ相対パスで写して push する。

  push    : 公開側の作業フォルダ → 非公開 clone へ写し、変化があれば commit・push
  restore : 非公開 clone → 公開側の作業フォルダへ、無いファイルだけ戻す（上書きしない）

消したファイルは非公開側では消さない（誤って消したときに戻せるように）。整理は非公開リポで手で行う。
main の自動追従（launchd/main_checkout_sync_runner.sh）が 30 分ごとに push → ff → restore の順で呼ぶ。
"""
from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PATTERNS = REPO / "config" / "private_paths.txt"
DEFAULT_PRIVATE = Path.home() / "git-repos-private" / "project-GE-private"


def private_dir() -> Path:
    return Path(os.environ.get("PRIVATE_DATA_REPO_DIR") or DEFAULT_PRIVATE).expanduser()


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=cwd, check=check,
                          capture_output=True, text=True)


def public_files() -> list[str]:
    """公開側の作業フォルダにある、private_paths に当たるファイル（追跡中・未追跡とも）。"""
    out = _git(REPO, "ls-files", "-z", "--cached", "--others", "--ignored",
               f"--exclude-from={PATTERNS}").stdout
    return sorted({p for p in out.split("\0") if p and (REPO / p).is_file()})


def private_files(dst: Path) -> list[str]:
    out = []
    for p in dst.rglob("*"):
        if p.is_file() and ".git" not in p.relative_to(dst).parts:
            rel = p.relative_to(dst).as_posix()
            if rel != "README.md":
                out.append(rel)
    return sorted(out)


def copy_newer(src_root: Path, dst_root: Path, rels: list[str], *, overwrite: bool, dry: bool) -> list[str]:
    done = []
    for rel in rels:
        s, d = src_root / rel, dst_root / rel
        if d.exists() and (not overwrite or filecmp.cmp(s, d, shallow=False)):
            continue
        done.append(rel)
        if not dry:
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, d)
    return done


def cmd_push(dst: Path, dry: bool) -> int:
    rels = public_files()
    changed = copy_newer(REPO, dst, rels, overwrite=True, dry=dry)
    print(f"private push: {len(rels)} 件中 {len(changed)} 件を写す" + ("（dry-run）" if dry else ""))
    if dry or not changed:
        return 0
    _git(dst, "add", "-A")
    if _git(dst, "diff", "--cached", "--quiet", check=False).returncode == 0:
        return 0
    _git(dst, "commit", "-q", "-m", f"sync from Mac ({len(changed)} files)")
    r = _git(dst, "push", "-q", check=False)
    if r.returncode != 0:
        print(f"private push: push 失敗 {r.stderr.strip()[:200]}", file=sys.stderr)
        return 1
    return 0


def cmd_restore(dst: Path, dry: bool) -> int:
    rels = private_files(dst)
    back = copy_newer(dst, REPO, rels, overwrite=False, dry=dry)
    print(f"private restore: {len(back)} 件を戻す" + ("（dry-run）" if dry else ""))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["push", "restore"])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    dst = private_dir()
    if not (dst / ".git").exists():
        print(f"private: {dst} に非公開リポの clone が無い（スキップ）")
        return 0
    if a.mode == "push":
        _git(dst, "pull", "-q", "--ff-only", check=False)
        return cmd_push(dst, a.dry_run)
    return cmd_restore(dst, a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
