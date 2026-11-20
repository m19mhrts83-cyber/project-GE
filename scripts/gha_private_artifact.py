#!/usr/bin/env python3
"""GHA の調査用ファイルを Supabase Storage の非公開バケットへ置く（2026-11-20）。

背景: project-GE は public リポなので、actions/upload-artifact で上げたファイルは
GitHub にログインした誰でもダウンロードできる。Zaim の明細 CSV・カード画面の写し・
会員コメントの差分などがそこに 14〜30 日残っていた。
置き場所を課金中の Supabase（非公開バケット gha-private-artifacts）に移す。

使い方（ワークフローの if: always() ステップから）:
    python scripts/gha_private_artifact.py --name zaim-finance --keep-days 14 \
        downloads/ .jarvis_state/zaim_*.json

- 指定したパス（glob 可・ディレクトリ可）を tar.gz 1 つにまとめ、
  <name>/<YYYYMMDD>_<run_id>.tar.gz に置く。何も無ければ何もしない。
- 同じ <name>/ の下で --keep-days より古いものは消す（期限切れの掃除）。
- バケットが無ければ非公開で作る。
- 鍵: JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY（無ければ SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY）。
- 失敗してもワークフローは止めない（終了コード 0、::warning:: を 1 行出すだけ）。中身はログに出さない。

取り出し: Supabase の Storage 画面 → gha-private-artifacts → <name>/ からダウンロード。
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import io
import json
import os
import sys
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BUCKET = "gha-private-artifacts"
MAX_BYTES = 45 * 1024 * 1024  # Storage の既定上限 50MB より少し下


def _env() -> tuple[str, str] | None:
    url = os.environ.get("JARVIS_SUPABASE_URL") or os.environ.get("SUPABASE_URL") or ""
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        return None
    return url.rstrip("/"), key


def _http(base: str, key: str, method: str, path: str, *, body=None, raw: bytes | None = None,
          ctype: str = "application/json", extra: dict[str, str] | None = None):
    req = urllib.request.Request(f"{base}{path}", method=method)
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", ctype)
    for k, v in (extra or {}).items():
        req.add_header(k, v)
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, data=data, timeout=120) as r:
        txt = r.read().decode() or "null"
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        return txt


def _ensure_bucket(base: str, key: str) -> None:
    try:
        _http(base, key, "GET", f"/storage/v1/bucket/{BUCKET}")
        return
    except urllib.error.HTTPError as e:
        if e.code not in (400, 404):
            raise
    _http(base, key, "POST", "/storage/v1/bucket", body={"id": BUCKET, "name": BUCKET, "public": False})


def _collect(patterns: list[str]) -> list[Path]:
    out: list[Path] = []
    for pat in patterns:
        hits = glob.glob(pat, recursive=True) or ([pat] if Path(pat).exists() else [])
        for h in hits:
            p = Path(h)
            if p.is_dir():
                out.extend(q for q in p.rglob("*") if q.is_file())
            elif p.is_file():
                out.append(p)
    seen: set[str] = set()
    uniq = []
    for p in out:
        s = str(p)
        if s not in seen:
            seen.add(s)
            uniq.append(p)
    return uniq


def _pack(files: list[Path]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for p in files:
            tar.add(str(p), arcname=str(p).lstrip("/"))
    return buf.getvalue()


def _prune(base: str, key: str, name: str, keep_days: int) -> int:
    rows = _http(base, key, "POST", f"/storage/v1/object/list/{BUCKET}",
                 body={"prefix": f"{name}/", "limit": 1000, "sortBy": {"column": "name", "order": "asc"}})
    if not isinstance(rows, list):
        return 0
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=keep_days)
    old = []
    for r in rows:
        ts = r.get("created_at") or ""
        try:
            when = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            continue
        if when < cutoff:
            old.append(f"{name}/{r['name']}")
    if old:
        _http(base, key, "DELETE", f"/storage/v1/object/{BUCKET}", body={"prefixes": old})
    return len(old)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--name", required=True, help="置き場所の名前（例: zaim-finance）")
    ap.add_argument("--keep-days", type=int, default=14)
    ap.add_argument("paths", nargs="+")
    a = ap.parse_args(argv)

    files = _collect(a.paths)
    if not files:
        print(f"# private artifact {a.name}: 対象ファイルなし（skip）")
        return 0
    cfg = _env()
    if not cfg:
        print(f"::warning::private artifact {a.name}: Supabase の鍵が無いので置けませんでした（{len(files)} files）")
        return 0
    base, key = cfg
    try:
        blob = _pack(files)
        if len(blob) > MAX_BYTES:
            print(f"::warning::private artifact {a.name}: {len(blob)//1024//1024}MB で大きすぎるため置きません")
            return 0
        _ensure_bucket(base, key)
        run_id = os.environ.get("GITHUB_RUN_ID", "local")
        day = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
        dest = f"{a.name}/{day}_{run_id}.tar.gz"
        _http(base, key, "POST", f"/storage/v1/object/{BUCKET}/{urllib.parse.quote(dest)}",
              raw=blob, ctype="application/gzip", extra={"x-upsert": "true"})
        pruned = _prune(base, key, a.name, a.keep_days)
        print(f"# private artifact: {BUCKET}/{dest} ({len(files)} files, {len(blob)//1024}KB, 古いもの {pruned} 件を削除)")
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as f:
                f.write(f"- 調査用ファイル: Supabase Storage `{BUCKET}/{dest}`（非公開・{a.keep_days}日）\n")
    except Exception as e:  # noqa: BLE001 — 調査用なので本処理は止めない
        msg = e.code if isinstance(e, urllib.error.HTTPError) else type(e).__name__
        print(f"::warning::private artifact {a.name}: 置けませんでした（{msg}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
