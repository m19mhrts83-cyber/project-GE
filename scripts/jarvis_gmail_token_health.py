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
    ("jarvis", "token_jarvis.json"),
    ("m19m_legacy", "token.json"),
    ("calendar", "token_calendar.json"),
)

# 取込用（read/modify）再同意。estate の送信用フルスコープは REAUTH_ESTATE_SEND。
REAUTH_CMD = (
    "cd ~/git-repos/215_kamiooya/C1_cursor/1b_Cursorマニュアル && "
    "export YORITOORI_BASE_PATH="
    '"$HOME/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/'
    'C2_ルーティン作業/26_パートナー社への相談" && '
    "export GMAIL_TOKEN_PATHS={token} && "
    "~/selenium_env/venv/bin/python gmail_to_yoritoori.py --include-read"
)

REAUTH_ESTATE_SEND = (
    "cd ~/git-repos/215_kamiooya/C1_cursor/1b_Cursorマニュアル && "
    "GMAIL_LOGIN_HINT=matsuno.estate@gmail.com "
    "~/selenium_env/venv/bin/python -c \""
    "from pathlib import Path; "
    "from gmail_to_yoritoori import build_service_for_token; "
    "s,e=build_service_for_token(Path('token_estate.json'), open_browser=True); "
    "print('OK', e)\""
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
        status = "OK" if full else ("read/modifyのみ（取込可・送信は要再同意）" if read_mod else "要再認証")
        print(f"- {label} ({name}): {status} · refresh={'あり' if refresh else 'なし'} · scopes={len(granted)}")
        missing = set(GMAIL_SCOPES_215) - set(granted)
        if missing:
            for m in sorted(missing):
                print(f"    不足: {m.split('/')[-1]}")
            # 取込は read/modify で足りる。estate の send/modify 欠落は送信用再同意を促す。
            if label == "estate" and not full:
                issues.append("estate_send")
                print("    ※取込は readonly でも可。パートナー送信にはフルスコープ再同意が必要。")
                print(f"    → {MANUAL / 'reauth_estate_gmail_send.py'}")
            elif not full:
                issues.append(label)
        if not refresh:
            issues.append(label)

    if issues:
        print("\n⚠️ 再認証（ブラウザで対象アカウントを選んで許可）:")
        for label, name in TOKENS:
            if label in issues and (MANUAL / name).is_file():
                print(REAUTH_CMD.format(token=name))
        if "estate_send" in issues:
            print("\n⚠️ estate 送信用（readonly+modify+send を一度に付与）:")
            print(
                "cd ~/git-repos/215_kamiooya/C1_cursor/1b_Cursorマニュアル && "
                "~/selenium_env/venv/bin/python reauth_estate_gmail_send.py"
            )
        print(
            "\nヒント: GCP OAuth は本番公開済みなら7日切れは起きにくい。"
            " 取込は token に付いている最小スコープで動く（readonly 単独でもブラウザ不要）。"
            " 送信はフルスコープ必須。send のみスクリプトで token を狭く上書きしない。"
        )
        return 1
    print("\n判定: 取込・送信に必要な token は OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
