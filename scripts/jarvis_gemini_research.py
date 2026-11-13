#!/usr/bin/env python3
"""
Jarvis: Gemini API で短文リサーチ（Cloud Agent / ローカル共通）。

Workspace Gemini のチャット履歴同期は対象外。API キーによる調査のみ。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_gemini_research.py "愛知県の投資用不動産ローンの近況を要約して"
  python scripts/jarvis_gemini_research.py --model gemini-flash-latest "質問"

要: GEMINI_FREE_API_KEY（課金を無効にした Google プロジェクトの無料枠専用の鍵）。
2026-11-13 から従量課金の GEMINI_API_KEY は使わない。無料枠は送った内容を Google が製品改善に使うことがあるので、私的な情報は送らない。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


DEFAULT_MODEL = "gemini-flash-latest"


def generate(prompt: str, *, api_key: str, model: str) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.load(r)
    parts = (
        data.get("candidates")
        or [{}]
    )[0].get("content", {}).get("parts") or []
    texts = [p.get("text") or "" for p in parts if isinstance(p, dict)]
    out = "\n".join(t for t in texts if t).strip()
    if not out:
        raise RuntimeError(f"empty response: {json.dumps(data)[:400]}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt", nargs="+", help="調査したい内容")
    ap.add_argument("--model", default=os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL)
    args = ap.parse_args(argv)
    key = (os.environ.get("GEMINI_FREE_API_KEY") or "").strip()
    if not key:
        print("GEMINI_FREE_API_KEY 未設定（従量課金の鍵は使わない）", file=sys.stderr)
        return 1
    prompt = " ".join(args.prompt).strip()
    try:
        print(generate(prompt, api_key=key, model=args.model))
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read()[:300]!r}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
