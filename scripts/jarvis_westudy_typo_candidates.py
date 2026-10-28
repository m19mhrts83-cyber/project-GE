#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""神大家講座の文字起こしから誤記候補を出す（AI 使用料ゼロ・ローカルのみ）。

考え方（2026-10-26 の基礎講座 189 件と同じ）:
  字幕／Whisper の語のうち、会員コメント・LINE オプチャに一度も出ない語を拾い、
  コメント側にある「読みが同じ語」か「字面が近い語」を修正案にする。
  既存の補正表（config/kamiooya_transcript_corrections.tsv）を当ててから数えるので、直し済みの語は出ない。

入力:
  --manifest   courseN_status.json / courseN_whisper.json（複数可）。MD は manifest の transcript_dir から読む
  --comments   WeStudy 管理者形式 CSV（コメント内容 列）。未指定は exports/ の最新 full_*.csv
  --line       LINE オプチャ本文のキャッシュ（1行1投稿）。未指定は ~/.cache/kamiooya_typo/line_content.txt
出力: 候補 CSV（修正前,修正案,根拠,字幕での出現数,例文,コース）。松野さんが確認 → 承認分を補正表に追記。

例:
  ~/selenium_env/venv/bin/python scripts/jarvis_westudy_typo_candidates.py \
    --manifest apps/jarvis-dashboard/data/course_transcripts/course2_status.json \
    --manifest apps/jarvis-dashboard/data/course_transcripts/course2_whisper.json \
    --out ~/Downloads/誤記候補_神大家2.csv
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
QA = REPO / "215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット"
sys.path.insert(0, str(QA / "scripts"))
from transcript_corrections import fix_text, load_rules  # noqa: E402

EXPORTS = Path.home() / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/exports"
LINE_CACHE = Path.home() / ".cache/kamiooya_typo/line_content.txt"
CUE = re.compile(r"^\[\d+:\d{2}(?::\d{2})?\]\s*(.*)$")
TOKEN = re.compile(r"[ァ-ヴー]{3,}|[一-龥々]{2,}")


def transcript_lines(manifests: list[Path]) -> list[tuple[str, str]]:
    """(コース, 補正済みのキュー本文) を返す。"""
    out = []
    for mp in manifests:
        m = json.loads(mp.read_text(encoding="utf-8"))
        src = Path(m["transcript_dir"])
        for L in m.get("lessons") or []:
            f = src / (L.get("jarvis_file") or "")
            if not L.get("jarvis_file") or not f.exists():
                continue
            for line in f.read_text(encoding="utf-8").splitlines():
                c = CUE.match(line)
                if c:
                    out.append((m.get("course", ""), fix_text(c.group(1))))
    return out


def load_corpus(comments: Path, line: Path) -> str:
    parts = []
    with comments.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            parts.append(row.get("コメント内容") or "")
    if line.exists():
        parts.append(line.read_text(encoding="utf-8"))
    # 補正表の正しい語も「出たことのある語」として扱う
    parts.append("\n".join(load_rules().values()))
    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, action="append", required=True)
    ap.add_argument("--comments", type=Path)
    ap.add_argument("--line", type=Path, default=LINE_CACHE)
    ap.add_argument("--min-count", type=int, default=2, help="字幕でこの回数以上出た語だけ（既定2）")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    comments = args.comments or max(EXPORTS.glob("full_2*.csv"), key=lambda p: p.stat().st_mtime)
    corpus = load_corpus(comments, args.line)
    corpus_tokens = Counter(TOKEN.findall(corpus))

    lines = transcript_lines(args.manifest)
    counts: Counter = Counter()
    example: dict[str, str] = {}
    courses: dict[str, set] = defaultdict(set)
    for course, text in lines:
        for t in TOKEN.findall(text):
            counts[t] += 1
            courses[t].add(course)
            example.setdefault(t, text[:60])

    unseen = [t for t, n in counts.items() if n >= args.min_count and t not in corpus_tokens and t not in corpus]

    import pykakasi
    kks = pykakasi.kakasi()

    def reading(w: str) -> str:
        return "".join(x["hira"] for x in kks.convert(w))

    by_reading: dict[str, tuple[str, int]] = {}
    for w, n in corpus_tokens.items():
        if n < 2:
            continue
        r = reading(w)
        if r not in by_reading or by_reading[r][1] < n:
            by_reading[r] = (w, n)
    frequent = [w for w, n in corpus_tokens.items() if n >= 3]
    by_len: dict[int, list[str]] = defaultdict(list)
    for w in frequent:
        by_len[len(w)].append(w)

    rows = []
    for t in sorted(unseen, key=lambda w: -counts[w]):
        hit = by_reading.get(reading(t))
        if hit and hit[0] != t:
            fix, why = hit[0], "同じ読み"
        else:
            pool = by_len[len(t)] + by_len[len(t) + 1] + by_len.get(len(t) - 1, [])
            # 「継続率→継続」のような複合語の一部は修正案にしない
            pool = [w for w in pool if w not in t and t not in w]
            near = difflib.get_close_matches(t, pool, n=1, cutoff=0.6)
            fix, why = (near[0], "字面が近い") if near else ("", "修正案なし（固有名詞・新語の可能性）")
        rows.append([t, fix, why, counts[t], example[t], "・".join(sorted(courses[t]))])

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["修正前", "修正案", "根拠", "字幕での出現数", "例文", "コース"])
        w.writerows(rows)
    print(json.dumps({"cue_lines": len(lines), "unique_tokens": len(counts), "candidates": len(rows),
                      "with_fix": sum(1 for r in rows if r[1]), "comments_csv": comments.name,
                      "out": str(args.out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
