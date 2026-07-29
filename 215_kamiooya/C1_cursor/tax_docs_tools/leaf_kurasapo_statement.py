#!/usr/bin/env python3
"""
LEAF（くらさぽコネクト）オーナーサイトから送金明細書 PDF をダウンロードする。

取得元:
  https://owner.kurasapo-connect.com/login
  → ログイン後「報告書」→ 送金明細書（支払明細書）を PDF 保存

認証情報（優先順）:
  1. ~/git-repos/.env.jarvis_private の KURASAPO_OWNER_LOGIN_ID / KURASAPO_OWNER_PASSWORD
  2. 互換: tax_docs_tools/.env.tax_docs（同キー）
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

from tax_docs_env import JARVIS_PRIVATE_ENV, load_tax_credentials

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = SCRIPT_DIR / ".env.tax_docs"

KURASAPO_LOGIN_URL = os.environ.get(
    "KURASAPO_OWNER_LOGIN_URL", "https://owner.kurasapo-connect.com/login"
)
KURASAPO_BASE_URL = os.environ.get(
    "KURASAPO_OWNER_BASE_URL", "https://owner.kurasapo-connect.com"
)
DEFAULT_BUNSYO_FILTER = "送金明細"



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
                " .env.jarvis_private（または .env.tax_docs）の"
                " KURASAPO_OWNER_LOGIN_ID / KURASAPO_OWNER_PASSWORD を確認してください。"
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
    for key in (
        "torihiki_ymd",
        "soushin_ymd",
        "send_ymd",
        "public_at",
        "created_at",
        "updated_at",
    ):
        raw = item.get(key)
        if not raw:
            continue
        for fmt in (
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                return datetime.strptime(str(raw)[:19], fmt)
            except ValueError:
                continue
    text = _item_text(item)
    # 例: Grandole… 2026/07月分 送金明細書
    m = re.search(r"(\d{4})[/-](\d{1,2})\s*月分", text)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), 1)
    m = re.search(r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})", text)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return datetime.min


def _is_soukin_meisai(item: dict[str, Any], bunsyo_filter: str) -> bool:
    text = _item_text(item)
    if bunsyo_filter and bunsyo_filter in text:
        return True
    keywords = ("送金明細", "支払明細", "送金のご案内", "物件別送金")
    return any(k in text for k in keywords)


def _collect_pdf_targets(page, item: dict[str, Any]) -> list[dict[str, Any]]:
    """
    PDF 取得候補を返す。優先順:
      1. files[].file_url（S3 直）
      2. files[].id → /file/pdf/{id}
      3. information/show 内の owapp_reportdata/{uuid}（閲覧用 PDF・6/7月で有効）
      4. 報告書 id → /api/file/pdf/{id}（空応答のことがある）
    """
    targets: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(*, key: str, **kwargs: Any) -> None:
        if key in seen:
            return
        seen.add(key)
        targets.append(kwargs)

    files = item.get("files") or []
    if isinstance(files, list):
        for f in files:
            if not isinstance(f, dict):
                continue
            if f.get("is_image") == 1:
                continue
            name = str(f.get("name") or f.get("file_name") or "")
            file_url = f.get("file_url") or f.get("url") or f.get("download_url")
            if file_url:
                add(key=f"url:{file_url}", url=str(file_url), name=name, id=None)
            file_id = f.get("id")
            if file_id is not None:
                add(
                    key=f"file:{file_id}",
                    url=f"{KURASAPO_BASE_URL}/file/pdf/{file_id}",
                    name=name,
                    id=file_id,
                )

    report_id = item.get("id")
    if report_id is not None:
        try:
            html = page.request.get(
                f"{KURASAPO_BASE_URL}/information/show/{report_id}"
            ).text()
        except Exception:
            html = ""
        for uuid in re.findall(
            r"owapp_reportdata/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
            html,
        ):
            url = f"{KURASAPO_BASE_URL}/owapp_reportdata/{uuid}"
            add(key=f"owapp:{uuid}", url=url, name="", id=None)
        # title / 月分 を item に補完（年月判定用）
        if not item.get("title"):
            m = re.search(
                r"(Grandole[^<\n]{0,80}\d{4}/\d{1,2}\s*月分[^<\n]{0,40})",
                html,
            )
            if m:
                item["title"] = m.group(1)
        add(
            key=f"api:{report_id}",
            url=f"{KURASAPO_BASE_URL}/api/file/pdf/{report_id}",
            name=str(item.get("title") or item.get("bunsyo") or ""),
            id=report_id,
        )

    file_id = item.get("file_id")
    if file_id is not None:
        add(
            key=f"file:{file_id}",
            url=f"{KURASAPO_BASE_URL}/file/pdf/{file_id}",
            name=str(item.get("bunsyo") or item.get("torihiki_name") or ""),
            id=file_id,
        )
    return targets


def _item_year_month(item: dict[str, Any], file_hint: str = "") -> tuple[int, int] | None:
    """報告書の対象年月。(year, month) または不明なら None。"""
    for text in (file_hint, str(item.get("title") or ""), _item_text(item)):
        if not text:
            continue
        m = re.search(r"(\d{4})[/-](\d{1,2})\s*月分", text)
        if m:
            return int(m.group(1)), int(m.group(2))
        m = re.search(r"(\d{4})[年.](\d{1,2})", text)
        if m:
            return int(m.group(1)), int(m.group(2))
    dt = _parse_item_date(item)
    if dt != datetime.min:
        return dt.year, dt.month
    return None


def _ym_key(ym: tuple[int, int] | None) -> str:
    if not ym:
        return "unknown"
    return f"{ym[0]:04d}-{ym[1]:02d}"


def _output_name(item: dict[str, Any], file_hint: str = "") -> str:
    ym = _item_year_month(item, file_hint)
    if ym:
        label = f"{ym[0]}年{ym[1]}月"
    else:
        now = datetime.now()
        label = f"{now.year}年{now.month}月"
    return f"LEAF_送金明細書_{label}.pdf"


def _download_pdf_from_url(page, url: str, dest: Path) -> None:
    resp = page.request.get(url)
    if not resp.ok:
        raise RuntimeError(f"PDF ダウンロード失敗: {url} (HTTP {resp.status})")
    body = resp.body()
    if not body or not body.startswith(b"%PDF"):
        raise RuntimeError(f"PDF ではない応答: {url} (len={len(body or b'')})")
    dest.write_bytes(body)
    print(f"  ✅ ダウンロード完了: {dest.name} ({len(body) // 1024}KB) ← {url.split('/')[-1]}")


def _download_pdf(page, file_id: Any, dest: Path) -> None:
    """互換: file_id 指定時は /file/pdf と /api/file/pdf を順に試す。"""
    urls = [
        f"{KURASAPO_BASE_URL}/file/pdf/{file_id}",
        f"{KURASAPO_BASE_URL}/api/file/pdf/{file_id}",
    ]
    errors: list[str] = []
    for url in urls:
        try:
            _download_pdf_from_url(page, url, dest)
            return
        except Exception as e:
            errors.append(str(e))
    raise RuntimeError(" / ".join(errors))


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
            ym = _item_year_month(it)
            if ym and ym in wanted:
                month_filtered.append(it)
        # 月指定時はフォールバックしない（別月を誤取得しない）
        filtered = month_filtered

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
            f"  → 正本: {JARVIS_PRIVATE_ENV}\n"
            f"  → 互換: {DEFAULT_ENV_PATH}\n"
            "  または --manual-login を指定してください。",
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
                targets = _collect_pdf_targets(page, item)
                ym = _item_year_month(item)
                ym_s = _ym_key(ym)
                if not targets:
                    print(f"  ⚠ PDF 添付なし ({ym_s}): {_item_text(item)[:80]}")
                    results.append(
                        {"status": "no_pdf", "year_month": ym_s, "item": item}
                    )
                    continue
                # 同一報告書は1ファイル保存できれば十分（候補 URL を順に試す）
                hint = str(targets[0].get("name") or item.get("title") or "")
                ym_t = _item_year_month(item, hint) or ym
                ym_ts = _ym_key(ym_t)
                dest = output_dir / _output_name(item, hint)
                if dest.exists():
                    print(f"  ⚠ 既に存在 → スキップ: {dest.name}")
                    results.append(
                        {
                            "status": "skipped",
                            "year_month": ym_ts,
                            "path": str(dest),
                        }
                    )
                    continue
                if dry_run:
                    print(
                        f"  [dry-run] {dest.name} candidates={len(targets)} "
                        f"first={targets[0].get('url')}"
                    )
                    results.append(
                        {
                            "status": "dry-run",
                            "year_month": ym_ts,
                            "path": str(dest),
                        }
                    )
                    continue
                last_err: Exception | None = None
                saved = False
                for tgt in targets:
                    url = str(tgt.get("url") or "")
                    if not url and tgt.get("id") is not None:
                        url = f"{KURASAPO_BASE_URL}/file/pdf/{tgt['id']}"
                    if not url:
                        continue
                    try:
                        _download_pdf_from_url(page, url, dest)
                        results.append(
                            {"status": "ok", "year_month": ym_ts, "path": str(dest)}
                        )
                        saved = True
                        break
                    except Exception as e:
                        last_err = e
                        continue
                if not saved:
                    err = str(last_err) if last_err else "no_candidate"
                    print(f"  ❌ {dest.name} ({ym_ts}): {err}", file=sys.stderr)
                    results.append(
                        {
                            "status": "failed",
                            "year_month": ym_ts,
                            "path": str(dest),
                            "error": err,
                        }
                    )

            if months:
                covered = {
                    r.get("year_month")
                    for r in results
                    if r.get("year_month")
                    and r.get("status")
                    in ("ok", "skipped", "dry-run", "failed", "no_pdf")
                }
                for y, m in months:
                    key = f"{y:04d}-{m:02d}"
                    if key not in covered:
                        print(f"  ❌ 対象月が一覧にありません: {key}", file=sys.stderr)
                        results.append(
                            {
                                "status": "failed",
                                "year_month": key,
                                "error": "not_in_list",
                            }
                        )

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
        help=(
            "追加で読む .env（既定: .env.tax_docs）。"
            "正本の jarvis_private は常に先に読み込む。"
        ),
    )
    parser.add_argument("--headless", action="store_true", help="ヘッドレス実行")
    parser.add_argument("--dry-run", action="store_true", help="一覧のみ（DL なし）")
    parser.add_argument("--no-pause", action="store_true", help="エラー時に pause しない")
    parser.add_argument(
        "--manual-login", action="store_true",
        help="ブラウザで手動ログイン（PW 未設定・変更済み時）",
    )
    args = parser.parse_args()

    load_tax_credentials(args.env_file)

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
    failed_months = sorted(
        {
            str(r.get("year_month"))
            for r in results
            if r.get("status") == "failed" and r.get("year_month")
        }
    )
    print(f"\n完了: {ok} 件成功, {fail} 件失敗")
    if failed_months:
        details = []
        for ym in failed_months:
            errs = [
                str(r.get("error") or "")
                for r in results
                if r.get("status") == "failed" and r.get("year_month") == ym
            ]
            err = errs[0] if errs else ""
            details.append(f"{ym}({err})" if err else ym)
        print(f"# leaf_kurasapo_failed_months: {', '.join(details)}")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
