#!/usr/bin/env python3
"""AIナビ東京移設: 切替前に、会員が通る経路を東京の関数で確かめる（Mac で本人が実行・2026-11-20）。

会員の画面は切り替えない。値は表示しない。
1. 回答文づくり: semantic-search に回答ありで1回だけ問い合わせる（Gemini の回答生成を1回使う。AIナビ用の従量課金）
2. 会員登録の経路: raimo-auth の名簿登録に名簿にない架空データを送り、not_on_roster が返ることを見る
   （Raimo のバックエンド・ゲートウェイ秘密・東京の表まで通る。架空データなので登録はされない）
3. 回答の設定照合: .env の SEMANTIC_SEARCH_URL が切替後に東京へ作り直されることを見る

    ~/selenium_env/venv/bin/python scripts/kamiooya_tokyo_precheck.py --target sufbsyddqgekvcgadhpv
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kamiooya_target  # noqa: E402
from kamiooya_tokyo_secrets import read_env  # noqa: E402

RAIMO_ORIGIN = "https://ma-54t2keqdelz3.raimo-app.buzz"


def post(url: str, body: dict, headers: dict, timeout: int = 90) -> tuple[int, dict, float]:
    req = urllib.request.Request(url, method="POST", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "kamiooya-tokyo-precheck/1", **headers})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}"), time.monotonic() - t0
    except urllib.error.HTTPError as e:
        try:
            data = json.loads(e.read().decode() or "{}")
        except ValueError:
            data = {}
        return e.code, data, time.monotonic() - t0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", required=True)
    a = ap.parse_args(argv)
    if a.target == kamiooya_target.DEFAULT_REF:
        print("旧プロジェクトではなく東京の ref を指定してください", file=sys.stderr)
        return 2
    env = read_env()
    secret = env.get("SEMANTIC_SEARCH_SHARED_SECRET", "")
    bad = 0

    # 1. 回答文づくり
    s, data, sec = post(kamiooya_target.functions_url("semantic-search", a.target),
                        {"query": "空室対策で最初にやること", "session_id": "cutover-precheck", "comment_limit": 10,
                         "chunk_limit": 10, "openchat_limit": 10},
                        {"x-semantic-shared-secret": secret})
    answer = str(data.get("answer") or "")
    ok = s == 200 and len(answer) >= 50
    bad += 0 if ok else 1
    print(f"{'OK' if ok else 'NG'} 1. 回答文づくり: HTTP{s} {sec:.1f}秒 回答 {len(answer)}文字 参照 {len(data.get('relatedComments') or []) + len(data.get('relatedChunks') or [])}件")

    # 2. 会員登録の経路（名簿にない架空データ）
    s, data, sec = post(kamiooya_target.functions_url("raimo-auth", a.target) + "/auth/register-roster",
                        {"email": "diag-tokyo-precheck@example.invalid", "password_hash": "DiagOnly-NotAMember-1",
                         "name": "診断用", "member_no": "DIAG-NOT-A-MEMBER", "prefecture": ""},
                        {"Origin": RAIMO_ORIGIN})
    code = str(data.get("errorCode") or data.get("error") or "")
    ok = code == "not_on_roster"
    bad += 0 if ok else 1
    print(f"{'OK' if ok else 'NG'} 2. 会員登録の経路: HTTP{s} {sec:.1f}秒 応答 {code or '（なし）'}（not_on_roster なら正常）")

    # 3. 回答の設定照合（切替後に公開し直したとき、Raimo が返す URL が東京になるか）
    url = env.get("SEMANTIC_SEARCH_URL", "")
    rebuilt = re.fullmatch(r"https://[a-z0-9]{20}\.supabase\.co/functions/v1/semantic-search", url) is not None
    ok = rebuilt
    bad += 0 if ok else 1
    print(f"{'OK' if ok else 'NG'} 3. 回答の設定照合: .env の SEMANTIC_SEARCH_URL は"
          + ("切替時に東京へ作り直せる形です" if ok else "想定外の形です（公開し直す前に確認が必要）"))

    print("切替前の確認: すべて通りました" if not bad else f"切替前の確認: {bad} 件が通りませんでした")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
