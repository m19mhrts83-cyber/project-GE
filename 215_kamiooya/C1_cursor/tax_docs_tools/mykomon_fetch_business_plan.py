#!/usr/bin/env python3
"""
MyKomon から事業計画・総勘定元帳・AI分析などを高速探索・DL。

方針: 「最近追加されたファイル」→ 2025/2026 年度直下＋特殊フォルダ名のみ。
四半期の深い証憑ツリーは走らない。

  cd ~/git-repos/215_kamiooya/C1_cursor/tax_docs_tools
  PYTHONUNBUFFERED=1 ~/selenium_env/venv/bin/python mykomon_fetch_business_plan.py --headless
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

import mykomon_upload as mk
from tax_docs_env import load_tax_credentials

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = SCRIPT_DIR / ".env.tax_docs"
DEFAULT_OUT = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    / "50_税金,確定申告/knees bee 税理士法人/1.資料/2期終了_202608"
)

KEYWORDS = [
    "事業計画",
    "損益分岐",
    "総勘定元帳",
    "元帳",
    "試算表",
    "AI分析",
    "分析レポート",
    "分析",
    "決算書",
    "貸借対照表",
    "損益計算",
    "キャッシュフロー",
    "リビングサポート",
]


def _list_files_in_view(page) -> list[dict]:
    return page.evaluate(
        """() => {
            const inner = document.querySelector('#inner_right') || document.body;
            const out = [];
            const seen = new Set();
            for (const a of inner.querySelectorAll('a')) {
                const name = (a.innerText || '').trim();
                if (!name || name.length > 220) continue;
                if (a.classList.contains('view_folder')) continue;
                if (/ファイル追加|フォルダ追加|印刷済/.test(name)) continue;
                const href = a.getAttribute('href') || '';
                const key = name + '|' + href;
                if (seen.has(key)) continue;
                seen.add(key);
                out.push({ name, href });
            }
            return out;
        }"""
    )


def _list_folders_in_view(page) -> list[str]:
    return page.evaluate(
        """() => {
            const inner = document.querySelector('#inner_right');
            if (!inner) return [];
            return [...inner.querySelectorAll('a.view_folder')]
                .filter(a => !a.closest('.title_area'))
                .map(a => a.innerText.trim())
                .filter(Boolean);
        }"""
    )


def _match_kw(name: str) -> bool:
    n = name.lower()
    return any(k.lower() in n for k in KEYWORDS)


def _safe_name(name: str) -> str:
    return re.sub(r'[\\\\/:*?"<>|]+', "_", name).strip() or "file"


def _interesting_folder(name: str) -> bool:
    if _match_kw(name):
        return True
    if any(x in name for x in ("事業", "計画", "決算", "試算", "元帳", "顧問", "共有", "資料")):
        return True
    # 四半期・証憑分類はスキップ
    if re.match(r"^[①②③④]", name):
        return False
    if re.match(r"^\d{2}_", name):
        return False
    if name.startswith("●"):
        return False
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=str(DEFAULT_ENV_PATH))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--list-only", action="store_true")
    ap.add_argument("--max-downloads", type=int, default=30)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    load_tax_credentials(Path(args.env))
    user = os.environ.get("MYKOMON_USER_ID") or os.environ.get("MYKOMON_USER")
    pw = os.environ.get("MYKOMON_PASSWORD") or os.environ.get("MYKOMON_PASS")
    if not user or not pw:
        print("MYKOMON_USER_ID / MYKOMON_PASSWORD がありません", file=sys.stderr)
        return 1

    catalog: list[dict] = []
    downloaded: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        print("使用サービス: MyKomon / Playwright")
        mk._login(page, user, pw)
        mk._open_shared_folder_tab(page)
        page.wait_for_timeout(800)

        # 1) 最近追加
        try:
            mk._click_tree_path(page, "最近追加されたファイル")
            for f in _list_files_in_view(page):
                catalog.append({**f, "path": "最近追加"})
            print(f"# recent_files={len(_list_files_in_view(page))}")
        except Exception as e:
            print(f"# recent WARN: {e}")

        # 2) 法人 2025 / 2026 直下の興味フォルダのみ
        for year in ("2025年（令和7年）", "2026年（令和8年）"):
            try:
                if not mk._goto_year(page, year):
                    print(f"# skip {year}")
                    continue
            except Exception as e:
                print(f"# year FAIL {year}: {e}")
                continue
            for f in _list_files_in_view(page):
                catalog.append({**f, "path": year})
            folders = _list_folders_in_view(page)
            interesting = [x for x in folders if _interesting_folder(x)]
            print(f"# {year} folders={len(folders)} interesting={interesting}")
            for folder in interesting[:15]:
                try:
                    if not mk._open_listing_folder(page, folder):
                        continue
                except Exception:
                    continue
                for f in _list_files_in_view(page):
                    catalog.append({**f, "path": f"{year}/{folder}"})
                for sub in [s for s in _list_folders_in_view(page) if _interesting_folder(s)][:8]:
                    try:
                        if not mk._open_listing_folder(page, sub):
                            continue
                    except Exception:
                        continue
                    for f in _list_files_in_view(page):
                        catalog.append({**f, "path": f"{year}/{folder}/{sub}"})
                    mk._click_breadcrumb(page, folder)
                    page.wait_for_timeout(300)
                mk._goto_year(page, year)
                page.wait_for_timeout(300)

        hits = []
        seen = set()
        for f in catalog:
            key = (f.get("path"), f.get("name"))
            if key in seen:
                continue
            seen.add(key)
            if _match_kw(str(f.get("name") or "")):
                hits.append(f)

        print(f"# catalog_unique={len(seen)} keyword_hits={len(hits)}")
        for h in hits:
            print(f"  ★ [{h.get('path')}] {h.get('name')}")
        if not hits:
            print("# no keyword hits — listing all catalog names:")
            for f in list(seen)[:80]:
                print(f"  · [{f[0]}] {f[1]}")

        manifest = {
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
            "keyword_hits": hits,
            "catalog_count": len(seen),
            "downloaded": [],
        }

        if args.list_only:
            (out_dir / "00_mykomon_catalog.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"📎 catalog → {out_dir / '00_mykomon_catalog.json'}")
            browser.close()
            return 0

        targets = hits[:] if hits else []
        if not targets:
            for path, name in seen:
                if re.search(r"\.(pdf|xlsx|xls|csv|docx)$", name or "", re.I):
                    targets.append({"path": path, "name": name})
            targets = targets[:10]

        # パス単位でナビ→DL
        by_path: dict[str, list[dict]] = {}
        for t in targets[: args.max_downloads]:
            by_path.setdefault(str(t.get("path") or ""), []).append(t)

        for path, files in by_path.items():
            parts = [p for p in path.split("/") if p and p != "最近追加"]
            try:
                mk._open_shared_folder_tab(page)
                if path == "最近追加":
                    mk._click_tree_path(page, "最近追加されたファイル")
                elif parts:
                    mk._click_tree_path(page, "カラフルファイル（法人）", parts[0])
                    for seg in parts[1:]:
                        if not mk._open_listing_folder(page, seg):
                            raise RuntimeError(f"open failed: {seg}")
            except Exception as e:
                print(f"# nav FAIL {path}: {e}")
                continue

            for f in files:
                name = str(f.get("name") or "")
                try:
                    with page.expect_download(timeout=25000) as dl_info:
                        clicked = page.evaluate(
                            """(name) => {
                                const inner = document.querySelector('#inner_right') || document.body;
                                const a = [...inner.querySelectorAll('a')]
                                    .find(x => (x.innerText || '').trim() === name);
                                if (!a) return false;
                                a.click();
                                return true;
                            }""",
                            name,
                        )
                        if not clicked:
                            raise RuntimeError("link not found")
                    download = dl_info.value
                    dest = out_dir / _safe_name(download.suggested_filename or name)
                    download.save_as(str(dest))
                    downloaded.append(str(dest))
                    print(f"  ↓ {dest.name}")
                except Exception as e:
                    print(f"  · DL skip {name}: {type(e).__name__}: {e}")

        manifest["downloaded"] = downloaded
        (out_dir / "00_mykomon_catalog.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        hit_lines = (
            [f"- `{h.get('path')}` / {h.get('name')}" for h in hits]
            if hits
            else ["- （なし）"]
        )
        dl_lines = (
            [f"- `{Path(p).name}`" for p in downloaded]
            if downloaded
            else ["- （なし）"]
        )
        (out_dir / "00_目録.md").write_text(
            "\n".join(
                [
                    "# MyKomon 取得目録（2期終了_202608）",
                    "",
                    f"- 取得日時: {manifest['fetched_at']}",
                    f"- カタログ件数: {manifest['catalog_count']}",
                    f"- キーワードヒット: {len(hits)}",
                    f"- DL成功: {len(downloaded)}",
                    "",
                    "## ヒット",
                    *hit_lines,
                    "",
                    "## 保存ファイル",
                    *dl_lines,
                    "",
                ]
            ),
            encoding="utf-8",
        )
        print(f"📎 out={out_dir} downloaded={len(downloaded)}")
        browser.close()
    return 0 if downloaded or hits else 2


if __name__ == "__main__":
    raise SystemExit(main())
