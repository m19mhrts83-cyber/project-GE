#!/usr/bin/env python3
"""
Jarvis: OneDrive（Microsoft Graph）読取・書込。

認証優先順:
  1) MS_GRAPH_REFRESH_TOKEN（個人用 OneDrive 向け・委任。推奨）
  2) MS_GRAPH_CLIENT_SECRET + TENANT/CLIENT + UPN|DRIVE_ID（職場テナントのアプリ専用）
  3) ローカル CloudStorage（Mac のみ）

初回（個人用）:
  python scripts/jarvis_ms_graph_device_login.py
  → .env.jarvis_private に MS_GRAPH_* を追記

書込には Azure 委任 Files.ReadWrite / Files.ReadWrite.All と再同意が必要。

確認:
  python scripts/jarvis_onedrive_graph.py --dry-run
  python scripts/jarvis_onedrive_graph.py --path "215_神・大家さん倶楽部/…"
  python scripts/jarvis_onedrive_graph.py --append-text "…" --text "\\n# probe\\n"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
LOCAL_ONEDRIVE = Path.home() / "Library/CloudStorage/OneDrive-個人用"
TOKEN_CACHE = Path.home() / ".jarvis_state" / "ms_graph_token_cache.json"

# 読取＋書込（パートナー MD 追記用）。旧 refresh は Read のみのことがある → 再同意。
DELEGATED_SCOPES = (
    "offline_access Files.Read Files.Read.All "
    "Files.ReadWrite Files.ReadWrite.All User.Read"
)


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def has_refresh_auth() -> bool:
    return bool(_env("MS_GRAPH_CLIENT_ID") and _env("MS_GRAPH_REFRESH_TOKEN"))


def has_app_auth() -> bool:
    return bool(
        _env("MS_GRAPH_TENANT_ID")
        and _env("MS_GRAPH_CLIENT_ID")
        and _env("MS_GRAPH_CLIENT_SECRET")
        and (_env("MS_GRAPH_USER_UPN") or _env("MS_GRAPH_DRIVE_ID"))
    )


def graph_configured() -> bool:
    return has_refresh_auth() or has_app_auth()


def _post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"token HTTP {e.code}: {detail}") from e


def _tenant_authority() -> str:
    # consumers = 個人 MSA、organizations = 職場、common = 両方
    return _env("MS_GRAPH_AUTHORITY") or "consumers"


def refresh_access_token() -> str:
    """委任フローの refresh → access。キャッシュあり。

    書込スコープ未同意の refresh でも読取が生きるよう、ReadWrite 失敗時は Read のみで再試行。
    """
    if TOKEN_CACHE.is_file():
        try:
            cached = json.loads(TOKEN_CACHE.read_text(encoding="utf-8"))
            if float(cached.get("expires_at") or 0) > time.time() + 60:
                tok = cached.get("access_token") or ""
                if tok:
                    return tok
        except Exception:
            pass

    client_id = _env("MS_GRAPH_CLIENT_ID")
    refresh = _env("MS_GRAPH_REFRESH_TOKEN")
    secret = _env("MS_GRAPH_CLIENT_SECRET")  # 公開クライアントなら空で可
    auth = _tenant_authority()
    url = f"https://login.microsoftonline.com/{auth}/oauth2/v2.0/token"
    scopes_try = (
        DELEGATED_SCOPES,
        "offline_access Files.Read Files.Read.All User.Read",
    )
    data: dict[str, Any] | None = None
    last_err: Exception | None = None
    for scope in scopes_try:
        form: dict[str, str] = {
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "scope": scope,
        }
        if secret:
            form["client_secret"] = secret
        try:
            data = _post_form(url, form)
            if scope != DELEGATED_SCOPES:
                print(
                    "# note: Graph token is read-only. "
                    "Azure に Files.ReadWrite を足して "
                    "jarvis_ms_graph_device_login.py で再同意してください。",
                    file=sys.stderr,
                )
            break
        except Exception as e:
            last_err = e
            continue
    if data is None:
        raise RuntimeError(f"token refresh failed: {last_err}")
    access = data["access_token"]
    expires_in = int(data.get("expires_in") or 3600)
    new_refresh = data.get("refresh_token")
    TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE.write_text(
        json.dumps(
            {
                "access_token": access,
                "expires_at": time.time() + expires_in,
                "obtained_at": time.time(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    TOKEN_CACHE.chmod(0o600)
    if new_refresh and new_refresh != refresh:
        # プロセス内はすぐ新トークンを使う。永続化は state ＋任意で private / GHA
        os.environ["MS_GRAPH_REFRESH_TOKEN"] = new_refresh
        rot = Path.home() / ".jarvis_state" / "ms_graph_new_refresh.env"
        rot.parent.mkdir(parents=True, exist_ok=True)
        rot.write_text(f"MS_GRAPH_REFRESH_TOKEN={new_refresh}\n", encoding="utf-8")
        rot.chmod(0o600)
        print(
            "# note: refresh_token が回転しました。"
            f" wrote {rot} → python scripts/jarvis_ms_graph_sync_refresh.py"
            " [--push-gha]",
            file=sys.stderr,
        )
    return access


def get_app_token() -> str:
    tenant = _env("MS_GRAPH_TENANT_ID")
    client_id = _env("MS_GRAPH_CLIENT_ID")
    client_secret = _env("MS_GRAPH_CLIENT_SECRET")
    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    return _post_form(
        url,
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
    )["access_token"]


def get_access_token() -> str:
    if has_refresh_auth():
        return refresh_access_token()
    if has_app_auth():
        return get_app_token()
    raise RuntimeError("MS_GRAPH_* 未設定（refresh または app 認証）")


def read_file_local(rel_path: str) -> bytes:
    p = LOCAL_ONEDRIVE / rel_path
    if not p.is_file():
        raise FileNotFoundError(p)
    return p.read_bytes()


def _graph_item_api(rel_path: str) -> str:
    """メタデータ用 URL（:/content ではない）。個人 OneDrive の content は 302+CDN で
    Authorization 付き追従が 401 になるため、downloadUrl を使う。"""
    drive_id = _env("MS_GRAPH_DRIVE_ID")
    upn = _env("MS_GRAPH_USER_UPN")
    encoded = "/".join(urllib.parse.quote(seg) for seg in rel_path.strip("/").split("/"))
    if drive_id:
        return f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{encoded}"
    if upn:
        return (
            f"https://graph.microsoft.com/v1.0/users/{urllib.parse.quote(upn)}"
            f"/drive/root:/{encoded}"
        )
    return f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded}"


def _http_get_bytes(url: str, headers: dict[str, str] | None = None, timeout: int = 90) -> bytes:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {e.code}: {detail}") from e


def read_file_graph(rel_path: str) -> bytes:
    token = get_access_token()
    meta_url = (
        _graph_item_api(rel_path)
        + "?$select=id,name,size,@microsoft.graph.downloadUrl"
    )
    req = urllib.request.Request(meta_url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            meta = json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"graph meta HTTP {e.code}: {detail}") from e

    download_url = meta.get("@microsoft.graph.downloadUrl") or ""
    if download_url:
        # pre-authenticated CDN URL — do NOT send Bearer (breaks with 401)
        return _http_get_bytes(download_url)

    # fallback: /content（職場テナント等で downloadUrl が無い場合）
    # 302 先へ Authorization を付けないよう手動追従
    content_url = _graph_item_api(rel_path) + ":/content"

    class _NoAuthRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
            return urllib.request.Request(newurl)

    opener = urllib.request.build_opener(_NoAuthRedirect)
    try:
        with opener.open(
            urllib.request.Request(
                content_url, headers={"Authorization": f"Bearer {token}"}
            ),
            timeout=90,
        ) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"graph content HTTP {e.code}: {detail}") from e


def read_file(provider: str, path: str) -> bytes:
    """共通インターフェース。provider: onedrive | local"""
    provider = (provider or "onedrive").lower()
    if provider in ("onedrive", "graph"):
        if graph_configured():
            return read_file_graph(path)
        return read_file_local(path)
    if provider == "local":
        return read_file_local(path)
    raise ValueError(f"unknown provider: {provider}")


def get_item_meta(rel_path: str) -> dict[str, Any]:
    """id / eTag / size / name。無いファイルは FileNotFoundError。"""
    token = get_access_token()
    meta_url = (
        _graph_item_api(rel_path)
        + "?$select=id,name,size,eTag,cTag,@microsoft.graph.downloadUrl"
    )
    req = urllib.request.Request(meta_url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        if e.code == 404:
            raise FileNotFoundError(rel_path) from e
        raise RuntimeError(f"graph meta HTTP {e.code}: {detail}") from e


def upload_file_graph(
    rel_path: str,
    content: bytes,
    *,
    if_match: str | None = None,
    content_type: str = "application/octet-stream",
) -> dict[str, Any]:
    """小ファイル（〜4MB）を PUT :/content で上書き。if_match で楽観ロック。"""
    token = get_access_token()
    url = _graph_item_api(rel_path) + ":/content"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": content_type,
    }
    if if_match:
        headers["If-Match"] = if_match
    req = urllib.request.Request(url, data=content, method="PUT", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
            if not raw:
                return {"ok": True, "bytes": len(content)}
            try:
                return json.loads(raw)
            except Exception:
                return {"ok": True, "bytes": len(content)}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"graph upload HTTP {e.code}: {detail}") from e


def write_file_local(rel_path: str, content: bytes) -> None:
    p = LOCAL_ONEDRIVE / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


def write_file(provider: str, path: str, content: bytes, *, if_match: str | None = None) -> dict[str, Any]:
    provider = (provider or "onedrive").lower()
    if provider in ("onedrive", "graph"):
        if graph_configured():
            return upload_file_graph(path, content, if_match=if_match)
        write_file_local(path, content)
        return {"ok": True, "bytes": len(content), "via": "local"}
    if provider == "local":
        write_file_local(path, content)
        return {"ok": True, "bytes": len(content), "via": "local"}
    raise ValueError(f"unknown provider: {provider}")


def append_text_graph(
    rel_path: str,
    block: str,
    *,
    transform: Callable[[str, str], str] | None = None,
    encoding: str = "utf-8",
    retries: int = 2,
) -> dict[str, Any]:
    """読取 → 結合（または transform）→ PUT。412 なら再読取してリトライ。

    transform(old_text, block) -> new_text。未指定時は末尾追記。
    """
    last_err: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            meta = get_item_meta(rel_path)
            etag = meta.get("eTag") or meta.get("cTag")
            raw = read_file_graph(rel_path)
            old = raw.decode(encoding, errors="replace")
            if transform:
                new = transform(old, block)
            else:
                new = old.rstrip() + "\n" + block
            if new == old:
                return {"ok": True, "unchanged": True, "bytes": len(raw)}
            data = new.encode(encoding)
            out = upload_file_graph(rel_path, data, if_match=etag)
            return {
                "ok": True,
                "bytes": len(data),
                "etag": out.get("eTag") or etag,
                "attempt": attempt + 1,
            }
        except Exception as e:
            last_err = e
            msg = str(e)
            if "412" in msg or "Precondition" in msg:
                time.sleep(0.4 * (attempt + 1))
                continue
            raise
    raise RuntimeError(f"append_text_graph failed after retries: {last_err}")


def probe_me(token: str) -> dict[str, Any]:
    req = urllib.request.Request(
        "https://graph.microsoft.com/v1.0/me?$select=displayName,userPrincipalName,mail,id",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--path", default="")
    ap.add_argument("--provider", default="onedrive")
    ap.add_argument("--probe", action="store_true", help="token 取得＋ /me 確認")
    ap.add_argument(
        "--append-text",
        default="",
        help="相対パスへテキスト追記（Graph 書込。試験用）",
    )
    ap.add_argument("--text", default="", help="--append-text 用の本文")
    args = ap.parse_args(argv)

    status: dict[str, Any] = {
        "graph_configured": graph_configured(),
        "auth_mode": (
            "refresh" if has_refresh_auth() else ("app" if has_app_auth() else "none")
        ),
        "local_onedrive_exists": LOCAL_ONEDRIVE.is_dir(),
        "provider": args.provider,
        "authority": _tenant_authority() if has_refresh_auth() else (_env("MS_GRAPH_TENANT_ID") or None),
        "scopes": DELEGATED_SCOPES,
    }
    if args.dry_run and not args.probe and not args.path and not args.append_text:
        print(json.dumps(status, ensure_ascii=False, indent=2))
        if not graph_configured():
            print(
                "# 未設定。個人用 OneDrive は:\n"
                "#   1) Azure でアプリ登録（個人アカウント対応）\n"
                "#   2) python scripts/jarvis_ms_graph_device_login.py\n"
                "# 手順: docs/Jarvis_OneDrive_Graph.md",
                file=sys.stderr,
            )
        return 0

    if args.probe or (graph_configured() and not args.path and not args.append_text):
        try:
            tok = get_access_token()
            me = probe_me(tok)
            status["probe_ok"] = True
            status["me"] = {
                "displayName": me.get("displayName"),
                "userPrincipalName": me.get("userPrincipalName"),
                "mail": me.get("mail"),
            }
        except Exception as e:
            status["probe_ok"] = False
            status["probe_error"] = str(e)[:300]
            print(json.dumps(status, ensure_ascii=False, indent=2))
            return 1
        print(json.dumps(status, ensure_ascii=False, indent=2))
        if not args.path and not args.append_text:
            return 0

    if args.append_text:
        if not (args.text or "").strip():
            print("--text が空です", file=sys.stderr)
            return 2
        out = append_text_graph(args.append_text, args.text)
        print(json.dumps({**status, "append": out, "path": args.append_text}, ensure_ascii=False, indent=2))
        return 0

    data = read_file(args.provider, args.path)
    print(
        json.dumps(
            {
                **status,
                "path": args.path,
                "bytes": len(data),
                "preview": data[:120].decode("utf-8", errors="replace"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
