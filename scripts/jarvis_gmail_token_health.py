#!/usr/bin/env python3
"""Gmail OAuth token のスコープ・refresh 有無を一覧し、再認証が必要なものを示す。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

MANUAL = Path(__file__).resolve().parents[1] / "215_kamiooya/C1_cursor/1b_Cursorマニュアル"
sys.path.insert(0, str(MANUAL))

from gmail_api_scopes import (  # noqa: E402
    GMAIL_SCOPES_215,
    granted_scopes_from_token_record,
    token_satisfies_215_scopes,
    token_satisfies_read_modify_scopes,
)

TOKENS = (
    ("admin", "token_livingsupport.json"),
    ("estate", "token_estate.json"),
    ("m19m", "token_m19m.json"),
    ("m19m_legacy", "token.json"),
    ("calendar", "token_calendar.json"),
)

REAUTH_CMD = (
    "cd ~/git-repos/215_kamiooya/C1_cursor/1b_Cursorマニュアル && "
    "export YORITOORI_BASE_PATH="
    '"$HOME/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/'
    'C2_ルーティン作業/26_パートナー社への相談" && '
    "export GMAIL_TOKEN_PATHS={token} && "
    "~/selenium_env/venv/bin/python gmail_to_yoritoori.py --include-read"
)


def main() -> int:
    issues: list[str] = []
    print("📎 Gmail token ヘルス")
    for label, name in TOKENS:
        path = MANUAL / name
        if not path.is_file():
            print(f"- {label} ({name}): なし")
            continue
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"- {label}: 読取失敗 ({e})")
            issues.append(label)
            continue
        granted = sorted(granted_scopes_from_token_record(d))
        refresh = bool(d.get("refresh_token"))
        if label == "calendar":
            ok = "https://www.googleapis.com/auth/calendar.events" in granted
            status = "OK" if ok else "要再認証"
            print(f"- {label} ({name}): {status} · refresh={'あり' if refresh else 'なし'}")
            if not ok:
                issues.append(label)
                print(
                    "    再認証: google_calendar_create.py "
                    "--auth-console --login-hint admin@livingsupport-matsu.co.jp"
                )
            continue
        full = token_satisfies_215_scopes(d)
        read_mod = token_satisfies_read_modify_scopes(d)
        status = "OK" if full else ("read/modifyのみ" if read_mod else "要再認証")
        print(f"- {label} ({name}): {status} · refresh={'あり' if refresh else 'なし'} · scopes={len(granted)}")
        missing = set(GMAIL_SCOPES_215) - set(granted)
        if missing:
            for m in sorted(missing):
                print(f"    不足: {m.split('/')[-1]}")
            issues.append(label)
        if not refresh:
            issues.append(label)

    if issues:
        print("\n⚠️ 再認証（ブラウザで admin / estate / m19m を選んで許可）:")
        for label, name in TOKENS:
            if label in issues and (MANUAL / name).is_file():
                print(REAUTH_CMD.format(token=name))
        print(
            "\nヒント: GCP OAuth アプリを「本番」にするとテスト用7日切れを避けやすい。"
            " send のみスクリプトで token を上書きしない（gmail_api_scopes.py 参照）。"
        )
        return 1
    print("\n判定: 全 token OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
