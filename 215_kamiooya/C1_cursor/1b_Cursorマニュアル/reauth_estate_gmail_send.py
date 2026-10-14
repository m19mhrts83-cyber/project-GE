#!/usr/bin/env python3
"""token_estate.json を Gmail フルスコープ（readonly+modify+send）で再同意する。

パートナー送信（yoritoori_send）で毎回ブラウザが出るときの是正用。
一度成功すれば refresh_token で自動更新され、毎回の同意は不要。

使い方:
  cd ~/git-repos/215_kamiooya/C1_cursor/1b_Cursorマニュアル
  ~/selenium_env/venv/bin/python reauth_estate_gmail_send.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import webbrowser
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from gmail_api_scopes import GMAIL_SCOPES_215, granted_scopes_from_token_record
from gmail_to_yoritoori import credentials_path

# gmail_token_sync は mail_automation 配下（yoritoori_send / gmail_to_yoritoori と同じ）
_MAIL_AUTO = Path(__file__).resolve().parent.parent / "mail_automation"
if _MAIL_AUTO.is_dir() and str(_MAIL_AUTO) not in sys.path:
    sys.path.insert(0, str(_MAIL_AUTO))
try:
    from gmail_token_sync import save_token_json_and_sync
except ImportError:
    def save_token_json_and_sync(  # type: ignore[misc]
        token_path: Path,
        creds_json: str,
        *,
        log_prefix: str = "📎 Gmail token",
    ) -> None:
        Path(token_path).parent.mkdir(parents=True, exist_ok=True)
        Path(token_path).write_text(creds_json, encoding="utf-8")
        print(
            f"{log_prefix}: WARN gmail_token_sync 未読込のためローカル保存のみ"
            "（OneDrive / GitHub Secret 同期なし）。"
            f" mail_automation を確認してください: {_MAIL_AUTO}",
            file=sys.stderr,
        )


TOKEN = Path(__file__).resolve().parent / "token_estate.json"
LOGIN_HINT = "matsuno.estate@gmail.com"


def main() -> int:
    if not credentials_path.is_file():
        print(f"credentials.json がありません: {credentials_path}", file=sys.stderr)
        return 1

    print(
        "📎 estate 送信用フルスコープ再同意\n"
        f"   アカウント: {LOGIN_HINT}\n"
        "   ブラウザで「許可」してください（読取・変更・送信）。\n"
        "   一度成功すれば、以後は毎回聞かれません。",
        flush=True,
    )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(credentials_path), list(GMAIL_SCOPES_215)
    )
    _wb_get = webbrowser.get

    def _get_and_wrap(using=None):
        ctrl = _wb_get(using)
        _ctrl_open = ctrl.open

        def _open_and_echo(url, new=0, autoraise=True):
            print(f"   認可URL: {url}", flush=True)
            if sys.platform == "darwin":
                try:
                    subprocess.run(
                        ["open", "-a", "Google Chrome", url],
                        check=False,
                        capture_output=True,
                        timeout=10,
                    )
                except Exception:
                    pass
            try:
                return _ctrl_open(url, new=new, autoraise=autoraise)
            except Exception:
                return False

        ctrl.open = _open_and_echo  # type: ignore[method-assign]
        return ctrl

    webbrowser.get = _get_and_wrap  # type: ignore[assignment]
    try:
        creds = flow.run_local_server(
            port=0,
            open_browser=True,
            timeout_seconds=600,
            access_type="offline",
            prompt="consent",
            login_hint=LOGIN_HINT,
        )
    finally:
        webbrowser.get = _wb_get  # type: ignore[assignment]

    save_token_json_and_sync(TOKEN, creds.to_json())
    data = json.loads(TOKEN.read_text(encoding="utf-8"))
    scopes = sorted(granted_scopes_from_token_record(data))
    missing = sorted(set(GMAIL_SCOPES_215) - set(scopes))
    print(f"token 更新: {TOKEN.name}")
    print(f"scopes: {scopes}")
    if missing:
        print(f"不足のまま: {missing}", file=sys.stderr)
        return 1
    if not data.get("refresh_token"):
        print("警告: refresh_token がありません。再度 prompt=consent で実行してください。", file=sys.stderr)
        return 1
    print("✅ 完了。パートナー送信は以後ブラウザ同意なしで動きます。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
