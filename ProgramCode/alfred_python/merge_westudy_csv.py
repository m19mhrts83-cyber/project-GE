#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
merge_westudy_csv.py
- westudyスクレイプ結果のトピック別CSVを1本に結合
- 依存: 標準ライブラリのみ
- デフォルト探索先: ~/alfred_python/outputs/westudy の「最新の実行フォルダ」配下
- デフォルト出力先: ~/Downloads/westudy_merged_<timestamp>.csv
"""

import os
import re
import sys
import csv
import glob
import json
import time
import argparse
import hashlib
from datetime import datetime
from collections import OrderedDict

def expand(p: str) -> str:
    return os.path.abspath(os.path.expanduser(p))

def find_latest_run_dir(root_dir: str) -> str:
    """
    root_dir直下にある「実行時刻フォルダ」のうち、更新時刻が最大のものを返す
    """
    if not os.path.isdir(root_dir):
        raise FileNotFoundError(f"root not found: {root_dir}")
    cand = []
    for name in os.listdir(root_dir):
        full = os.path.join(root_dir, name)
        if os.path.isdir(full):
            cand.append((os.path.getmtime(full), full))
    if not cand:
        raise FileNotFoundError(f"no run dirs in: {root_dir}")
    cand.sort(key=lambda x: x[0], reverse=True)
    return cand[0][1]

def list_csv_files(target_dir: str, include_regex: str = None, exclude_regex: str = None, verbose=False):
    """
    target_dir配下を再帰で探索し*.csvを列挙
    include/excludeはパス全体に対してマッチ（大文字小文字無視）
    """
    patt = os.path.join(target_dir, "**", "*.csv")
    files = glob.glob(patt, recursive=True)

    # 既知の結合ファイルや明らかに不要なCSV名を除外
    default_exclude_words = ["merged", "manifest", "topics", "failures"]
    def _skip_name(path):
        base = os.path.basename(path).lower()
        return any(w in base for w in default_exclude_words)

    files = [f for f in files if not _skip_name(f)]

    def _regex_ok(path, rgx):
        return re.search(rgx, path, flags=re.IGNORECASE) is not None

    if include_regex:
        files = [f for f in files if _regex_ok(f, include_regex)]
    if exclude_regex:
        files = [f for f in files if not _regex_ok(f, exclude_regex)]

    files.sort()
    if verbose:
        for f in files:
            print(f" - {f}")
    return files

PREFERRED_COL_ORDER = [
    "external_id", "comment_id", "comment_url",
    "topic_slug", "topic_title", "topic_url",
    "author", "author_id",
    "created_at", "updated_at",
    "content", "content_text", "content_html", "body", "text",
    "likes", "replies", "index",
    "source_file",
]

def compute_row_key_auto(row: dict) -> str:
    """
    重複判定用のキーを自動生成。
    優先度: external_id → comment_id → comment_url → (topic_url, author, created_at, content系) → 全体ハッシュ
    """
    for k in ["external_id", "comment_id", "comment_url"]:
        v = (row.get(k) or "").strip()
        if v:
            return f"{k}:{v}"

    topic_url = (row.get("topic_url") or "").strip()
    author = (row.get("author") or row.get("author_name") or "").strip()
    created_at = (row.get("created_at") or "").strip()
    # content候補を順に探す
    content_keys = ["content", "content_text", "body", "text"]
    content_val = ""
    for ck in content_keys:
        if row.get(ck):
            content_val = str(row.get(ck)).strip()
            break
    if topic_url or author or created_at or content_val:
        key_src = "\u241F".join([topic_url, author, created_at, content_val])  # ␟(unit separator)っぽい文字
        h = hashlib.sha1(key_src.encode("utf-8", errors="ignore")).hexdigest()
        return f"mix:{h}"

    # 最後の砦：行全体のソート済みキー→値でハッシュ
    pairs = []
    for k in sorted(row.keys()):
        v = "" if row.get(k) is None else str(row.get(k))
        pairs.append(f"{k}={v}")
    h = hashlib.sha1("\u241F".join(pairs).encode("utf-8", errors="ignore")).hexdigest()
    return f"all:{h}"

def merge_csvs(
    files,
    output_path,
    encoding="utf-8",
    dedup="auto",
    sort_by=None,
    verbose=False,
):
    """
    filesのCSVを結合し、output_pathに書き出す
    - 列はユニオン
    - dedup='auto'で自動重複除去 / 'none'で無効化
    - sort_byが指定されればその列でソート（存在しなければ無視）
    """
    all_rows = []
    # 列の順序（最終ユニオン）
    col_order = []
    col_set = set()

    loaded_files = 0
    loaded_rows = 0

    for fp in files:
        try:
            with open(fp, "r", encoding=encoding, newline="") as f:
                reader = csv.DictReader(f)
                # ヘッダ補正（重複や空ヘッダに耐性）
                fieldnames = [c if c else "" for c in (reader.fieldnames or [])]
                # 列ユニオン
                for c in fieldnames:
                    if c not in col_set:
                        col_set.add(c)
                        col_order.append(c)

                for row in reader:
                    # 行はdictのまま蓄積
                    r = dict(row)
                    # どのCSVから来たか
                    r.setdefault("source_file", os.path.basename(fp))
                    all_rows.append(r)
                    loaded_rows += 1

            loaded_files += 1
            if verbose:
                print(f"read: {fp}")
        except Exception as e:
            print(f"[WARN] failed to read {fp}: {e}", file=sys.stderr)

    if loaded_files == 0:
        raise RuntimeError("no csv loaded")

    # source_file列をユニオンに確実に含める
    if "source_file" not in col_set:
        col_set.add("source_file")
        col_order.append("source_file")

    # 列の最終順序：PREFERRED優先→それ以外
    final_cols = []
    for c in PREFERRED_COL_ORDER:
        if c in col_set and c not in final_cols:
            final_cols.append(c)
    # 残り
    for c in col_order:
        if c not in final_cols:
            final_cols.append(c)

    # 重複排除
    if dedup == "auto":
        seen = set()
        uniq_rows = []
        for r in all_rows:
            key = compute_row_key_auto(r)
            if key in seen:
                continue
            seen.add(key)
            uniq_rows.append(r)
        all_rows = uniq_rows
    elif dedup == "none":
        pass
    else:
        raise ValueError("--dedup must be 'auto' or 'none'")

    # ソート（存在しない列なら素通し）
    if sort_by and any(sort_by == c for c in final_cols):
        def _sort_key(r):
            v = r.get(sort_by)
            # created_atっぽければ時刻として解釈を試みる
            if isinstance(v, str):
                s = v.strip()
                # よくあるISO/日時の軽い解釈
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                    try:
                        return datetime.strptime(s, fmt)
                    except Exception:
                        pass
            return ("" if v is None else v)
        all_rows.sort(key=_sort_key)

    # 出力
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=final_cols, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for r in all_rows:
            # 欠け列を補完
            out = {c: ("" if r.get(c) is None else r.get(c)) for c in final_cols}
            writer.writerow(out)

    return {
        "files": loaded_files,
        "rows_in": loaded_rows,
        "rows_out": len(all_rows),
        "output": output_path,
        "columns": final_cols,
    }

def main():
    home = os.path.expanduser("~")
    default_root = os.path.join(home, "alfred_python", "outputs", "westudy")
    ts = time.strftime("%Y%m%d_%H%M%S")
    default_out = os.path.join(home, "Downloads", f"westudy_merged_{ts}.csv")

    ap = argparse.ArgumentParser(description="Merge westudy topic CSVs into a single CSV for Notion import.")
    ap.add_argument("--root", default=default_root, help="探索ルート（実行フォルダがこの直下にある想定）")
    ap.add_argument("--run-dir", default=None, help="特定の実行フォルダを直接指定（未指定なら最新版を自動選択）")
    ap.add_argument("--all-runs", action="store_true", help="root配下すべての実行フォルダをまたいで結合（通常は最新のみ）")
    ap.add_argument("--include", default=None, help="取り込み対象パスにマッチさせる正規表現（例: 'monthly|融資'）")
    ap.add_argument("--exclude", default=None, help="除外パスにマッチさせる正規表現")
    ap.add_argument("--output", default=default_out, help="結合CSVの出力先パス")
    ap.add_argument("--encoding", default="utf-8", help="入出力のテキストエンコーディング（既定: utf-8）")
    ap.add_argument("--dedup", choices=["auto", "none"], default="auto", help="重複除去方式（auto=推定で除去 / none=無効）")
    ap.add_argument("--sort-by", default=None, help="特定列でソート（例: created_at）")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    root = expand(args.root)
    output = expand(args.output)

    if args.all_runs:
        target_dir = root
    else:
        if args.run_dir:
            target_dir = expand(args.run_dir)
        else:
            target_dir = find_latest_run_dir(root)

    if args.verbose:
        print(f"[root]    {root}")
        print(f"[target]  {target_dir}")
        print(f"[output]  {output}")
        print(f"[filter]  include={args.include} exclude={args.exclude}")
        print(f"[dedup]   {args.dedup}  [sort] {args.sort_by or '-'}")

    files = list_csv_files(target_dir, include_regex=args.include, exclude_regex=args.exclude, verbose=args.verbose)
    if not files:
        print("対象CSVが見つかりません。探索先やフィルタを見直してください。", file=sys.stderr)
        sys.exit(2)

    res = merge_csvs(
        files=files,
        output_path=output,
        encoding=args.encoding,
        dedup=args.dedup,
        sort_by=args.sort_by,
        verbose=args.verbose,
    )

    # ちょっとしたサマリJSONも出しておくと便利
    summary_path = re.sub(r"\.csv$", ".summary.json", output, flags=re.IGNORECASE)
    with open(summary_path, "w", encoding="utf-8") as jf:
        json.dump(res, jf, ensure_ascii=False, indent=2)

    print(f"\n✅ 結合完了: {res['rows_out']}/{res['rows_in']} 行, {res['files']} ファイル → {res['output']}")
    print(f"   列数: {len(res['columns'])}  サマリ: {summary_path}")

if __name__ == "__main__":
    main()
