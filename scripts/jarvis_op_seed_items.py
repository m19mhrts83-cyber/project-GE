#!/usr/bin/env python3
""".env.jarvis_private の指定キーを 1Password の保管庫へ「1キー＝1項目（タイトル＝キー名）」で入れる。

値は画面・ログに出さない（op への受け渡しは 0600 の一時ファイル、表示はキー名と結果だけ）。
既に同じタイトルの項目があるキーは飛ばす（上書きしない）。
人の Touch ID セッション（1Password アプリ連携）で動かす想定。Service Account は読み取り専用なので使わない。

例:
  python scripts/jarvis_op_seed_items.py --vault <保管庫ID> --env-file config/op/comm_hub_backup.env
  （--env-file の参照ファイルからキー名を拾う。--keys A,B でも可）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

OP = "/usr/local/bin/op"
PRIVATE_ENV = Path.home() / "git-repos" / ".env.jarvis_private"


def read_private_values(path: Path, keys: list[str]) -> dict[str, str]:
    """zsh で source した結果を読む（runner と同じ解釈にそろえる）。値は返すだけで表示しない。"""
    script = 'set -a; source "$1"; set +a; shift; for k in "$@"; do printf "%s\\0%s\\0" "$k" "${(P)k-}"; done'
    out = subprocess.run(
        ["/bin/zsh", "-c", script, "zsh", str(path), *keys], capture_output=True, check=True
    ).stdout.decode("utf-8")
    parts = out.split("\0")
    return {parts[i]: parts[i + 1] for i in range(0, len(parts) - 1, 2)}


def existing_titles(vault: str) -> set[str]:
    r = subprocess.run([OP, "item", "list", "--vault", vault, "--format", "json"], capture_output=True, check=True)
    return {it.get("title", "") for it in json.loads(r.stdout or b"[]")}


def create_item(vault: str, key: str, value: str) -> str:
    tpl = {
        "title": key,
        "category": "PASSWORD",
        "fields": [{"id": "password", "type": "CONCEALED", "purpose": "PASSWORD", "label": "password", "value": value}],
    }
    fd, tmp = tempfile.mkstemp(prefix="op_tpl_", suffix=".json")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(tpl, f)
        r = subprocess.run(
            [OP, "item", "create", "--vault", vault, "--template", tmp, "--format", "json"],
            capture_output=True,
        )
    finally:
        Path(tmp).unlink(missing_ok=True)
    if r.returncode != 0:
        return f"失敗 rc={r.returncode}"  # stderr は値を含みうるので出さない
    return "作成 id=" + str(json.loads(r.stdout).get("id", "?"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault", required=True, help="保管庫 ID（名前でも可）")
    ap.add_argument("--env-file", help="KEY=op://... の参照ファイル。キー名だけ使う")
    ap.add_argument("--keys", help="カンマ区切りのキー名")
    ap.add_argument("--private-env", default=str(PRIVATE_ENV))
    args = ap.parse_args()
    keys: list[str] = []
    if args.env_file:
        for line in Path(args.env_file).read_text(encoding="utf-8").splitlines():
            m = re.match(r"^([A-Z_][A-Z0-9_]*)=", line)
            if m:
                keys.append(m.group(1))
    if args.keys:
        keys += [k.strip() for k in args.keys.split(",") if k.strip()]
    if not keys:
        print("キーがありません", file=sys.stderr)
        return 2
    values = read_private_values(Path(args.private_env), keys)
    have = existing_titles(args.vault)
    rc = 0
    for k in keys:
        if k in have:
            print(f"{k}: 既にあるので飛ばす")
            continue
        v = values.get(k, "")
        if not v:
            print(f"{k}: .env に値がないので飛ばす")
            rc = 1
            continue
        res = create_item(args.vault, k, v)
        print(f"{k}: {res}")
        if res.startswith("失敗"):
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
