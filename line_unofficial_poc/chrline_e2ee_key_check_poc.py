#!/usr/bin/env python3
"""
サーバーが知っている自分の E2EE 公開鍵の keyId と、
CHRLINE が savePath 配下 .e2eeKeys に持っている秘密鍵ファイルを照合する。

sync の E2EE で「selfKey should not be None. KeyId=XXXX」と出たとき、
その XXXX が「ローカル欠け」かどうかを確認する用途。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from chrline_client_utils import build_logged_in_client, save_root_from_env


def _server_key_ids(cl) -> list[int]:
    raw = cl.getE2EEPublicKeys()
    if not isinstance(raw, list):
        return []
    out: list[int] = []
    for item in raw:
        try:
            kid = cl.checkAndGetValue(item, "keyId", 2)
            if kid is None and isinstance(item, dict):
                kid = item.get(2)
            out.append(int(kid))
        except (TypeError, ValueError, KeyError):
            continue
    return sorted(set(out))


def _local_key_ids(save_root: Path) -> list[int]:
    d = save_root / ".e2eeKeys"
    if not d.is_dir():
        return []
    out: list[int] = []
    for p in d.iterdir():
        if not p.is_file():
            continue
        m = re.match(r"key_(\d+)\.json$", p.name)
        if m:
            out.append(int(m.group(1)))
    return sorted(set(out))


def main() -> int:
    save_root = save_root_from_env()
    cl = build_logged_in_client(save_root)

    server = _server_key_ids(cl)
    local = _local_key_ids(save_root)
    missing_on_disk = [k for k in server if k not in local]
    orphan_local = [k for k in local if k not in server]

    print("# サーバー側に登録されている自分の E2EE keyId（getE2EEPublicKeys）")
    print(f"#   {server if server else '(取得できず・空)'}")
    print("# ローカル .e2eeKeys にある key_*.json の keyId")
    print(f"#   {local if local else '(ファイルなし)'}")
    print("# サーバーにあるがローカルに無い keyId（復号で selfKey None になりやすい）")
    print(f"#   {missing_on_disk if missing_on_disk else '(なし)'}")
    if orphan_local:
        print("# ローカルのみ（サーバー一覧に無い・古い等）")
        print(f"#   {orphan_local}")

    mid = getattr(cl, "mid", None) or ""
    if mid:
        ufile = save_root / ".e2eeKeys" / f"{mid}.json"
        print(f"# 代表ファイル {ufile.name}: {'あり' if ufile.is_file() else 'なし'}")

    print(
        "# 注意: --verbose の「KeyId=NNN」はメッセージ chunks 内の receiverKeyId。"
        "鍵ローテ後は getE2EEPublicKeys の一覧に NNN が載らないことがあり、"
        "その場合はバックアップ復元が無いと当該メッセージは復号できません。"
    )

    print(
        "\n# ヒント: 欠けがある場合は CHRLINE の SQR ログイン・E2EE 復元、"
        "または registerE2EESelfKey（新規鍵は既存トーク履歴とは別扱いになり得る）を検討。",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
