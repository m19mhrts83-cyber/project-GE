#!/usr/bin/env python3
"""
Gmail token を更新し、必要なら GitHub Actions の Secret GMAIL_TOKEN_B64 を更新する。
定期実行（launchd 等）に使う想定。エラーを事前に防ぐため、トークンを自動で新しく保つ。

前提:
  - 215 の credentials.json / token.json（Gmail と同じ）
  - GitHub の Personal Access Token（Secrets: Read and write）を GITHUB_TOKEN または .github_token に設定
  - 環境変数 GITHUB_REPO で owner/repo を指定可能（未設定時は m19mhrts83-cyber/DX-_-）

使い方:
  python refresh_token_and_update_github_secret.py           # 更新＋GitHub に反映
  python refresh_token_and_update_github_secret.py --refresh-only  # Gmail 更新のみ（GitHub は触らない）
  python refresh_token_and_update_github_secret.py --dry-run  # 何も書き換えず確認のみ
"""

import argparse
import base64
import json
import os
import sys
from pathlib import Path

# 215 の credentials を参照（gmail_ai_news_save と同じ）
DEFAULT_CREDENTIALS_DIR = Path(
    "/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1b_Cursorマニュアル"
)
SCRIPT_DIR = Path(__file__).resolve().parent
CREDENTIALS_PATH = Path(os.environ.get("GMAIL_CREDENTIALS_PATH", str(DEFAULT_CREDENTIALS_DIR / "credentials.json")))
TOKEN_PATH = Path(os.environ.get("GMAIL_TOKEN_PATH", str(DEFAULT_CREDENTIALS_DIR / "token.json")))
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]
DEFAULT_GITHUB_REPO = "m19mhrts83-cyber/DX-_-"
GITHUB_SECRET_NAME = "GMAIL_TOKEN_B64"


def load_and_refresh_gmail_token():
    """Gmail の token を読み込み、期限切れなら更新して保存する。"""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CREDENTIALS_PATH.exists():
        print(f"エラー: credentials.json が見つかりません: {CREDENTIALS_PATH}", file=sys.stderr)
        return None

    creds = None
    if TOKEN_PATH.exists():
        try:
            token_data = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
            cred_data = dict(token_data)
            if "client_id" not in cred_data:
                cred_file = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
                client = cred_file.get("installed") or cred_file.get("web", {})
                cred_data["client_id"] = client.get("client_id")
                cred_data["client_secret"] = client.get("client_secret")
                cred_data["token_uri"] = "https://oauth2.googleapis.com/token"
                if "access_token" in cred_data and "token" not in cred_data:
                    cred_data["token"] = cred_data["access_token"]
            creds = Credentials.from_authorized_user_info(cred_data, SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Gmail token の更新に失敗しました（ブラウザで再認証が必要かもしれません）: {e}", file=sys.stderr)
                return None
        else:
            print("Gmail のブラウザ認証が必要です。手元で gmail_ai_news_save.py --list を実行して認証してください。", file=sys.stderr)
            return None

    # 更新後の token を保存（refresh で中身が変わっている場合があるため）
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


def get_github_token():
    """環境変数 GITHUB_TOKEN または .github_token からトークンを取得。"""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return token
    token_file = SCRIPT_DIR / ".github_token"
    if token_file.exists():
        return token_file.read_text(encoding="utf-8").strip()
    return None


def _ascii_header_value(s: str) -> str:
    """HTTP ヘッダ用に ASCII のみにし、UnicodeEncodeError を防ぐ。"""
    return s.encode("ascii", "ignore").decode("ascii").strip()


def get_github_public_key(owner: str, repo: str, token: str):
    """リポジトリの Actions Secrets 用公開鍵を取得。"""
    import urllib.request
    token_ascii = _ascii_header_value(token)
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/secrets/public-key"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token_ascii}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "GitHub-Secret-Update/1.0",
        },
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
    return data.get("key_id"), data.get("key")


def encrypt_secret(public_key_b64: str, plain_value: str) -> str:
    """GitHub の公開鍵で SealedBox 暗号化。"""
    from nacl import encoding, public
    pub = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder())
    box = public.SealedBox(pub)
    encrypted = box.encrypt(plain_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("ascii")


def update_github_secret(owner: str, repo: str, secret_name: str, plain_value: str, token: str) -> bool:
    """GitHub の Repository Secret を更新。"""
    import urllib.request
    key_id, public_key = get_github_public_key(owner, repo, token)
    if not key_id or not public_key:
        print("GitHub の公開鍵の取得に失敗しました。", file=sys.stderr)
        return False
    encrypted = encrypt_secret(public_key, plain_value)
    token_ascii = _ascii_header_value(token)
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/secrets/{secret_name}"
    body = json.dumps({"encrypted_value": encrypted, "key_id": key_id}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="PUT",
        headers={
            "Authorization": f"Bearer {token_ascii}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "GitHub-Secret-Update/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status in (200, 201, 204):
                return True
    except urllib.error.HTTPError as e:
        print(f"GitHub API エラー: {e.code} {e.reason}", file=sys.stderr)
        if e.fp:
            print(e.fp.read().decode(), file=sys.stderr)
    except Exception as e:
        print(f"GitHub 更新中にエラー: {e}", file=sys.stderr)
    return False


def main():
    parser = argparse.ArgumentParser(description="Gmail token を更新し、GitHub Secret GMAIL_TOKEN_B64 を更新")
    parser.add_argument("--refresh-only", action="store_true", help="Gmail の token 更新のみ（GitHub は更新しない）")
    parser.add_argument("--dry-run", action="store_true", help="書き換えせずに確認のみ")
    args = parser.parse_args()

    if args.dry_run:
        print("[dry-run] Gmail token と GitHub Secret の更新をスキップします。")
        if not TOKEN_PATH.exists():
            print("[dry-run] token.json がありません。")
        else:
            print(f"[dry-run] token.json: {TOKEN_PATH}")
        gh_token = get_github_token()
        print(f"[dry-run] GITHUB_TOKEN: {'設定済み' if gh_token else '未設定'}")
        return 0

    # 1. Gmail token を更新
    print("Gmail token を確認・更新しています...")
    creds = load_and_refresh_gmail_token()
    if not creds:
        return 1
    print("Gmail token を更新しました。")

    if args.refresh_only:
        print("--refresh-only のため GitHub は更新しません。")
        return 0

    # 2. GitHub Secret を更新
    gh_token = get_github_token()
    if not gh_token:
        print("GITHUB_TOKEN が未設定のため、GitHub Secret は更新しません。", file=sys.stderr)
        print("環境変数 GITHUB_TOKEN または .github_token を設定すると自動更新されます。", file=sys.stderr)
        return 0

    repo_env = os.environ.get("GITHUB_REPO", "").strip() or DEFAULT_GITHUB_REPO
    if "/" not in repo_env:
        print("GITHUB_REPO は owner/repo 形式で指定してください。", file=sys.stderr)
        return 1
    owner, repo = repo_env.split("/", 1)
    repo = repo.replace(".git", "")

    token_b64 = base64.b64encode(TOKEN_PATH.read_bytes()).decode("ascii").replace("\n", "")
    if update_github_secret(owner, repo, GITHUB_SECRET_NAME, token_b64, gh_token):
        print("GitHub Secret GMAIL_TOKEN_B64 を更新しました。")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
