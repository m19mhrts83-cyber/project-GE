#!/usr/bin/env python3
"""AIナビ東京移設の「試しの切替」: 同じ検索を旧（ムンバイ）と新（東京）に投げて、結果と速さを比べる（2026-11-20）。

会員向けの画面は切り替えない。Mac で本人が実行する（値は表示しない）。
回答文は作らせない（skip_answer）ので Gemini の回答生成は呼ばない。検索語の埋め込みだけ各1回。
検索ログには session_id=cutover-smoke で残る。

    ~/selenium_env/venv/bin/python scripts/kamiooya_tokyo_smoke.py --target sufbsyddqgekvcgadhpv
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kamiooya_target  # noqa: E402
from kamiooya_tokyo_secrets import read_env  # noqa: E402

QUERIES = ["雨漏り 修理", "融資 金利", "空室対策"]


def search(ref: str, secret: str, query: str) -> tuple[int, float, list[str]]:
    body = {"query": query, "skip_answer": True, "comment_limit": 10, "chunk_limit": 10, "openchat_limit": 10,
            "session_id": "cutover-smoke"}
    req = urllib.request.Request(kamiooya_target.functions_url("semantic-search", ref), method="POST",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "x-semantic-shared-secret": secret,
                                          "User-Agent": "kamiooya-tokyo-smoke/1"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode() or "{}")
            status = r.status
    except urllib.error.HTTPError as e:
        return e.code, time.monotonic() - t0, []
    ms = time.monotonic() - t0
    keys: list[str] = []
    for field in ("relatedComments", "relatedChunks", "relatedOpenchat"):
        for row in data.get(field) or []:
            if isinstance(row, dict):
                keys.append(str(row.get("comment_id") or row.get("chunk_key") or row.get("id") or ""))
    return status, ms, keys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", required=True)
    a = ap.parse_args(argv)
    secret = read_env().get("SEMANTIC_SEARCH_SHARED_SECRET", "")
    if not secret:
        print("SEMANTIC_SEARCH_SHARED_SECRET が .env にありません", file=sys.stderr)
        return 2
    bad = 0
    for q in QUERIES:
        s1, t1, k1 = search(kamiooya_target.DEFAULT_REF, secret, q)
        s2, t2, k2 = search(a.target, secret, q)
        same = len(set(k1) & set(k2))
        ok = s1 == s2 == 200 and k2 and same >= max(1, len(k1) * 8 // 10)
        bad += 0 if ok else 1
        print(f"{'OK' if ok else 'NG'} 「{q}」 旧 HTTP{s1} {t1*1000:.0f}ms {len(k1)}件 / 新 HTTP{s2} {t2*1000:.0f}ms {len(k2)}件 / 共通 {same}件")
    print("試しの切替: 検索は同じ結果です" if not bad else f"試しの切替: {bad} 件の検索で違いがあります")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
