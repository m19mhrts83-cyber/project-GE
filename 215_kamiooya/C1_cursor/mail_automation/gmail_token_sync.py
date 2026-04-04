#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gmail のトークンファイル保存後、バックアップ先と GitHub Actions の Secret を自動で揃える。

- token.json / token_estate.json / token_m19m.json について、git-repos の 1b と OneDrive 215 の同フォルダへ相互ミラー
- GITHUB_GMAIL_SECRET_REPO と gh CLI が使えるとき、保存したファイルが token.json または token_m19m.json の場合のみ GMAIL_TOKEN_B64 を更新（estate 単体の更新で Secret を潰さない）

無効化:
  GMAIL_TOKEN_SYNC_DISABLE=1  … ミラー・GitHub 更新の両方をスキップ
  GMAIL_TOKEN_SKIP_GITHUB_SYNC=1 … GitHub だけスキップ（OneDrive 等は実施）
追加ミラー（任意）:
  GMAIL_TOKEN_EXTRA_MIRRORS=/path/a/token.json,/path/b/token.json
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _manual_gitrepos() -> Path:
    return Path.home() / "git-repos/215_kamiooya/C1_cursor/1b_Cursorマニュアル"


def _manual_onedrive() -> Path:
    return (
        Path.home()
        / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1b_Cursorマニュアル"
    )


def _gitrepos_token_path() -> Path:
    return _manual_gitrepos() / "token.json"


def _onedrive_token_path() -> Path:
    return _manual_onedrive() / "token.json"


def _extra_mirror_paths() -> list[Path]:
    raw = os.environ.get("GMAIL_TOKEN_EXTRA_MIRRORS", "").strip()
    if not raw:
        return []
    return [Path(p.strip()) for p in raw.split(",") if p.strip()]


def _mirror_targets_for_primary(primary: Path) -> list[Path]:
    primary = primary.resolve()
    targets: list[Path] = []
    gr = _gitrepos_token_path().resolve()
    od = _onedrive_token_path().resolve()

    # git-repos 側が更新された → OneDrive へ（親フォルダがあれば）
    if gr == primary and od.parent.is_dir():
        targets.append(od)

    # OneDrive 側が更新された → git-repos へ（親フォルダがあれば）
    if od == primary and gr.parent.is_dir():
        targets.append(gr)

    gr_m = _manual_gitrepos()
    od_m = _manual_onedrive()
    for name in ("token_estate.json", "token_m19m.json"):
        gr_f = (gr_m / name).resolve()
        od_f = (od_m / name).resolve()
        if primary == gr_f and od_m.is_dir():
            targets.append(od_m / name)
        if primary == od_f and gr_m.is_dir():
            targets.append(gr_m / name)

    for p in _extra_mirror_paths():
        if p.resolve() != primary:
            p.parent.mkdir(parents=True, exist_ok=True)
            targets.append(p)

    # 重複除去（順序維持）
    seen: set[Path] = set()
    out: list[Path] = []
    for t in targets:
        tr = t.resolve()
        if tr not in seen:
            seen.add(tr)
            out.append(t)
    return out


def sync_token_mirrors(
    primary_token_file: Path,
    *,
    log_prefix: str = "📎 Gmail token",
    skip_github: bool = False,
) -> None:
    """
    primary_token_file に書き込んだ直後に呼ぶ。ミラー先へ copy2、必要なら gh で Secret 更新。
    skip_github: True のときファイルコピーのみ（refresh_token_and_update_github_secret 等で API 更新する場合）
    """
    if _truthy_env("GMAIL_TOKEN_SYNC_DISABLE"):
        return

    primary = primary_token_file.resolve()
    if not primary.is_file():
        return

    targets = _mirror_targets_for_primary(primary)
    for dest in targets:
        try:
            shutil.copy2(primary, dest)
            print(f"{log_prefix}: ミラーしました → {dest}", file=sys.stderr)
        except OSError as e:
            print(f"{log_prefix}: ミラー失敗 {dest}: {e}", file=sys.stderr)

    if skip_github or _truthy_env("GMAIL_TOKEN_SKIP_GITHUB_SYNC"):
        return

    # GitHub Actions（いけとも AI ニュース等）は m19m 系トークンを想定。estate だけの再保存で Secret を上書きしない
    if primary.name not in ("token.json", "token_m19m.json"):
        return

    if shutil.which("gh") is None:
        return

    repo = os.environ.get("GITHUB_GMAIL_SECRET_REPO", "m19mhrts83-cyber/DX-_-").strip()
    if "/" not in repo:
        return

    token_b64 = base64.b64encode(primary.read_bytes()).decode("ascii").replace("\n", "")
    try:
        proc = subprocess.run(
            ["gh", "secret", "set", "GMAIL_TOKEN_B64", "--repo", repo],
            input=token_b64,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode == 0:
            print(
                f"{log_prefix}: GitHub Secret GMAIL_TOKEN_B64 を更新しました（{repo}）",
                file=sys.stderr,
            )
        else:
            err = (proc.stderr or proc.stdout or "").strip()
            print(
                f"{log_prefix}: gh secret set 失敗（exit {proc.returncode}）{': ' + err if err else ''}",
                file=sys.stderr,
            )
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"{log_prefix}: gh 実行エラー: {e}", file=sys.stderr)


def save_token_json_and_sync(token_path: Path, creds_json: str, *, log_prefix: str = "📎 Gmail token") -> None:
    """token を保存してからミラー・GitHub 更新。"""
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds_json, encoding="utf-8")
    sync_token_mirrors(token_path, log_prefix=log_prefix)
