#!/usr/bin/env python3
"""Encrypt and retain backups of ~/.env.jarvis_private (age public-key).

  cd ~/git-repos
  ./scripts/jarvis_private_backup_setup.sh
  python scripts/jarvis_private_backup.py --backup
  python scripts/jarvis_private_backup.py --status
  python scripts/jarvis_private_backup.py --restore /tmp/jarvis_private.restored.env

Never prints plaintext secrets or the age private key.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
SRC = REPO / ".env.jarvis_private"
AGE_DIR = Path.home() / ".config" / "age"
PRIV_KEY = AGE_DIR / "jarvis-private.key"
PUB_KEY = AGE_DIR / "jarvis-private.pub"
LOCAL_DIR = Path.home() / "Library" / "Application Support" / "jarvis-private-backup"
ICLOUD_DIR = (
    Path.home()
    / "Library"
    / "Mobile Documents"
    / "com~apple~CloudDocs"
    / "JarvisPrivateBackup"
)
KEEP = 12
STATE_PATH = REPO / ".jarvis_state" / "jarvis_private_backup.json"


def _now_stamp() -> str:
    return datetime.now(JST).strftime("%Y%m%d_%H%M%S")


def _now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def find_age() -> str:
    for p in (
        Path.home() / "bin" / "age",
        Path("/opt/homebrew/bin/age"),
        Path("/usr/local/bin/age"),
        Path(shutil.which("age") or ""),
    ):
        if p and p.is_file() and os.access(p, os.X_OK):
            return str(p)
    raise SystemExit(
        "age が見つかりません。scripts/jarvis_private_backup_setup.sh を先に実行してください。"
    )


def find_age_keygen() -> str:
    for p in (
        Path.home() / "bin" / "age-keygen",
        Path("/opt/homebrew/bin/age-keygen"),
        Path("/usr/local/bin/age-keygen"),
        Path(shutil.which("age-keygen") or ""),
    ):
        if p and p.is_file() and os.access(p, os.X_OK):
            return str(p)
    raise SystemExit("age-keygen が見つかりません。setup を先に実行してください。")


def ensure_pub_from_priv() -> None:
    if PUB_KEY.is_file():
        return
    if not PRIV_KEY.is_file():
        raise SystemExit(
            f"秘密鍵がありません: {PRIV_KEY}\n"
            "scripts/jarvis_private_backup_setup.sh を実行し、EasyPass2 に秘密鍵を控えてください。"
        )
    r = subprocess.run(
        [find_age_keygen(), "-y", str(PRIV_KEY)],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        raise SystemExit(f"公開鍵の抽出に失敗: {r.stderr.strip()}")
    pub = (r.stdout or "").strip()
    if not pub.startswith("age1"):
        raise SystemExit("公開鍵の形式が不正です")
    AGE_DIR.mkdir(parents=True, exist_ok=True)
    PUB_KEY.write_text(pub + "\n", encoding="utf-8")
    PUB_KEY.chmod(0o644)


def load_recipients() -> list[str]:
    ensure_pub_from_priv()
    lines = [
        ln.strip()
        for ln in PUB_KEY.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    if not lines:
        raise SystemExit(f"公開鍵が空です: {PUB_KEY}")
    return lines


def prune(dir_path: Path, keep: int = KEEP) -> int:
    if not dir_path.is_dir():
        return 0
    files = sorted(
        dir_path.glob("jarvis_private_*.age"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    removed = 0
    for old in files[keep:]:
        try:
            old.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def write_state(payload: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_state() -> dict:
    if not STATE_PATH.is_file():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def cmd_backup() -> int:
    if not SRC.is_file():
        print(f"# missing source: {SRC}", file=sys.stderr)
        return 2
    recipients = load_recipients()
    age = find_age()
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    ICLOUD_DIR.mkdir(parents=True, exist_ok=True)

    name = f"jarvis_private_{_now_stamp()}.age"
    local_path = LOCAL_DIR / name
    icloud_path = ICLOUD_DIR / name

    cmd = [age, "-o", str(local_path)]
    for r in recipients:
        cmd.extend(["-r", r])
    cmd.append(str(SRC))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"# age encrypt failed: {proc.stderr.strip()}", file=sys.stderr)
        return 1

    shutil.copy2(local_path, icloud_path)
    pruned_l = prune(LOCAL_DIR)
    pruned_i = prune(ICLOUD_DIR)

    write_state(
        {
            "updated_at": _now_iso(),
            "last_backup_name": name,
            "local_path": str(local_path),
            "icloud_path": str(icloud_path),
            "src_bytes": SRC.stat().st_size,
            "age_bytes": local_path.stat().st_size,
            "pruned_local": pruned_l,
            "pruned_icloud": pruned_i,
        }
    )
    print("📎 Jarvis Private バックアップ")
    print(f"- 作成: {name}")
    print(f"- ローカル: {LOCAL_DIR}（保持{KEEP}世代・今回削除{pruned_l}）")
    print(f"- iCloud: {ICLOUD_DIR}（保持{KEEP}世代・今回削除{pruned_i}）")
    print("- 秘密鍵は stdout に出していません。EasyPass2 の控えを確認してください。")
    return 0


def cmd_status() -> int:
    st = read_state()
    local_n = len(list(LOCAL_DIR.glob("jarvis_private_*.age"))) if LOCAL_DIR.is_dir() else 0
    cloud_n = (
        len(list(ICLOUD_DIR.glob("jarvis_private_*.age"))) if ICLOUD_DIR.is_dir() else 0
    )
    print("📎 Jarvis Private バックアップ status")
    print(f"- 正本: {'あり' if SRC.is_file() else 'なし'} ({SRC})")
    print(f"- 秘密鍵: {'あり' if PRIV_KEY.is_file() else 'なし'} ({PRIV_KEY})")
    print(f"- 公開鍵: {'あり' if PUB_KEY.is_file() else 'なし'} ({PUB_KEY})")
    try:
        print(f"- age binary: {find_age()}")
    except SystemExit as e:
        print(f"- age binary: 未導入（{e}）")
    print(f"- ローカル世代: {local_n} / iCloud世代: {cloud_n}")
    if st.get("updated_at"):
        print(f"- 最終成功: {st.get('updated_at')} · {st.get('last_backup_name')}")
    else:
        print("- 最終成功: まだありません")
    print("- FileVault / Time Machine は OS 設定（別レイヤ）。秘密の本線はこの .age です。")
    return 0


def cmd_restore(dest: Path, *, force: bool) -> int:
    if not PRIV_KEY.is_file():
        print(
            f"# 秘密鍵がありません: {PRIV_KEY}\n"
            "# EasyPass2 の控えから戻してから再実行してください。",
            file=sys.stderr,
        )
        return 2
    candidates: list[Path] = []
    if ICLOUD_DIR.is_dir():
        candidates.extend(ICLOUD_DIR.glob("jarvis_private_*.age"))
    if LOCAL_DIR.is_dir():
        candidates.extend(LOCAL_DIR.glob("jarvis_private_*.age"))
    if not candidates:
        print("# 復元用 .age がありません", file=sys.stderr)
        return 2
    newest = max(candidates, key=lambda p: p.stat().st_mtime)
    if dest.exists() and not force:
        print(
            f"# 宛先が既にあります: {dest}\n# 上書きする場合は --force を付けてください。",
            file=sys.stderr,
        )
        return 2
    dest.parent.mkdir(parents=True, exist_ok=True)
    age = find_age()
    proc = subprocess.run(
        [age, "-d", "-i", str(PRIV_KEY), "-o", str(dest), str(newest)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(f"# decrypt failed: {proc.stderr.strip()}", file=sys.stderr)
        return 1
    dest.chmod(0o600)
    print("📎 Jarvis Private 復元")
    print(f"- 元: {newest.name}")
    print(f"- 宛先: {dest}（内容は表示しません）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Jarvis private env age backup")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--backup", action="store_true")
    g.add_argument("--status", action="store_true")
    g.add_argument(
        "--restore",
        metavar="PATH",
        help="復号先パス（例: /tmp/jarvis_private.restored.env）",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="--restore で既存ファイルを上書き",
    )
    args = ap.parse_args()
    if args.backup:
        return cmd_backup()
    if args.status:
        return cmd_status()
    return cmd_restore(Path(args.restore).expanduser(), force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
