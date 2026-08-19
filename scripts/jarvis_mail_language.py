"""英語メール判定と Gemini 和訳（GHA 取込用）。"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any

KANA_KANJI = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
LATIN = re.compile(r"[A-Za-z]")


def looks_english(text: str | None) -> bool:
    t = (text or "").strip()
    if len(t) < 40:
        return False
    letters = len(LATIN.findall(t))
    jp = len(KANA_KANJI.findall(t))
    if jp >= 12:
        return False
    return letters >= 80 and letters > jp * 4


def translate_mail_en(*, subject: str, body: str) -> dict[str, str]:
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        return {}
    prompt = (
        "次の英語メールを日本語に翻訳してください。意味は変えず、JSONだけ返す。"
        '形式: {"subject_ja":"","body_ja":""} 前置き禁止。\n\n'
        f"【件名】\n{subject[:300]}\n\n【本文】\n{body[:6000]}"
    )
    models = [
        (os.environ.get("GEMINI_MODEL") or "").strip(),
        "gemini-flash-lite-latest",
        "gemini-flash-latest",
    ]
    models = [m for i, m in enumerate(models) if m and m not in models[:i]]
    last = ""
    for model in models:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={key}"
        )
        payload = json.dumps(
            {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
        ).encode()
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last = str(e)[:160]
            continue
        parts = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts")) or []
        text = "".join(p.get("text") or "" for p in parts if isinstance(p, dict)).strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{[\s\S]*\}", text)
            if not m:
                last = "json"
                continue
            try:
                obj = json.loads(m.group(0))
            except json.JSONDecodeError:
                last = "json2"
                continue
        if isinstance(obj, dict):
            out: dict[str, str] = {}
            if obj.get("subject_ja"):
                out["subject_ja"] = str(obj["subject_ja"]).strip()
            if obj.get("body_ja"):
                out["body_ja"] = str(obj["body_ja"]).strip()
            return out
    if last:
        print(f"# mail translate skipped: {last}", file=__import__("sys").stderr)
    return {}
