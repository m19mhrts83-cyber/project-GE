#!/usr/bin/env python3
"""借入残高トラッカー → KURASHIFT 投影（読取のみ・書込しない）。

データは loan-tracker アプリの画面ではなく、ログインした Google アカウントの
Drive（多くの場合アプリ専用の隠し領域 appDataFolder）に JSON として保存される。
KURASHIFT はそれを読んで kurashift_loan_tracker_loans に投影する。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_loan_tracker_sync.py --discover
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_loan_tracker_sync.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_loan_tracker_sync.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
DISCOVER = REPO / "docs" / "KURASHIFT_loan_tracker_Discover.md"
APP_URL = "https://loan-tracker-plum.vercel.app/"
DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.appdata",
]
NAME_HINTS = (
    "loan-tracker",
    "loan_tracker",
    "借入残高",
    "loans.json",
    "loan-tracker-data",
)


def sb_client() -> Any:
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です")
    from supabase import create_client

    return create_client(url, key)


def token_paths() -> list[Path]:
    extra = (os.environ.get("LOAN_TRACKER_DRIVE_TOKEN_PATH") or "").strip()
    names = [
        extra,
        str(MANUAL / "token_estate_drive.json"),
        str(MANUAL / "token_estate.json"),
        str(MANUAL / "token_livingsupport.json"),
        str(MANUAL / "token_m19m.json"),
    ]
    out: list[Path] = []
    seen: set[str] = set()
    for n in names:
        if not n:
            continue
        p = Path(n).expanduser()
        if str(p) in seen:
            continue
        seen.add(str(p))
        out.append(p)
    return out


def load_drive_service(path: Path) -> Any | None:
    if not path.is_file():
        return None
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(str(path))
    scopes = set(creds.scopes or [])
    if not any("drive" in s for s in scopes):
        print(f"# skip {path.name}: Drive scope なし")
        return None
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def drive_search(svc: Any, *, space: str) -> list[dict[str, Any]]:
    q = " or ".join(f"name contains '{h}'" for h in ("loan", "借入", "tracker"))
    kwargs: dict[str, Any] = {
        "q": f"({q}) and trashed=false",
        "pageSize": 50,
        "fields": "files(id,name,mimeType,modifiedTime,size,parents,spaces)",
        "supportsAllDrives": True,
        "includeItemsFromAllDrives": True,
    }
    if space == "appDataFolder":
        kwargs["spaces"] = "appDataFolder"
        kwargs["q"] = "trashed=false"
    resp = svc.files().list(**kwargs).execute()
    files = resp.get("files") or []
    if space == "appDataFolder":
        files = [
            f
            for f in files
            if any(h in (f.get("name") or "").lower() for h in ("loan", "json", "借入", "tracker"))
            or True
        ]
    return files


def download_file(svc: Any, file_id: str) -> bytes:
    from googleapiclient.http import MediaIoBaseDownload
    import io

    buf = io.BytesIO()
    req = svc.files().get_media(fileId=file_id)
    downloader = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def normalize_loans(payload: Any) -> list[dict[str, Any]]:
    """loan-tracker の JSON 形が版で違っても、一覧配列を拾う。"""
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        for key in ("loans", "items", "borrowings", "data", "records"):
            if isinstance(payload.get(key), list):
                rows = payload[key]
                break
        else:
            rows = [payload]
    else:
        return []

    out: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()
    for i, raw in enumerate(rows):
        if not isinstance(raw, dict):
            continue
        lid = str(raw.get("id") or raw.get("loanId") or f"row-{i}")
        name = raw.get("name") or raw.get("title") or raw.get("label") or lid
        lender = raw.get("lender") or raw.get("bank") or raw.get("institution")
        tags = raw.get("tags") or raw.get("categories") or []
        if isinstance(tags, str):
            tags = [tags]
        major = raw.get("categoryMajor") or raw.get("major") or raw.get("group")
        if not major and tags:
            for t in tags:
                if t in ("不動産", "プライベート", "#不動産", "#住宅"):
                    major = t.lstrip("#")
                    break
        def num(*keys: str) -> float | None:
            for k in keys:
                v = raw.get(k)
                if v is None or v == "":
                    continue
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
            return None

        out.append(
            {
                "id": lid[:120],
                "name": str(name)[:200],
                "lender": (str(lender)[:120] if lender else None),
                "category_major": (str(major)[:80] if major else None),
                "tags": [str(t) for t in tags][:20],
                "principal_jpy": num("principal", "principalJpy", "amount", "originalAmount"),
                "balance_jpy": num("balance", "balanceJpy", "remaining", "currentBalance"),
                "monthly_payment_jpy": num("monthlyPayment", "monthly", "paymentMonthly"),
                "annual_payment_jpy": num("annualPayment", "yearlyPayment"),
                "rate_pct": num("rate", "interestRate", "ratePct"),
                "rate_type": raw.get("rateType") or raw.get("interestType"),
                "start_date": raw.get("startDate") or raw.get("contractStart"),
                "payoff_date": raw.get("payoffDate") or raw.get("endDate"),
                "payload": raw,
                "synced_at": now,
            }
        )
    return out


def discover() -> dict[str, Any]:
    result: dict[str, Any] = {
        "app_url": APP_URL,
        "google_account": "estate（アプリログインと同じ Google）",
        "where_data_lives": (
            "画面の表ではなく、Google ログイン後に Drive へ保存される専用ファイル。"
            "マイドライブに見えないことが多い（appDataFolder＝アプリ専用の隠し領域）。"
            "API はログイン後 GET /api/data。"
        ),
        "visible_drive_search": [],
        "appdata_search": [],
        "json_path": (os.environ.get("LOAN_TRACKER_JSON_PATH") or "").strip() or None,
        "sheet_id": (os.environ.get("LOAN_TRACKER_SHEET_ID") or "").strip() or None,
        "folder_id": (os.environ.get("LOAN_TRACKER_DRIVE_FOLDER_ID") or "").strip() or None,
        "blocker": None,
    }
    json_path = result["json_path"]
    if json_path and Path(json_path).expanduser().is_file():
        result["blocker"] = None
        result["ready"] = "json_path"
        return result

    any_drive = False
    for path in token_paths():
        try:
            svc = load_drive_service(path)
        except Exception as e:
            print(f"# token {path.name}: {type(e).__name__}: {e}")
            continue
        if not svc:
            continue
        any_drive = True
        try:
            vis = drive_search(svc, space="drive")
            result["visible_drive_search"].append(
                {"token": path.name, "count": len(vis), "files": vis[:15]}
            )
        except Exception as e:
            result["visible_drive_search"].append(
                {"token": path.name, "error": f"{type(e).__name__}: {e}"}
            )
        try:
            hid = drive_search(svc, space="appDataFolder")
            result["appdata_search"].append(
                {"token": path.name, "count": len(hid), "files": hid[:15]}
            )
        except Exception as e:
            result["appdata_search"].append(
                {"token": path.name, "error": f"{type(e).__name__}: {e}"}
            )

    hits = []
    for block in result["visible_drive_search"] + result["appdata_search"]:
        hits.extend(block.get("files") or [])
    if hits:
        result["ready"] = "drive_files"
        result["picked"] = hits[0]
        return result
    if not any_drive:
        result["blocker"] = (
            "estate の token に Drive 権限がない。"
            "loan-tracker と同じ Google（estate）で Drive 読取 OAuth するか、"
            "アプリから JSON を書き出して LOAN_TRACKER_JSON_PATH を渡す。"
        )
    else:
        result["blocker"] = (
            "Drive は読めたが loan-tracker のファイルが見つからない。"
            "アプリ専用領域は loan-tracker 自身の OAuth クライアントしか見えないことがある。"
            "その場合はアプリ画面から JSON/CSV 書き出し、またはログイン済み /api/data が必要。"
        )
    return result


def load_payload_from_discover(disc: dict[str, Any]) -> Any:
    json_path = disc.get("json_path")
    if json_path:
        return json.loads(Path(json_path).expanduser().read_text(encoding="utf-8"))
    picked = disc.get("picked")
    if not picked:
        return None
    file_id = picked.get("id")
    for path in token_paths():
        svc = load_drive_service(path)
        if not svc:
            continue
        try:
            raw = download_file(svc, file_id)
            return json.loads(raw.decode("utf-8"))
        except Exception:
            continue
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--discover", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply and not args.discover:
        args.dry_run = True

    print("使用アカウント: estate / 借入残高トラッカーは Drive 保存（画面の表はコピーではない）")
    disc = discover()
    print(json.dumps({k: v for k, v in disc.items() if k != "picked" or v}, ensure_ascii=False, indent=2)[:8000])

    if args.discover and not args.apply and not args.dry_run:
        print(f"📎 loan_tracker: discover 完了。詳細 {DISCOVER}")
        return 0 if not disc.get("blocker") else 2

    if disc.get("blocker") and not disc.get("json_path") and not disc.get("picked"):
        print("KURASHIFT_RESULT:" + json.dumps({"ok": False, "blocker": disc["blocker"]}, ensure_ascii=False))
        print(f"取得失敗: {disc['blocker']}", file=sys.stderr)
        return 2

    payload = load_payload_from_discover(disc)
    if payload is None:
        msg = "ファイルは見つかったが中身を読めない／JSON パス未設定"
        print("KURASHIFT_RESULT:" + json.dumps({"ok": False, "blocker": msg}, ensure_ascii=False))
        print(f"取得失敗: {msg}", file=sys.stderr)
        return 2

    loans = normalize_loans(payload)
    print(f"# normalized loans={len(loans)}")
    for row in loans[:8]:
        print(f"  - {row.get('category_major') or '-'} {row.get('lender') or '-'} {row['name']} 残高={row.get('balance_jpy')}")

    if args.dry_run and not args.apply:
        print("📎 loan_tracker: dry-run（--apply で投影）")
        return 0

    sb = sb_client()
    upserted = 0
    for row in loans:
        sb.table("kurashift_loan_tracker_loans").upsert(row).execute()
        upserted += 1
    print(f"📎 loan_tracker: upserted={upserted}")
    print("KURASHIFT_RESULT:" + json.dumps({"ok": True, "upserted": upserted}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
