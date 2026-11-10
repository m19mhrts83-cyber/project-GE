"""Google OAuth トークン保存の共通口（スコープを落とさない）。

問題（2026-11-10 調査）: 各スクリプトが「自分に必要な狭いスコープ」で token を読み、
期限切れで refresh したあと `creds.to_json()` をそのまま上書きしていた。refresh_token 自体の
許可（例: estate の gmail.send）は Google 側で生きているのに、ファイルの `scopes` が
gmail.readonly だけに書き換わり、ヘルスチェックや送信側が「送信許可が切れた」と判断していた。

対策: 保存時、既存ファイルと refresh_token が同じ（＝同じ許可）なら、既存の scopes と合流して保存する。
新しく同意し直した（refresh_token が変わった）ときは、新しい scopes をそのまま使う。
値はログに出さない。
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def merged_token_json(new_json: str, existing: dict[str, Any] | None) -> str:
    data = json.loads(new_json)
    if not existing or not data.get("refresh_token") or data.get("refresh_token") != existing.get("refresh_token"):
        return new_json
    old = existing.get("scopes") or []
    if isinstance(old, str):
        old = old.split()
    new = data.get("scopes") or []
    if isinstance(new, str):
        new = new.split()
    merged = list(dict.fromkeys([*old, *new]))  # 既存の並びを優先
    if merged == list(new):
        return new_json
    data["scopes"] = merged
    return json.dumps(data)


def save_creds_keep_scopes(path: str | os.PathLike, creds: Any) -> None:
    """creds.to_json() を、同じ許可なら既存スコープを残して保存する（一時ファイル→置き換え）。"""
    p = Path(path)
    existing = None
    if p.is_file():
        try:
            existing = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = None
    text = merged_token_json(creds.to_json(), existing)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=p.name + ".", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        try:
            os.chmod(tmp, p.stat().st_mode & 0o777 if p.exists() else 0o600)
        except OSError:
            pass
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
