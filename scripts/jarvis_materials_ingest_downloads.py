#!/usr/bin/env python3
"""
Downloads → docs/jarvis-self/assets へ資料を取り込み、index.html とカタログを更新する。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_materials_ingest_downloads.py
  python scripts/jarvis_materials_ingest_downloads.py --copy   # 移動せずコピー
  python scripts/jarvis_materials_ingest_downloads.py --dry-run
  python scripts/jarvis_materials_ingest_downloads.py --sync-only  # カタログ→JSON/HTML のみ

運用: NotebookLM 確認 → Downloads 保存 → 本スクリプト → git push（Pages 反映）
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DOWNLOADS = Path.home() / "Downloads"
SELF_DIR = REPO / "docs" / "jarvis-self"
ASSETS = SELF_DIR / "assets"
INDEX_HTML = SELF_DIR / "index.html"
CATALOG_YAML = REPO / "config" / "materials_catalog.yaml"
CATALOG_JSON = REPO / "apps" / "jarvis-dashboard" / "data" / "materials_catalog.json"
PAGES_ASSET_BASE = (
    "https://m19mhrts83-cyber.github.io/project-GE/docs/jarvis-self/assets"
)

# Downloads 直下で取り込む拡張子（未知ファイルも候補に）
INGEST_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".html", ".htm"}

# ファイル名ヒント → 表示タイトル（部分一致）
TITLE_HINTS: list[tuple[str, str]] = [
    ("Jarvis_Dashboard_Handover", "Jarvis Dashboard 引き継ぎ"),
    ("Jarvisダッシュボードの全体構成", "Jarvis ダッシュボードの全体構成"),
    ("周辺MAP自動化", "周辺MAP 自動化ガイド"),
    ("会員名簿", "会員名簿データ活用の提案"),
    ("不動産業務自動化", "不動産業務自動化 説明資料"),
]


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        # 最小フォールバック: JSON 互換ではないので必須
        raise SystemExit("PyYAML が必要です（selenium_env の venv を使ってください）")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def dump_yaml(path: Path, data: dict[str, Any]) -> None:
    import yaml  # type: ignore

    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def slug_id(name: str) -> str:
    stem = Path(name).stem
    s = re.sub(r"[^\w\-]+", "-", stem, flags=re.UNICODE).strip("-").lower()
    return (s or "item")[:60]


def title_for(filename: str) -> str:
    for hint, title in TITLE_HINTS:
        if hint in filename:
            return title
    return Path(filename).stem


def known_filenames(catalog: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for it in catalog.get("items") or []:
        fn = it.get("filename")
        if fn:
            out.add(str(fn))
    return out


def ingest_from_downloads(
    catalog: dict[str, Any],
    *,
    downloads: Path,
    copy: bool,
    dry_run: bool,
) -> list[str]:
    ASSETS.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []
    known = known_filenames(catalog)
    candidates = set(known)
    if downloads.is_dir():
        for p in downloads.iterdir():
            if p.is_file() and p.suffix.lower() in INGEST_SUFFIXES:
                if p.name.startswith("."):
                    continue
                if p.name in ("Gemini.html",):
                    continue
                candidates.add(p.name)

    items_by_fn = {
        str(it.get("filename")): it
        for it in (catalog.get("items") or [])
        if it.get("filename")
    }

    for name in sorted(candidates):
        src = downloads / name
        if not src.is_file():
            continue
        dest = ASSETS / name
        action = "copy" if copy else "move"
        print(f"# {action}: {src} → {dest}")
        if not dry_run:
            if copy:
                shutil.copy2(src, dest)
            else:
                shutil.move(str(src), str(dest))
        moved.append(name)

        url = f"{PAGES_ASSET_BASE}/{name}"
        if name in items_by_fn:
            items_by_fn[name]["url"] = url
            continue
        new_item = {
            "id": slug_id(name),
            "lane": "self",
            "title": title_for(name),
            "filename": name,
            "url": url,
            "note": f"Downloads から取込（{date.today().isoformat()}）",
        }
        catalog.setdefault("items", []).append(new_item)
        items_by_fn[name] = new_item
        print(f"# catalog+: {new_item['id']}")

    return moved


def write_index_html(catalog: dict[str, Any]) -> None:
    self_items = [
        it
        for it in (catalog.get("items") or [])
        if it.get("lane") == "self" and it.get("filename")
    ]
    # assets にある順で安定化
    self_items.sort(key=lambda x: str(x.get("title") or ""))

    lis = []
    for it in self_items:
        fn = it["filename"]
        title = it.get("title") or fn
        note = it.get("note") or ""
        href = f"assets/{fn}"
        lis.append(
            f"""    <li>
      <a href="{href}" target="_blank" rel="noopener noreferrer" class="external">
        <strong>{title}</strong>
        <span>{note}</span>
      </a>
    </li>"""
        )
    body_list = "\n".join(lis) if lis else "    <li><p class=\"sub\">資料がまだありません。</p></li>"

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>自分の理解用（Jarvis）</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Hiragino Sans", "Hiragino Kaku Gothic ProN", sans-serif; background: #1a1a2e; color: #eee; min-height: 100vh; padding: 2rem 3rem; }}
    h1 {{ font-size: 1.75rem; margin: 0 0 0.5rem; border-bottom: 2px solid #4a9; padding-bottom: 0.5rem; }}
    .sub {{ color: #8b949e; margin-bottom: 2rem; font-size: 0.95rem; }}
    ul {{ list-style: none; padding: 0; margin: 0; }}
    li {{ margin: 0.75rem 0; }}
    a {{ display: block; background: #16213e; border: 1px solid #4a9; color: #8cf; padding: 1rem 1.25rem; border-radius: 8px; text-decoration: none; transition: background 0.2s; }}
    a:hover {{ background: #0f3460; color: #fff; }}
    a strong {{ display: block; margin-bottom: 0.25rem; font-size: 1.05rem; }}
    a span {{ font-size: 0.9rem; opacity: 0.9; }}
    .note {{ background: #0f3460; padding: 0.75rem 1rem; border-radius: 8px; font-size: 0.9rem; margin-top: 2rem; color: #8b949e; }}
    .back {{ margin-bottom: 1.5rem; font-size: 0.95rem; }}
    .back a {{ display: inline-block; background: transparent; border: 1px solid #6a9; padding: 0.4rem 0.8rem; }}
    .external::after {{ content: " ↗"; font-size: 0.85em; opacity: 0.8; }}
  </style>
</head>
<body>
  <p class="back"><a href="../index.html">← DX互助会・資料トップへ</a>
    · <a href="https://jarvis-dashboard-amber.vercel.app/materials">ダッシュボード資料</a>
  </p>
  <h1>自分の理解用（Jarvis）</h1>
  <p class="sub">NotebookLM 等で確認したあとに Downloads へ置き、取込スクリプトでここへ集約した資料です。対外配布ではなく自分用の正本リンクです。</p>
  <ul>
{body_list}
  </ul>
  <p class="note">
    追加手順: NotebookLM で確認 → Downloads に保存 →<br>
    <code>python scripts/jarvis_materials_ingest_downloads.py</code> → git push（GitHub Pages 反映）
  </p>
</body>
</html>
"""
    SELF_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_HTML.write_text(html, encoding="utf-8")
    print(f"# wrote {INDEX_HTML}")


