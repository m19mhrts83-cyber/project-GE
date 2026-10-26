#!/usr/bin/env python3
"""Vimeo自動字幕の誤記補正。config/kamiooya_transcript_corrections.tsv を左から最長一致で適用する。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "config/kamiooya_kiso_transcripts.yaml").exists())
RULES_PATH = REPO / "config/kamiooya_transcript_corrections.tsv"


def load_rules(path: Path = RULES_PATH) -> dict[str, str]:
    rules: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        bad, good = line.split("\t")[:2]
        rules[bad] = good
    return rules


@lru_cache(maxsize=4)
def _compiled(path: Path) -> tuple[re.Pattern, dict[str, str]]:
    rules = load_rules(path)
    # 正しい語も候補に入れ、「金融機関」の中の「金融機」や「雰囲気」の中の「雰囲」を置換しない
    words = sorted(set(rules) | set(rules.values()), key=lambda w: (-len(w), w))
    return re.compile("|".join(map(re.escape, words))), rules


def fix_text(text: str, path: Path = RULES_PATH) -> str:
    pattern, rules = _compiled(path)
    return pattern.sub(lambda m: rules.get(m[0], m[0]), text)
