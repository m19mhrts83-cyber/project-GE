#!/usr/bin/env python3
"""Just Press Record 等の .m4a を Gemini で文字起こしする。

前処理: macOS の `afconvert` で WAV 化し、Gemini（無料枠）へ送る。
話者分離はモデル任せ（分かれば 話者A/B）。

例:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_transcribe_m4a.py \\
    --input \"$HOME/Library/Mobile Documents/iCloud~com~openplanetsoftware~just-press-record/Documents/2026-08-25/20-05-07.m4a\"
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


API_BASE = "https://generativelanguage.googleapis.com"
DEFAULT_MODEL = "gemini-3.5-flash"
PROMPT = """あなたは日本語の電話録音の文字起こし係です。
次の音声を可能な限り正確に文字起こししてください。

出力ルール:
1. 話者が区別できそうなら「話者A:」「話者B:」で分けて書く（断定できないときは無理に分けず、段落で続ける）。
2. 聞き取れない箇所は［聴き取り不能］と書く。
3. フィラー（えー、あのー）は必要最小限に残す。
4. タイムスタンプは分単位の目安で、大きな話題の切れ目だけ `[mm:ss]` を付けてよい（細かすぎなくてよい）。
5. 最後に「## 要約（3行以内）」を付ける。
6. 前置き・解説は不要。Markdown 本文のみ。
7. 呼び出し音・無音のみならその旨を短く書いてよい。
"""


def _api_key() -> str:
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        raise SystemExit("GEMINI_API_KEY が未設定です。.env.jarvis_private を source してください。")
    return key


def _safe_url(url: str) -> str:
    return url.split("?key=")[0]


def _http_json(
    method: str,
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 300,
) -> dict:
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {e.code} {_safe_url(url)}: {err[:800]}") from e


def validate_media(path: Path) -> None:
    raw = path.read_bytes()
    if path.suffix.lower() == ".m4a" and b"mdat" not in raw:
        raise SystemExit(
            f"この .m4a は媒体データ（mdat）が無く再生できません（iCloud未展開や破損の可能性）: {path}\n"
            "iPhone で Just Press Record を開き、該当ファイルを再生→Mac へ再同期してから再実行してください。"
        )


def to_wav(src: Path, wav_path: Path, *, large: bool = False) -> None:
    """macOS afconvert で 16-bit PCM WAV へ。大ファイルは 16kHz mono に落とす。"""
    if not shutil.which("afconvert"):
        raise SystemExit("afconvert が見つかりません（macOS 標準のはずです）。")
    if src.suffix.lower() in {".wav", ".wave"}:
        shutil.copy2(src, wav_path)
        return
    # 大きい m4a は WAV が膨らみすぎるためレートを落とす
    if large or src.stat().st_size >= 8_000_000:
        cmd = ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(src), str(wav_path)]
    else:
        cmd = ["afconvert", "-f", "WAVE", "-d", "LEI16", str(src), str(wav_path)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise SystemExit(
            f"afconvert 失敗: {e.stderr or e.stdout or e}\n"
            "ファイルが壊れているか、未ダウンロードの可能性があります。"
        ) from e
    if not wav_path.is_file() or wav_path.stat().st_size < 1000:
        raise SystemExit("WAV 変換結果が空です。")


def upload_wav(wav_path: Path, api_key: str) -> str:
    raw = wav_path.read_bytes()
    mime = "audio/wav"
    start_headers = {
        "x-goog-api-key": api_key,
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(len(raw)),
        "X-Goog-Upload-Header-Content-Type": mime,
        "Content-Type": "application/json",
    }
    meta = json.dumps({"file": {"display_name": wav_path.name}}).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}/upload/v1beta/files",
        data=meta,
        method="POST",
        headers=start_headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            upload_url = resp.headers.get("X-Goog-Upload-URL")
            if not upload_url:
                raise SystemExit("Upload URL が返りませんでした。")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"upload start HTTP {e.code}: {err[:800]}") from e

    info = _http_json(
        "POST",
        upload_url,
        data=raw,
        headers={
            "Content-Length": str(len(raw)),
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
        },
        timeout=600,
    )
    file_info = info.get("file") or info
    name = file_info.get("name")
    uri = file_info.get("uri")
    if not name:
        raise SystemExit(f"upload 応答不正: {info!r}")
    for _ in range(60):
        st = _http_json(
            "GET",
            f"{API_BASE}/v1beta/{name}",
            headers={"x-goog-api-key": api_key},
            timeout=60,
        )
        state = (st.get("state") or "").upper()
        if state == "ACTIVE":
            return st.get("uri") or uri
        if state == "FAILED":
            raise SystemExit(f"ファイル処理失敗: {st}")
        time.sleep(2)
    raise SystemExit("ファイルが ACTIVE になりませんでした。")


def generate_transcript(file_uri: str, api_key: str, model: str) -> str:
    url = f"{API_BASE}/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": PROMPT},
                    {"file_data": {"mime_type": "audio/wav", "file_uri": file_uri}},
                ]
            }
        ],
        "generationConfig": {"temperature": 0.2},
    }
    out = _http_json(
        "POST",
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        timeout=600,
    )
    cands = out.get("candidates") or []
    if not cands:
        raise SystemExit(f"候補なし: {json.dumps(out, ensure_ascii=False)[:800]}")
    parts = (((cands[0] or {}).get("content") or {}).get("parts")) or []
    texts = [p.get("text", "") for p in parts if p.get("text")]
    text = "\n".join(texts).strip()
    if not text:
        raise SystemExit(f"本文空: {json.dumps(out, ensure_ascii=False)[:800]}")
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description="m4a → Gemini 文字起こし")
    ap.add_argument("--input", "-i", required=True, help=".m4a / .wav パス")
    ap.add_argument("--output", "-o", help="出力 MD（省略時は隣に *_文字起こし.md）")
    ap.add_argument("--model", default=os.environ.get("JARVIS_TRANSCRIBE_MODEL", DEFAULT_MODEL))
    ap.add_argument("--stdout", action="store_true", help="ファイル保存せず標準出力のみ")
    args = ap.parse_args()

    src = Path(args.input).expanduser().resolve()
    if not src.is_file():
        raise SystemExit(f"ファイルがありません: {src}")

    validate_media(src)
    api_key = _api_key()

    with tempfile.TemporaryDirectory(prefix="jarvis_jpr_") as tmp:
        wav = Path(tmp) / f"{src.stem}.wav"
        print(f"# convert: {src.name} → wav", file=sys.stderr)
        to_wav(src, wav)
        print(f"# upload: {wav.name} ({wav.stat().st_size} bytes)", file=sys.stderr)
        uri = upload_wav(wav, api_key)
        print(f"# generate: model={args.model}", file=sys.stderr)
        body = generate_transcript(uri, api_key, args.model)

    header = (
        f"# 文字起こし: {src.name}\n\n"
        f"- 元ファイル: `{src}`\n"
        f"- 手段: afconvert → Gemini `{args.model}`（Jarvis）\n"
        f"- 注意: 自動文字起こしのため誤変換あり。重要判断は録音で確認。\n\n"
        f"---\n\n"
    )
    full = header + body + "\n"

    if args.stdout:
        sys.stdout.write(full)
        return 0

    out = Path(args.output).expanduser() if args.output else src.with_name(f"{src.stem}_文字起こし.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(full, encoding="utf-8")
    print(f"✅ 保存: {out}", file=sys.stderr)
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