def sync_json(catalog: dict[str, Any]) -> None:
    CATALOG_JSON.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "version": catalog.get("version", 1),
        "updated": catalog.get("updated") or date.today().isoformat(),
        "pages_base": catalog.get("pages_base"),
        "lanes": catalog.get("lanes") or [],
        "items": catalog.get("items") or [],
    }
    CATALOG_JSON.write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"# wrote {CATALOG_JSON}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="資料 Downloads 取込 → jarvis-self / catalog")
    ap.add_argument("--copy", action="store_true", help="移動せずコピー")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sync-only", action="store_true", help="取込せず HTML/JSON 再生成のみ")
    ap.add_argument("--downloads", type=Path, default=DOWNLOADS)
    args = ap.parse_args(argv)

    downloads = args.downloads.expanduser()

    if not CATALOG_YAML.is_file():
        raise SystemExit(f"catalog missing: {CATALOG_YAML}")

    catalog = load_yaml(CATALOG_YAML)
    catalog["updated"] = date.today().isoformat()

    moved: list[str] = []
    if not args.sync_only:
        moved = ingest_from_downloads(
            catalog, downloads=downloads, copy=args.copy, dry_run=args.dry_run
        )

    if not args.dry_run:
        dump_yaml(CATALOG_YAML, catalog)
        write_index_html(catalog)
        sync_json(catalog)
    else:
        print(f"# dry-run: would touch {len(moved)} files")

    print(json.dumps({"ingested": moved, "self_items": sum(1 for i in catalog.get("items") or [] if i.get("lane") == "self")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
