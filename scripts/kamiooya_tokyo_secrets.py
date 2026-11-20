#!/usr/bin/env python3
"""AIナビの Edge Function 用の秘密を、東京の新プロジェクトへ写す（Mac で本人が実行・2026-11-20）。

Supabase は秘密の値を読み出せないため、Mac の .env ファイルにある値を写し先へ登録する。
値は画面に出さない。名前と「登録した／.env に無い」だけを表示する。旧プロジェクトには触れない。

    ~/selenium_env/venv/bin/python scripts/kamiooya_tokyo_secrets.py --target sufbsyddqgekvcgadhpv          # 確認だけ
    ~/selenium_env/venv/bin/python scripts/kamiooya_tokyo_secrets.py --target sufbsyddqgekvcgadhpv --apply  # 登録
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kamiooya_target  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
CHATBOT = REPO / "215_kamiooya" / "C1_cursor" / "1c_神・大家さん倶楽部_AI推進" / "神・大家さん倶楽部情報Q&Aチャットボット"
ENV_FILES = [Path.home() / "git-repos" / ".env.jarvis_private", REPO / ".env.jarvis_private", CHATBOT / "scripts" / ".env"]
# 関数が読む秘密（SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY は Supabase が自動で入れる）
NAMES = [
    "RAIMO_AUTH_GATEWAY_SECRET", "SEMANTIC_SEARCH_SHARED_SECRET", "GEMINI_API_KEY", "GEMINI_LITE_MODEL",
    "COMMUNITY_ATTACHMENTS_PROXY_SECRET", "COMMUNITY_ATTACHMENTS_SESSION_SECRET",
    "COMMUNITY_ATTACHMENTS_MEMBER_READS_ENABLED", "SEMANTIC_SEARCH_DISABLED",
]


def read_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for f in ENV_FILES:
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip().removeprefix("export ").strip()
            out.setdefault(k, v.strip().strip('"').strip("'"))
    return out


def api(method: str, path: str, token: str, body=None):
    req = urllib.request.Request(f"https://api.supabase.com/v1{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                                          "User-Agent": "kamiooya-tokyo-secrets/1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        txt = r.read().decode() or "null"
    return json.loads(txt)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    if a.target == kamiooya_target.DEFAULT_REF:
        print("旧プロジェクトには書き込みません", file=sys.stderr)
        return 2
    env = read_env()
    token = os.environ.get("SUPABASE_ACCESS_TOKEN_KAMIOOYA") or env.get("SUPABASE_ACCESS_TOKEN_KAMIOOYA") \
        or os.environ.get("SUPABASE_ACCESS_TOKEN") or env.get("SUPABASE_ACCESS_TOKEN") or ""
    if not token:
        print("SUPABASE_ACCESS_TOKEN(_KAMIOOYA) が見つかりません（値は表示しません）", file=sys.stderr)
        return 2
    try:
        old = {s["name"] for s in api("GET", f"/projects/{kamiooya_target.DEFAULT_REF}/secrets", token)}
        new = {s["name"] for s in api("GET", f"/projects/{a.target}/secrets", token)}
    except urllib.error.HTTPError as e:
        print(f"Supabase API: HTTP {e.code}", file=sys.stderr)
        return 1
    wanted = [n for n in NAMES if n in old]
    extra_old = sorted(n for n in old if n not in NAMES and not n.startswith("SUPABASE_"))
    body = []
    for n in wanted:
        state = "写し先に登録済み" if n in new else ("登録する" if n in env else ".env に無い（手で登録が必要）")
        print(f"- {n}: {state}")
        if n not in new and n in env:
            body.append({"name": n, "value": env[n]})
    for n in extra_old:
        print(f"- {n}: 旧にだけある（このスクリプトの対象外。必要なら手で登録）")
    if not a.apply:
        print(f"確認だけ（{len(body)} 件を登録予定）。--apply で登録します")
        return 0
    if body:
        api("POST", f"/projects/{a.target}/secrets", token, body)
    print(f"登録しました: {len(body)} 件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
