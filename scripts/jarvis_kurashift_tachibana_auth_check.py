#!/usr/bin/env python3
"""立花証券e支店API（公開鍵認証）の認証情報 readiness チェック。

値（AuthID・秘密鍵・仮想URL）は**一切表示しない**。存在・権限・形式・接続可否だけ。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_tachibana_auth_check.py
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_tachibana_auth_check.py --probe

取得手順: docs/KURASHIFT_立花API_認証設定.md
接続先: v4r10 本番 / デモ（v4r9 は 2026-09-27 廃止）
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import stat
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
P_NO_PATH = REPO / ".jarvis_state" / "tachibana_p_no.json"

DEFAULT_PROD_BASE = "https://kabuka.e-shiten.jp/e_api_v4r10/"
DEFAULT_DEMO_BASE = "https://demo-kabuka.e-shiten.jp/e_api_v4r10/"


def _truthy(v: str | None) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


def _env(key: str, default: str = "") -> str:
    return (os.environ.get(key) or default).strip()


def is_demo() -> bool:
    return _truthy(_env("TACHIBANA_API_DEMO", "1"))


def api_base() -> str:
    if is_demo():
        return _env("TACHIBANA_API_DEMO_BASE", DEFAULT_DEMO_BASE)
    return _env("TACHIBANA_API_BASE", DEFAULT_PROD_BASE)


def _mode_ok(path: Path) -> tuple[bool, str]:
    try:
        mode = path.stat().st_mode
    except OSError:
        return False, "stat不能"
    if mode & (stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH):
        return False, oct(stat.S_IMODE(mode)) + "（他ユーザ読取可: chmod 600 推奨）"
    return True, oct(stat.S_IMODE(mode))


def check_file(label: str, raw_path: str) -> dict[str, Any]:
    row: dict[str, Any] = {"label": label, "path_set": bool(raw_path), "ok": False}
    if not raw_path:
        row["detail"] = "未設定"
        return row
    p = Path(os.path.expanduser(raw_path))
    row["path"] = str(p)
    if not p.is_file():
        row["detail"] = "ファイルがありません"
        return row
    size = p.stat().st_size
    row["size"] = size
    if size <= 0:
        row["detail"] = "空ファイル"
        return row
    perm_ok, perm_desc = _mode_ok(p)
    row["perm"] = perm_desc
    row["perm_ok"] = perm_ok
    row["ok"] = True
    row["detail"] = "OK" if perm_ok else "存在（権限を確認）"
    return row


def check_private_key(raw_path: str) -> dict[str, Any]:
    row: dict[str, Any] = {"ok": False}
    if not raw_path:
        row["detail"] = "未設定"
        return row
    p = Path(os.path.expanduser(raw_path))
    if not p.is_file():
        row["detail"] = "ファイルがありません"
        return row
    try:
        from Cryptodome.PublicKey import RSA

        pem = p.read_text(encoding="utf-8-sig")
        key = RSA.import_key(pem)
        row["ok"] = True
        row["bits"] = key.size_in_bits()
        row["has_private"] = key.has_private()
        row["detail"] = f"RSA {key.size_in_bits()}bit"
    except Exception as e:  # noqa: BLE001
        row["detail"] = f"RSA秘密鍵として読めません: {type(e).__name__}"
    return row


def check_auth_id(raw_path: str) -> dict[str, Any]:
    """AuthID は読むが値は出さない（長さ・文字種のみ）。"""
    row: dict[str, Any] = {"ok": False}
    if not raw_path:
        row["detail"] = "未設定"
        return row
    p = Path(os.path.expanduser(raw_path))
    if not p.is_file():
        row["detail"] = "ファイルがありません"
        return row
    try:
        val = p.read_text(encoding="utf-8-sig").strip()
    except Exception as e:  # noqa: BLE001
        row["detail"] = f"読めません: {type(e).__name__}"
        return row
    if not val:
        row["detail"] = "空"
        return row
    row["length"] = len(val)
    row["alnum"] = val.isalnum()
    row["ok"] = True
    row["detail"] = f"{len(val)}桁・{'英数のみ' if val.isalnum() else '英数以外を含む'}"
    return row


def p_no_load() -> int:
    if P_NO_PATH.is_file():
        try:
            data = json.loads(P_NO_PATH.read_text(encoding="utf-8"))
            return int(data.get("p_no") or 1)
        except Exception:  # noqa: BLE001
            return 1
    return 1


def p_no_save(n: int) -> None:
    P_NO_PATH.parent.mkdir(parents=True, exist_ok=True)
    P_NO_PATH.write_text(json.dumps({"p_no": str(n)}, ensure_ascii=False) + "\n", encoding="utf-8")


def _p_sd_date() -> str:
    dt = datetime.now(ZoneInfo("Asia/Tokyo"))
    return dt.strftime("%Y.%m.%d-%H:%M:%S") + "." + f"{dt.microsecond:06d}"[0:3]


def _read_secret(path: str) -> str:
    return Path(os.path.expanduser(path)).read_text(encoding="utf-8-sig").strip()


def probe(auth_path: str, key_path: str, *, timeout: float = 15.0) -> dict[str, Any]:
    """公開鍵認証でログインし、仮想URL（1日券）が取れるかだけ確認。値は出さない。"""
    auth_id = _read_secret(auth_path)
    p_no = p_no_load()
    req = {
        "p_no": str(p_no),
        "p_sd_date": _p_sd_date(),
        "sCLMID": "CLMAuthLoginRequest",
        "sAuthId": auth_id,
        "sJsonOfmt": "5",
    }
    query = json.dumps(req, ensure_ascii=False, separators=(",", ":"))
    base = api_base()
    url = urllib.parse.urljoin(base, "auth/") + "?" + query
    masked = url.replace(auth_id, auth_id[:3] + "*" * max(len(auth_id) - 6, 0) + auth_id[-3:])
    print(f"# probe login: {masked[:120]}{'…' if len(masked) > 120 else ''}")
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            raw = resp.read()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": f"通信失敗: {type(e).__name__}: {e}"}
    text = raw.decode("shift-jis", errors="ignore")
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        return {"ok": False, "detail": "応答がJSONではありません", "preview": text[:120]}
    errno = str(out.get("p_errno", ""))
    if errno != "0":
        return {"ok": False, "detail": f"p_errno={errno} p_err={out.get('p_err')}"}
    enc = out.get("sUrl") or out.get("sUrlRequest") or ""
    if not enc:
        return {"ok": False, "detail": "sUrl が応答にありません"}
    try:
        from Cryptodome.Cipher import PKCS1_OAEP
        from Cryptodome.Hash import SHA256
        from Cryptodome.PublicKey import RSA

        key = RSA.import_key(Path(os.path.expanduser(key_path)).read_text(encoding="utf-8-sig"))
        dec = PKCS1_OAEP.new(key, hashAlgo=SHA256)
        virtual = dec.decrypt(base64.b64decode(enc.strip().replace('"', ""))).decode("utf-8-sig").strip()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": f"仮想URLの復号に失敗: {type(e).__name__}"}
    p_no_save(p_no + 1)
    return {"ok": True, "detail": "ログイン成功・仮想URL取得", "virtual_host": urllib.parse.urlparse(virtual).netloc}


def push_sync_meta(report: dict[str, Any]) -> None:
    """ダッシュボード／stock-watch 向けに readiness だけ投影（秘密は出さない）。"""
    try:
        from jarvis_trade_common import sb_client
    except Exception as e:  # noqa: BLE001
        print(f"# sync_meta soft-fail import: {e}", file=sys.stderr)
        return
    ts = datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds")
    slim = {
        "ready": bool(report.get("ready")),
        "env": report.get("env"),
        "api_base": report.get("api_base"),
        "version": report.get("version"),
        "auth_id": (report.get("auth_id") or {}).get("detail"),
        "private_key": (report.get("private_key") or {}).get("detail"),
        "probe": (report.get("probe") or {}).get("detail") if report.get("probe") else None,
        "checked_at": ts,
    }
    try:
        sb = sb_client()
        sb.table("sync_meta").upsert(
            [
                {"key": "tachibana_api_ready", "value": "1" if slim["ready"] else "0", "updated_at": ts},
                {
                    "key": "tachibana_api_status",
                    "value": json.dumps(slim, ensure_ascii=False)[:4000],
                    "updated_at": ts,
                },
            ],
            on_conflict="key",
        ).execute()
        print(f"# sync_meta pushed tachibana_api_ready={'1' if slim['ready'] else '0'}")
    except Exception as e:  # noqa: BLE001
        print(f"# sync_meta soft-fail: {e}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="立花e支店API 認証 readiness")
    ap.add_argument("--probe", action="store_true", help="デモ/本番へログインのみ試す（値は出さない）")
    ap.add_argument("--push", action="store_true", help="sync_meta に readiness を投影")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    auth_path = _env("TACHIBANA_API_AUTH_ID_PATH")
    key_path = _env("TACHIBANA_API_PRIVATE_KEY_PATH")

    report: dict[str, Any] = {
        "env": "demo" if is_demo() else "prod",
        "api_base": api_base(),
        "version": _env("TACHIBANA_API_VERSION", "4r10"),
        "auth_id": check_auth_id(auth_path),
        "auth_id_file": check_file("auth_id_file", auth_path),
        "private_key_file": check_file("private_key_file", key_path),
        "private_key": check_private_key(key_path),
    }
    ready = bool(
        report["auth_id"].get("ok")
        and report["auth_id_file"].get("ok")
        and report["private_key_file"].get("ok")
        and report["private_key"].get("ok")
    )
    report["ready"] = ready
    if args.probe:
        if not ready:
            report["probe"] = {"ok": False, "detail": "認証情報が未整備のため probe 不可"}
        else:
            report["probe"] = probe(auth_path, key_path)

    if args.push:
        push_sync_meta(report)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("📎 立花e支店API 認証 readiness（値は表示しません）")
        print(f"  環境: {report['env']} / {report['api_base']} (v{report['version']})")
        print(f"  認証ID : {report['auth_id'].get('detail')}")
        print(f"  秘密鍵 : {report['private_key'].get('detail')} / {report['private_key_file'].get('perm','-')}")
        print(f"  判定   : {'READY' if ready else 'NOT READY'}")
        if args.probe and "probe" in report:
            print(f"  probe  : {report['probe'].get('detail')}")
        if not ready:
            print("  → docs/KURASHIFT_立花API_認証設定.md の手順で鍵を取得・配置してください。")

    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
