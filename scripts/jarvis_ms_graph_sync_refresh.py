#!/usr/bin/env python3
"""
Jarvis: 回転した MS_GRAPH_REFRESH_TOKEN を .env.jarvis_private へ反映。
任意で GHA Secrets／（opt-in）sync_meta へ。

既定の耐久本線は private ＋ Secrets。sync_meta は --supabase または
JARVIS_MS_GRAPH_USE_SYNC_META=1 のときだけ。

入力:
  ~/.jarvis_state/ms_graph_new_refresh.env
  または --from-env（現在の環境変数）

使い方:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_ms_graph_sync_refresh.py
  python scripts/jarvis_ms_graph_sync_refresh.py --push-gha
  python scripts/jarvis_ms_graph_sync_refresh.py --delete-sync-meta
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
PRIVATE = REPO / ".env.jarvis_private"
NEW_REFRESH = Path.home() / ".jarvis_state" / "ms_graph_new_refresh.env"


def _read_new_refresh() -> str:
    if NEW_REFRESH.is_file():
        for line in NEW_REFRESH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("MS_GRAPH_REFRESH_TOKEN="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return (os.environ.get("MS_GRAPH_REFRESH_TOKEN") or "").strip()


def apply_rotated_refresh(
    *,
    push_gha: bool = False,
    from_env: bool = False,
    supabase: bool = False,
) -> dict[str, str]:
    token = (
        (os.environ.get("MS_GRAPH_REFRESH_TOKEN") or "").strip()
        if from_env
        else _read_new_refresh()
    )
    if not token:
        raise SystemExit(
            f"新しい refresh がありません（{NEW_REFRESH} または MS_GRAPH_REFRESH_TOKEN）"
        )
    if not PRIVATE.is_file():
        raise SystemExit(f"missing {PRIVATE}")

    text = PRIVATE.read_text(encoding="utf-8")
    # bash source で $ ! * が展開されないよう単一引用符で保存
    qtoken = "'" + token.replace("'", "'\\''") + "'"
    if re.search(r"^MS_GRAPH_REFRESH_TOKEN=", text, re.M):
        text = re.sub(
            r"^MS_GRAPH_REFRESH_TOKEN=.*$",
            f"MS_GRAPH_REFRESH_TOKEN={qtoken}",
            text,
            count=1,
            flags=re.M,
        )
    else:
        text = text.rstrip() + f"\nMS_GRAPH_REFRESH_TOKEN={qtoken}\n"
    PRIVATE.write_text(text, encoding="utf-8")
    os.environ["MS_GRAPH_REFRESH_TOKEN"] = token
    if NEW_REFRESH.is_file():
        NEW_REFRESH.unlink()

    from jarvis_ms_graph_refresh_store import fingerprint, persist_refresh, use_sync_meta

    out: dict[str, str] = {
        "private": "updated",
        "refresh_len": str(len(token)),
        "fp": fingerprint(token),
    }

    if supabase or use_sync_meta():
        if supabase and not use_sync_meta():
            os.environ["JARVIS_MS_GRAPH_USE_SYNC_META"] = "1"
        sb_ok = persist_refresh(token)
        out["supabase"] = "ok" if sb_ok else "fail"
    else:
        out["supabase"] = "skipped"

    if push_gha:
        r = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "jarvis_ms_graph_secrets_to_gha.py")],
            cwd=str(REPO),
            env=os.environ.copy(),
            capture_output=True,
            text=True,
        )
        out["gha_exit"] = str(r.returncode)
        out["gha_tail"] = (r.stdout + r.stderr)[-400:]
        if r.returncode != 0:
            raise SystemExit(f"GHA secrets push failed:\n{r.stdout}\n{r.stderr}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--push-gha",
        action="store_true",
        help="GitHub Secrets へも反映（推奨・耐久本線の一部）",
    )
    ap.add_argument(
        "--supabase",
        action="store_true",
        help="sync_meta へも書く（非推奨・opt-in。JARVIS_MS_GRAPH_USE_SYNC_META=1 相当）",
    )
    ap.add_argument(
        "--delete-sync-meta",
        action="store_true",
        help="sync_meta.ms_graph_refresh_token を削除して終了",
    )
    ap.add_argument("--from-env", action="store_true", help="state ファイルではなく現在の env")
    args = ap.parse_args(argv)

    if args.delete_sync_meta:
        from jarvis_ms_graph_refresh_store import delete_persisted_refresh

        ok = delete_persisted_refresh()
        print({"delete_sync_meta": "ok" if ok else "fail"})
        return 0 if ok else 1

    result = apply_rotated_refresh(
        push_gha=args.push_gha,
        from_env=args.from_env,
        supabase=args.supabase,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
