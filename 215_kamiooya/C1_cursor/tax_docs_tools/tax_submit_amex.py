#!/usr/bin/env python3
"""
AMEX 利用履歴 Excel 取得 → 結合 → 費目仕分け → MyKomon アップロードを一括実行する。

使い方（フェーズA: 取得＋費目付与＋空欄報告で停止）:
  python tax_submit_amex.py \\
      --periods missing-2025-06-2026-05 \\
      --materials-root ".../2.経費,売上資料"

使い方（フェーズB: 空欄確認後に export-tagged → MyKomon 提出）:
  python tax_submit_amex.py \\
      --periods missing-2025-06-2026-05 \\
      --materials-root ".../2.経費,売上資料" \\
      --finalize-upload

認証情報: .env.tax_docs に AMEX / MyKomon を設定する。

MyKomon 提出先: 07_クレジットカード明細 / 取引が全て経費のもの
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = SCRIPT_DIR / ".env.tax_docs"
DEFAULT_RULES = SCRIPT_DIR / "amex_himoku_rules.json"

MYKOMON_CATEGORY = "07_クレジットカード明細"
MYKOMON_SUBFOLDER = "取引が全て経費のもの"

# 欠落分（2025-06〜2026-05）の4取得期間
MISSING_PERIODS_PRESET = "missing-2025-06-2026-05"


@dataclass(frozen=True)
class AmexPeriod:
    key: str
    start: date
    end: date
    output_name: str
    materials_year: int
    materials_period: str
    mykomon_year_label: str
    mykomon_quarter: str


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


def _year_label(calendar_year: int) -> str:
    reiwa = calendar_year - 2018
    return f"{calendar_year}年（令和{reiwa}年）"


def _quarter_label(month: int) -> str:
    labels = ["①1-3月", "②4-6月", "③7-9月", "④10-12月"]
    return labels[(month - 1) // 3]


def _materials_location(start: date, end: date) -> tuple[int, str]:
    """OneDrive 期間フォルダ（暦年ベース）。"""
    from amex_statement_postprocess import materials_period_folder

    return materials_period_folder(start.year, start.month, end.year, end.month)


def _mykomon_location(end: date) -> tuple[str, str]:
    """MyKomon 年度・四半期（暦年ベース）。"""
    return _year_label(end.year), _quarter_label(end.month)


def _output_label(start: date, end: date) -> str:
    if start.year == end.year and start.month == end.month:
        return f"AMEX_{start.year}年{start.month}月.xlsx"
    if start.year == end.year:
        return f"AMEX_{start.year}年{start.month}月〜{end.month}月.xlsx"
    return f"AMEX_{start.year}年{start.month}月〜{end.year}年{end.month}月.xlsx"


def default_periods() -> list[AmexPeriod]:
    """欠落分4期間の定義（OneDrive 実フォルダ名に合わせる）。"""
    specs: list[tuple[date, date, int, str]] = [
        (date(2025, 6, 1), date(2025, 6, 30), 2025, "6月"),
        (date(2025, 10, 1), date(2025, 12, 31), 2025, "10月-2026.4月"),
        (date(2026, 1, 1), date(2026, 3, 31), 2025, "10月-2026.4月"),
        (date(2026, 5, 1), date(2026, 5, 31), 2026, "5月"),
    ]
    out: list[AmexPeriod] = []
    for start, end, my, mp in specs:
        yl, ql = _mykomon_location(end)
        out.append(
            AmexPeriod(
                key=f"{start.isoformat()}_{end.isoformat()}",
                start=start,
                end=end,
                output_name=_output_label(start, end),
                materials_year=my,
                materials_period=mp,
                mykomon_year_label=yl,
                mykomon_quarter=ql,
            )
        )
    return out


def _amex_raw_dir(materials_root: Path, period: AmexPeriod) -> Path:
    return (
        materials_root
        / str(period.materials_year)
        / period.materials_period
        / "00_元ファイル_サイト取得"
        / "AMEX"
    )


def _period_output_path(materials_root: Path, period: AmexPeriod) -> Path:
    return (
        materials_root
        / str(period.materials_year)
        / period.materials_period
        / period.output_name
    )


def _run_py(args: list[str]) -> int:
    py = sys.executable
    r = subprocess.run([py] + args, cwd=str(SCRIPT_DIR))
    return r.returncode


def _summarize_unmapped(workbook: Path, rules: Path) -> list[tuple[str, str]]:
    """費目が空の行を (日付, 内容) で返す。"""
    from amex_activity_classify import (
        classify_description,
        find_header_row,
        load_rules,
        parse_data_rows,
        normalize_text,
    )
    import openpyxl

    rules_data = load_rules(rules)
    excludes = list(rules_data.get("exclude_row_substrings", []))
    himoku_rules = list(rules_data.get("himoku_rules", []))

    wb = openpyxl.load_workbook(workbook, data_only=True)
    ws = wb["ご利用履歴"]
    header_row = find_header_row(ws)
    parsed = parse_data_rows(ws, header_row)
    blanks: list[tuple[str, str]] = []
    for _ridx, rowd in parsed:
        desc = str(rowd.get("ご利用内容", "") or "")
        day = str(rowd.get("ご利用日", "") or "")
        cat = classify_description(desc, himoku_rules, excludes)
        if cat == "":
            blanks.append((day, normalize_text(desc)[:120]))
    wb.close()
    return blanks


def process_period(
    period: AmexPeriod,
    *,
    materials_root: Path,
    rules: Path,
    headed: bool,
    dry_run: bool,
    skip_download: bool,
    finalize_upload: bool,
    skip_mykomon: bool,
    pause_on_error: bool,
    page=None,
) -> dict:
    from amex_statement import download_period, run as amex_run
    from amex_statement_postprocess import merge_activity_workbooks
    from amex_activity_classify import run_finalize, run_export_tagged_only
    from mykomon_upload import run as mykomon_run

    raw_dir = _amex_raw_dir(materials_root, period)
    merged_raw = raw_dir / f"_merged_{period.key}.xlsx"
    classified = _period_output_path(materials_root, period)
    classified.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "period": period.key,
        "output": str(classified),
        "download": "skipped" if skip_download else "pending",
        "merge": "pending",
        "classify": "pending",
        "unmapped": 0,
        "mykomon": "skipped",
    }

    print(f"\n{'='*60}")
    print(f"  期間: {period.start} 〜 {period.end}")
    print(f"  出力: {classified.name}")
    print(f"  MyKomon: {period.mykomon_year_label} / {period.mykomon_quarter}")
    print(f"{'='*60}")

    # --- ダウンロード ---
    dl_paths: list[Path] = []
    if not skip_download:
        if dry_run:
            print("[dry-run] AMEX ダウンロードをスキップ")
            result["download"] = "dry-run"
        else:
            if page is not None:
                print(f"[DL] 期間 {period.start} 〜 {period.end}")
                dl_results = download_period(
                    page,
                    start_date=period.start,
                    end_date=period.end,
                    output_dir=raw_dir,
                )
            else:
                dl_results = amex_run(
                    start_date=period.start,
                    end_date=period.end,
                    output_dir=raw_dir,
                    headed=headed,
                    dry_run=False,
                    pause_on_error=pause_on_error,
                )
            dl_paths = [r["path"] for r in dl_results if r.get("path")]
            ok = sum(1 for r in dl_results if r["status"] == "ok")
            if not dl_results:
                result["download"] = "FAILED (login or no cards)"
            elif not dl_paths:
                result["download"] = f"FAILED ({ok}/{len(dl_results)} ok)"
            else:
                result["download"] = f"OK ({ok}/{len(dl_results)})"
            if not dl_paths:
                result["merge"] = "failed: no downloads"
                return result
    else:
        dl_paths = sorted(raw_dir.glob("activity_*.xlsx"))
        if not dl_paths:
            dl_paths = sorted(raw_dir.glob("*.xlsx"))
        result["download"] = f"existing ({len(dl_paths)})"

    if dry_run and not dl_paths:
        result["merge"] = "dry-run"
        return result

    # --- 結合 ---
    if not dl_paths:
        result["merge"] = "failed: no files"
        return result
    try:
        merge_activity_workbooks(dl_paths, merged_raw)
        result["merge"] = "OK"
    except Exception as e:
        result["merge"] = f"failed: {e}"
        return result

    # --- 費目付与 (finalize --allow-unmapped) ---
    rc = run_finalize(
        merged_raw,
        rules,
        classified,
        allow_unmapped=True,
        drop_unmapped=False,
    )
    if rc != 0:
        result["classify"] = f"failed (code {rc})"
        return result
    result["classify"] = "OK"

    blanks = _summarize_unmapped(classified, rules)
    result["unmapped"] = len(blanks)
    if blanks:
        print(f"\n--- 未マッチ（費目空欄）{len(blanks)} 件 ---")
        for day, desc in blanks[:30]:
            print(f"  {day}  {desc}")
        if len(blanks) > 30:
            print(f"  … 他 {len(blanks) - 30} 件")
        print(
            "\n費目が空欄の行について、追加でルールに入れる取引がないかご確認ください。"
            " 完了後 --finalize-upload で提出できます。"
        )

    if not finalize_upload:
        result["mykomon"] = "pending (phase A)"
        return result

    if blanks:
        print(
            "\n⚠ 未マッチ行が残っています。"
            " ルール追記後に --finalize-upload を再実行してください。",
            file=sys.stderr,
        )
        result["mykomon"] = "blocked: unmapped rows"
        return result

    # --- フェーズB: export-tagged → MyKomon ---
    rc = run_export_tagged_only(classified, classified)
    if rc != 0:
        result["mykomon"] = f"export-tagged failed ({rc})"
        return result

    if skip_mykomon:
        result["mykomon"] = "skipped"
        return result

    ok = mykomon_run(
        file_path=classified,
        year=period.mykomon_year_label,
        quarter=period.mykomon_quarter,
        category=MYKOMON_CATEGORY,
        subfolder=MYKOMON_SUBFOLDER,
        headed=headed,
        dry_run=dry_run,
        pause_on_error=pause_on_error,
    )
    result["mykomon"] = "OK" if ok else "FAILED"
    return result


def run_pipeline(
    *,
    periods: list[AmexPeriod],
    materials_root: Path,
    rules: Path,
    headed: bool,
    dry_run: bool,
    skip_download: bool,
    finalize_upload: bool,
    skip_mykomon: bool,
    pause_on_error: bool,
) -> None:
    if not skip_download and not dry_run:
        if not all([os.environ.get("AMEX_LOGIN_ID"), os.environ.get("AMEX_PASSWORD")]):
            print(
                "エラー: AMEX_LOGIN_ID / AMEX_PASSWORD が未設定です。\n"
                f"  → {DEFAULT_ENV_PATH} を編集してください",
                file=sys.stderr,
            )
            sys.exit(1)

    results: list[dict] = []
    shared_page = None
    browser_ctx = None
    browser = None
    pw = None

    if not skip_download and not dry_run:
        from playwright.sync_api import sync_playwright
        from amex_statement import _login, _login_verified, _storage_state_path, save_storage_state

        login_id = os.environ.get("AMEX_LOGIN_ID", "")
        password = os.environ.get("AMEX_PASSWORD", "")
        state_path = _storage_state_path()
        login_headed = headed or not state_path.exists()
        if not state_path.exists() and not headed:
            print(
                "  初回ログイン: 二段階認証のためブラウザを表示します（--headless は使用しません）",
                file=sys.stderr,
            )

        def _launch_browser(*, headed_launch: bool):
            launch_kw: dict = {"headless": not headed_launch}
            try:
                launch_kw["channel"] = "chrome"
                launch_kw["args"] = ["--disable-blink-features=AutomationControlled"]
            except Exception:
                pass
            return pw.chromium.launch(**launch_kw)

        def _new_context(browser_instance):
            ctx_kw: dict = {"locale": "ja-JP", "accept_downloads": True}
            if state_path.exists():
                ctx_kw["storage_state"] = str(state_path)
            return browser_instance.new_context(**ctx_kw)

        pw = sync_playwright().start()
        browser = _launch_browser(headed_launch=login_headed)
        browser_ctx = _new_context(browser)
        shared_page = browser_ctx.new_page()
        auth_timeout = int(os.environ.get("AMEX_AUTH_TIMEOUT_SEC", "600"))
        try:
            print("[AMEX] ログイン（全期間共通）...")
            session_ok = state_path.exists() and _login_verified(shared_page)
            if session_ok:
                print(f"  保存済みセッションを使用: {state_path}")
            else:
                if headed and not login_headed:
                    print(
                        "  セッション無効: 二段階認証のためブラウザを表示して再ログインします",
                        file=sys.stderr,
                    )
                    browser_ctx.close()
                    browser.close()
                    login_headed = True
                    browser = _launch_browser(headed_launch=True)
                    browser_ctx = _new_context(browser)
                    shared_page = browser_ctx.new_page()
                _login(
                    shared_page,
                    login_id,
                    password,
                    headed=login_headed,
                    manual_login=True,
                    manual_credentials=True,
                    auth_timeout_sec=auth_timeout,
                )
                save_storage_state(browser_ctx)
        except Exception as e:
            print(f"エラー: ログイン失敗 — {e}", file=sys.stderr)
            for period in periods:
                results.append({
                    "period": period.key,
                    "output": str(_period_output_path(materials_root, period)),
                    "download": "FAILED (login)",
                    "merge": "skipped",
                    "classify": "skipped",
                    "unmapped": 0,
                    "mykomon": "skipped",
                })
            if browser_ctx is not None:
                browser_ctx.close()
            if browser is not None:
                browser.close()
            if pw is not None:
                pw.stop()
            _print_summary(results)
            return

    try:
        for period in periods:
            results.append(
                process_period(
                    period,
                    materials_root=materials_root,
                    rules=rules,
                    headed=headed,
                    dry_run=dry_run,
                    skip_download=skip_download,
                    finalize_upload=finalize_upload,
                    skip_mykomon=skip_mykomon,
                    pause_on_error=pause_on_error,
                    page=shared_page,
                )
            )
    finally:
        if browser_ctx is not None:
            browser_ctx.close()
        if browser is not None:
            browser.close()
        if pw is not None:
            pw.stop()

    _print_summary(results)


def _print_summary(results: list[dict]) -> None:
    print(f"\n{'='*60}")
    print("  結果サマリー")
    print(f"{'='*60}")
    for r in results:
        print(
            f"  {r['period']}: DL={r['download']} merge={r['merge']} "
            f"classify={r['classify']} unmapped={r['unmapped']} MyKomon={r['mykomon']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="AMEX → 費目仕分け → MyKomon 一括提出")
    parser.add_argument(
        "--periods",
        default=MISSING_PERIODS_PRESET,
        help=f"期間プリセット（既定: {MISSING_PERIODS_PRESET}）",
    )
    parser.add_argument("--materials-root", required=True)
    parser.add_argument("--rules", default=str(DEFAULT_RULES))
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH))
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="00_元ファイル_サイト取得/AMEX/ の既存ファイルだけで結合・仕分け",
    )
    parser.add_argument(
        "--finalize-upload",
        action="store_true",
        help="フェーズB: export-tagged → MyKomon 提出（空欄行が無いとき）",
    )
    parser.add_argument("--skip-mykomon", action="store_true")
    parser.add_argument("--no-pause", action="store_true")
    parser.add_argument(
        "--login-timeout",
        type=int,
        default=600,
        help="二段階認証・手動ログインの待機秒数（既定 600）",
    )
    args = parser.parse_args()

    os.environ["AMEX_AUTH_TIMEOUT_SEC"] = str(args.login_timeout)

    _load_env_file(Path(args.env_file))

    if args.periods != MISSING_PERIODS_PRESET:
        print(f"エラー: 未対応の --periods: {args.periods}", file=sys.stderr)
        sys.exit(1)

    run_pipeline(
        periods=default_periods(),
        materials_root=Path(args.materials_root),
        rules=Path(args.rules),
        headed=not args.headless,
        dry_run=args.dry_run,
        skip_download=args.skip_download,
        finalize_upload=args.finalize_upload,
        skip_mykomon=args.skip_mykomon,
        pause_on_error=not args.no_pause,
    )


if __name__ == "__main__":
    main()
