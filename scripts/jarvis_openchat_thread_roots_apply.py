#!/usr/bin/env python3
"""オプチャのスレッド元投稿（openchat_thread_roots.json）を qa_openchat_threads に反映する。

- 元投稿の取得は line_unofficial_poc/chrline_openchat_thread_roots.py（LINE 読み取りのみ）。
- ここは DB 関数 qa_apply_openchat_thread_roots(p jsonb) を呼ぶだけ（照合は DB 側）。
- jarvis_openchat_publish.py --apply の最後（スレッド番号の更新の後）からも呼ばれる。失敗しても取込は成功扱い。

使い方:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_openchat_thread_roots_apply.py            # 件数だけ（dry-run）
  python scripts/jarvis_openchat_thread_roots_apply.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DEFAULT_ROOTS_JSON = REPO / "line_unofficial_poc" / ".line_auth" / "openchat_thread_roots.json"
BATCH = 100
APPLY_STATUSES = {"ok", "no_root", "deleted"}


def _poc_auth_dir() -> Path | None:
    """CHRLINE 側と同じ認証フォルダ（環境変数 → line_unofficial_poc/.env の LINE_UNOFFICIAL_AUTH_DIR）。"""
    raw = (os.environ.get("LINE_UNOFFICIAL_AUTH_DIR") or "").strip()
    if not raw:
        env = REPO / "line_unofficial_poc" / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
                k, sep, v = line.strip().partition("=")
                if sep and k.strip() == "LINE_UNOFFICIAL_AUTH_DIR":
                    raw = v.strip().strip("'\"")
    if not raw:
        return None
    p = Path(raw).expanduser()
    return p if p.is_absolute() else (REPO / "line_unofficial_poc" / p)


def roots_json_path() -> Path:
    raw = (os.environ.get("JARVIS_OPENCHAT_THREAD_ROOTS_JSON") or "").strip()
    if raw:
        return Path(raw).expanduser()
    auth = _poc_auth_dir()
    return (auth / "openchat_thread_roots.json") if auth else DEFAULT_ROOTS_JSON


def thread_keys(thread_mid: str, title: str | None) -> list[str]:
    """qa_openchat_threads.thread_key になりうる形（line_openchat_logs.thread_title と同じ）。"""
    keys = [f"「{thread_mid[:8]}…」" if len(thread_mid) > 8 else f"「{thread_mid}」"]
    t = (title or "").strip()
    if t:
        keys.append(f"「{t}」")
    return keys


def build_payload(data: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tmid, rec in (data.get("threads") or {}).items():
        if not isinstance(rec, dict) or rec.get("status") not in APPLY_STATUSES:
            continue
        chat = str(rec.get("chat_title") or "").strip()
        if not chat or not str(tmid).startswith("t"):
            continue
        title = str(rec.get("thread_title") or "").strip() or None
        out.append(
            {
                "chat_title": chat,
                "thread_keys": thread_keys(str(tmid), title),
                "title": title,
                "thread_mid": tmid,
                "root_message_id": rec.get("root_message_id"),
                "root_posted_at": rec.get("root_posted_at"),
                "root_text": rec.get("root_text"),
                "status": rec.get("status"),
                "fetched_at": rec.get("fetched_at"),
            }
        )
    return out


def apply_thread_roots(sb: Any, path: Path | None = None, *, dry_run: bool = False) -> int:
    p = path or roots_json_path()
    if not p.exists():
        print(f"ℹ️ スレッド元投稿: ファイルなし（{p.name}）→ スキップ")
        return 0
    payload = build_payload(json.loads(p.read_text(encoding="utf-8")))
    if dry_run:
        print(f"🧵 スレッド元投稿: 反映対象 {len(payload)} 件（dry-run）")
        return 0
    n = 0
    for i in range(0, len(payload), BATCH):
        res = sb.rpc("qa_apply_openchat_thread_roots", {"p": payload[i : i + BATCH]}).execute()
        n += int(res.data or 0)
    print(f"🧵 スレッド元投稿: {len(payload)} 件中 {n} 件をスレッドに反映")
    return n


def main() -> int:
    sys.path.insert(0, str(REPO / "scripts"))
    from jarvis_kurashift_openchat_sync import QA_ENV_CANDIDATES, load_dotenv_file, qa_sb

    ap = argparse.ArgumentParser(description="スレッド元投稿を qa_openchat_threads に反映")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()
    for f in QA_ENV_CANDIDATES:
        load_dotenv_file(f)
    apply_thread_roots(qa_sb(), args.json, dry_run=not args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
