#!/usr/bin/env python3
"""神大家 AI ナビの Storage（添付）を東京の新プロジェクトへ写す（2026-11-20）。

鍵は環境変数 SOURCE_KEY / TARGET_KEY（service_role）。ログにはファイル名・中身を出さず、件数と量だけ出す。
写し先に同じ名前・同じ大きさのものがあれば飛ばすので、切替の夜にもう一度回すと差分だけ写る。
旧側は読むだけ。
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import requests

BUCKETS = ["community-attachments", "openchat-attachments"]
PAGE = 1000
WORKERS = 16
_local = threading.local()


def _session() -> requests.Session:
    if not hasattr(_local, "s"):
        _local.s = requests.Session()
    return _local.s


def _h(key: str, **extra: str) -> dict:
    return {"apikey": key, "Authorization": f"Bearer {key}", **extra}


def walk(base: str, key: str, bucket: str, prefix: str = "") -> dict[str, int]:
    """bucket 内の全ファイル {path: size}。フォルダは再帰で降りる。"""
    out: dict[str, int] = {}
    offset = 0
    while True:
        r = requests.post(f"{base}/storage/v1/object/list/{bucket}", headers=_h(key),
                          json={"prefix": prefix, "limit": PAGE, "offset": offset,
                                "sortBy": {"column": "name", "order": "asc"}}, timeout=60)
        r.raise_for_status()
        rows = r.json()
        for row in rows:
            path = f"{prefix}{row['name']}"
            if row.get("id") is None:  # フォルダ
                out.update(walk(base, key, bucket, path + "/"))
            else:
                out[path] = int((row.get("metadata") or {}).get("size") or 0)
        if len(rows) < PAGE:
            return out
        offset += PAGE


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--max-minutes", type=float, default=0, help="この分数を過ぎたら新しいファイルに手を付けない（0 は無制限）")
    a = ap.parse_args(argv)
    deadline = time.monotonic() + (a.max_minutes * 60 if a.max_minutes else 10**9)
    skey, tkey = os.environ.get("SOURCE_KEY", ""), os.environ.get("TARGET_KEY", "")
    if not skey or not tkey:
        print("SOURCE_KEY / TARGET_KEY が必要です", file=sys.stderr)
        return 2
    if a.source.rstrip("/") == a.target.rstrip("/"):
        print("写し元と写し先が同じです", file=sys.stderr)
        return 2
    failed = 0
    for bucket in BUCKETS:
        t0 = time.monotonic()
        src = walk(a.source, skey, bucket)
        dst = walk(a.target, tkey, bucket)
        print(f"{bucket}: 一覧 {time.monotonic() - t0:.0f}秒", flush=True)
        todo = [p for p, size in src.items() if dst.get(p) != size]
        copied = moved = 0
        lock = threading.Lock()

        def one(path: str) -> None:
            nonlocal copied, moved, failed
            if time.monotonic() > deadline:
                with lock:
                    failed += 1
                return
            q = urllib.parse.quote(path)
            try:
                s = _session()
                for attempt in range(3):  # 一時的な 5xx・接続切れは少し待って2回までやり直す
                    try:
                        g = s.get(f"{a.source}/storage/v1/object/{bucket}/{q}", headers=_h(skey), timeout=300)
                        g.raise_for_status()
                        ctype = g.headers.get("content-type", "application/octet-stream")
                        r = s.post(f"{a.target}/storage/v1/object/{bucket}/{q}", data=g.content, timeout=300,
                                   headers=_h(tkey, **{"content-type": ctype, "x-upsert": "true"}))
                        r.raise_for_status()
                        break
                    except requests.RequestException as e:
                        code = getattr(getattr(e, "response", None), "status_code", None)
                        if attempt == 2 or (code is not None and code < 500):
                            raise
                        time.sleep(5 * (attempt + 1))
                with lock:
                    copied += 1
                    moved += len(g.content)
                    if copied % 250 == 0:
                        print(f"{bucket}: {copied}/{len(todo)} 件・{moved // 1024 // 1024}MB", flush=True)
            except requests.RequestException as e:
                code = getattr(getattr(e, "response", None), "status_code", type(e).__name__)
                with lock:
                    failed += 1
                print(f"::warning::{bucket}: 1件写せませんでした（{code}）", flush=True)

        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            list(ex.map(one, todo))
        extra = len(set(dst) - set(src))
        print(f"{bucket}: 元 {len(src)} 件 / 写し済み {len(src) - len(todo)} 件 / 今回 {copied} 件・{moved // 1024 // 1024}MB"
              + (f" / 写し先だけにある {extra} 件" if extra else ""))
    if failed:
        print(f"::error::写せなかったファイル {failed} 件（もう一度回すと差分だけ写します）")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
