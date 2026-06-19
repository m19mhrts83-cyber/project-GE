#!/usr/bin/env python3
"""
LEAF（くらさぽコネクト）オーナーサイトから送金明細書 PDF をダウンロードする。

取得元:
  https://owner.kurasapo-connect.com/login
  → ログイン後「報告書」→ 送金明細書（支払明細書）を PDF 保存

認証情報: .env.tax_docs（同ディレクトリ）に
  KURASAPO_OWNER_LOGIN_ID / KURASAPO_OWNER_PASSWORD を設定する。
  （LEAF 案内メール添付「オーナーIDパスワード（…）.pdf」参照。初回ログイン後に変更済みの場合は現行 PW を設定）

使い方:
  python leaf_kurasapo_statement.py \
      --latest \
      --output-dir ".../516_名古屋銀行/3.送信添付/"

  python leaf_kurasapo_statement.py \
      --count 2 \
      --output-dir ".../00_元ファイル_サイト取得/LEAF/"

  # ログイン画面で手動入力（PW 未設定時）
  python leaf_kurasapo_statement.py --latest --output-dir "..." --manual-login
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = SCRIPT_DIR / ".env.tax_docs"

KURASAPO_LOGIN_URL = os.environ.get(
    "KURASAPO_OWNER_LOGIN_URL", "https://owner.kurasapo-connect.com/login"
)
KURASAPO_BASE_URL = os.environ.get(
    "KURASAPO_OWNER_BASE_URL", "https://owner.kurasapo-connect.com"
)
DEFAULT_BUNSYO_FILTER = "送金明細"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and value and key not in os.environ:
            os.environ[key] = value


def _wait_ready(page, *, timeout_ms: int = 15000) -> None:
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    try:
        page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 10000))
    except Exception:
        pass


def _login(page, login_id: str, password: str) -> None:
    page.goto(KURASAPO_LOGIN_URL, wait_until="load")
    _wait_ready(page)
    page.fill("#owner_id", login_id)
    page.fill("#password", password)
    page.click('input[type="submit"]')
    _wait_ready(page, timeout_ms=30000)
    page.wait_for_timeout(1500)

    if "/login" in page.url:
        body = page.inner_text("body")
        if "間違っています" in body:
            raise RuntimeError(
                "くらさぽコネクトのログインに失敗しました。"
                " .env.tax_docs の KURASAPO_OWNER_LOGIN_ID / KURASAPO_OWNER_PASSWORD を確認してください。"
                " 初回パスワード変更済みの場合は現行パスワードを設定するか、--manual-login を使ってください。"
            )
        if "ログイン試行回数が多すぎます" in body:
            raise RuntimeError(
                "くらさぽコネクトがログイン試行回数制限中です。数分待ってから再実行するか、"
                " Chrome で手動ログイン後に --manual-login を使ってください。"
            )
        raise RuntimeError(f"ログイン後もログイン画面のままです: {page.url}")
    print(f"  ログイン成功: {page.url}")


def _manual_login(page) -> None:
    page.goto(KURASAPO_LOGIN_URL, wait_until="load")
    print("  ブラウザでログインしてください。完了したら Playwright Inspector の Resume を押してください。")
    page.pause()
    if "/login" in page.url:
        raise RuntimeError("手動ログインが完了していません（ログイン画面のまま）。")
    print(f"  手動ログイン成功: {page.url}")


def _fetch_reports(page, bunsyo_filter: str = "") -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "isShowFiles": "true",
        "isShowHiddenItem": "false",
    }
    if bunsyo_filter:
        params["bunsyoNameSearchBox"] = bunsyo_filter

    resp = page.request.get(f"{KURASAPO_BASE_URL}/report/search", params=params)
    if not resp.ok:
        raise RuntimeError(f"報告書一覧の取得に失敗しました: HTTP {resp.status}")

    payload = resp.json()
    data = payload.get("data") or payload
    report_block = data.get("dataReport") or data
    items = report_block.get("infoShowReportsParam") or []
    if not isinstance(items, list):
        raise RuntimeError("報告書一覧の形式が想定外です（infoShowReportsParam）")
    return items


def _item_text(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, val in item.items():
        if isinstance(val, (str, int, float)):
            parts.append(str(val))
        elif isinstance(val, list):
            for sub in val:
                if isinstance(sub, dict):
                    parts.extend(str(v) for v in sub.values() if isinstance(v, (str, int, float)))
    return " ".join(parts)


def _parse_item_date(item: dict[str, Any]) -> datetime:
    for key in ("torihiki_ymd", "soushin_ymd", "send_ymd", "created_at", "updated_at"):
        raw = item.get(key)
        if not raw:
            continue
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d %H:%M:%S"):
            try:
                return datetime.strptime(str(raw)[:19], fmt)
            except ValueError:
                continue
    m = re.search(r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})", _item_text(item))
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return datetime.min


def _is_soukin_meisai(item: dict[str, Any], bunsyo_filter: str) -> bool:
    text = _item_text(item)
    if bunsyo_filter and bunsyo_filter in text:
        return True
    keywords = ("送金明細", "支払明細", "送金のご案内")
    return any(k in text for k in keywords)


def _collect_pdf_targets(item: dict[str, Any]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    files = item.get("files") or []
    if isinstance(files, list):
        for f in files:
            if not isinstance(f, dict):
                continue
            if f.get("is_image") == 1:
                continue
            file_id = f.get("id")
            if file_id is not None:
                targets.append({"id": file_id, "name": f.get("name") or f.get("file_name") or ""})
    file_id = item.get("file_id") or item.get("id")
    if file_id is not None and not targets:
        targets.append({"id": file_id, "name": item.get("bunsyo") or item.get("torihiki_name") or ""})
    return targets


def _output_name(item: dict[str, Any], file_hint: str = "") -> str:
    dt = _parse_item_date(item)
    if dt != datetime.min:
        label = f"{dt.year}年{dt.month}月"
    else:
        label = datetime.now().strftime("%Y年%m月")
    suffix = ""
    if file_hint:
        m = re.search(r"(\d{4})[年.](\d{1,2})", file_hint)
        if m:
            label = f"{m.group(1)}年{int(m.group(2))}月"
    return f"LEAF_送金明細書_{label}.pdf"


def _download_pdf(page, file_id: Any, dest: Path) -> None:
    url = f"{KURASAPO_BASE_URL}/file/pdf/{file_id}"
    resp = page.request.get(url)
    if not resp.ok:
        raise RuntimeError(f"PDF ダウンロード失敗: {url} (HTTP {resp.status})")
    body = resp.body()
    if not body.startswith(b"%PDF"):
        raise RuntimeError(f"PDF ではない応答: {url}")
    dest.write_bytes(body)
    print(f"  ✅ ダウンロード完了: {dest.name} ({len(body) // 1024}KB)")


def _select_items(
    items: list[dict[str, Any]],
    *,
    bunsyo_filter: str,
    latest: bool,
    count: int | None,
    months: list[tuple[int, int]] | None,
) -> list[dict[str, Any]]:
    filtered = [it for it in items if _is_soukin_meisai(it, bunsyo_filter)]
    if not filtered:
        filtered = items

    if months:
        wanted = set(months)
        month_filtered = []
        for it in filtered:
            dt = _parse_item_date(it)
            if dt != datetime.min and (dt.year, dt.month) in wanted:
                month_filtered.append(it)
        filtered = month_filtered or filtered

    filtered.sort(key=_parse_item_date, reverse=True)

    if latest:
        return filtered[:1]
    if count is not None:
        return filtered[:count]
    return filtered


def run(
    *,
    output_dir: Path,
    latest: bool = True,
    count: int | None = None,
    months: list[tuple[int, int]] | None = None,
    bunsyo_filter: str = DEFAULT_BUNSYO_FILTER,
    headed: bool = True,
    dry_run: bool = False,
    pause_on_error: bool = True,
    manual_login: bool = False,
) -> list[dict]:
    login_id = os.environ.get("KURASAPO_OWNER_LOGIN_ID", "")
    password = os.environ.get("KURASAPO_OWNER_PASSWORD", "")

    if not manual_login and not all([login_id, password]):
        print(
            "エラー: KURASAPO_OWNER_LOGIN_ID / KURASAPO_OWNER_PASSWORD が未設定です。\n"
            f"  → {DEFAULT_ENV_PATH} を編集するか、--manual-login を指定してください。",
            file=sys.stderr,
        )
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            print("[1/3] くらさぽコネクトにログイン中...")
            if manual_login:
                _manual_login(page)
            else:
                _login(page, login_id, password)

            print("[2/3] 報告書一覧を取得...")
            items = _fetch_reports(page, bunsyo_filter=bunsyo_filter)
            print(f"  一覧: {len(items)} 件（フィルタ前）")
            selected = _select_items(
                items,
                bunsyo_filter=bunsyo_filter,
                latest=latest,
                count=count,
                months=months,
            )
            if not selected:
                print("  ⚠ 送金明細書が見つかりませんでした")
                return results

            print(f"[3/3] PDF ダウンロード ({len(selected)} 件)...")
            for item in selected:
                targets = _collect_pdf_targets(item)
                if not targets:
                    print(f"  ⚠ PDF 添付なし: {_item_text(item)[:80]}")
                    results.append({"status": "no_pdf", "item": item})
                    continue
                for tgt in targets:
                    dest = output_dir / _output_name(item, str(tgt.get("name") or ""))
                    if dest.exists():
                        print(f"  ⚠ 既に存在 → スキップ: {dest.name}")
                        results.append({"status": "skipped", "path": dest})
                        continue
                    if dry_run:
                        print(f"  [dry-run] {dest.name} (file_id={tgt['id']})")
                        results.append({"status": "dry-run", "path": dest})
                        continue
                    try:
                        _download_pdf(page, tgt["id"], dest)
                        results.append({"status": "ok", "path": dest})
                    except Exception as e:
                        print(f"  ❌ {dest.name}: {e}", file=sys.stderr)
                        results.append({"status": "failed", "path": dest, "error": str(e)})

        except PlaywrightTimeoutError as e:
            print(f"タイムアウト: {e}", file=sys.stderr)
            if pause_on_error and headed:
                try:
                    page.pause()
                except KeyboardInterrupt:
                    pass
            raise
        except Exception as e:
            print(f"エラー: {e}", file=sys.stderr)
            if pause_on_error and headed:
                try:
                    page.pause()
                except KeyboardInterrupt:
                    pass
            raise
        finally:
            context.close()
            browser.close()

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LEAF・くらさぽコネクトから送金明細書 PDF をダウンロード",
    )
    parser.add_argument(
        "--output-dir", required=True,
        help="PDF の保存先ディレクトリ",
    )
    parser.add_argument(
        "--latest", action="store_true",
        help="最新の送金明細書のみ（既定）",
    )
    parser.add_argument(
        "--count", type=int, default=None,
        help="直近 N 件の送金明細書を取得（--latest より優先）",
    )
    parser.add_argument(
        "--months",
        help="対象月（YYYY-MM のカンマ区切り。例: 2026-04,2026-05）",
    )
    parser.add_argument(
        "--bunsyo-filter", default=DEFAULT_BUNSYO_FILTER,
        help=f"報告書検索フィルタ（既定: {DEFAULT_BUNSYO_FILTER}）",
    )
    parser.add_argument(
        "--env-file", default=str(DEFAULT_ENV_PATH),
        help=f"認証情報 .env ファイル（既定: {DEFAULT_ENV_PATH}）",
    )
    parser.add_argument("--headless", action="store_true", help="ヘッドレス実行")
    parser.add_argument("--dry-run", action="store_true", help="一覧のみ（DL なし）")
    parser.add_argument("--no-pause", action="store_true", help="エラー時に pause しない")
    parser.add_argument(
        "--manual-login", action="store_true",
        help="ブラウザで手動ログイン（PW 未設定・変更済み時）",
    )
    args = parser.parse_args()

    _load_env_file(Path(args.env_file))

    months: list[tuple[int, int]] | None = None
    if args.months:
        months = []
        for token in args.months.split(","):
            token = token.strip()
            y, m = token.split("-")
            months.append((int(y), int(m)))

    latest = True
    if args.count is not None:
        latest = False
    elif args.months:
        latest = False
    elif args.latest:
        latest = True

    results = run(
        output_dir=Path(args.output_dir),
        latest=latest if args.count is None and not args.months else latest,
        count=args.count,
        months=months,
        bunsyo_filter=args.bunsyo_filter,
        headed=not args.headless,
        dry_run=args.dry_run,
        pause_on_error=not args.no_pause,
        manual_login=args.manual_login,
    )

    ok = sum(1 for r in results if r.get("status") == "ok")
    fail = sum(1 for r in results if r.get("status") == "failed")
    print(f"\n完了: {ok} 件成功, {fail} 件失敗")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
