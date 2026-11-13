#!/usr/bin/env python3
"""Just Press Record 等の .m4a を Mac の中だけで文字起こしする（2026-11-13 から）。

前処理: macOS の `afconvert` で WAV 化し、ローカル Whisper（mlx-whisper、無ければ faster-whisper）で起こす。
音声は外へ出さない。従量課金の Gemini API は使わない。
最後の「要約（3行以内）」は Mac の定額AI（jarvis_flat_ai）で付ける。作れなければ要約なしで保存する。
話者の書き分けはしない（Whisper は話者を分けない）。

例:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_transcribe_m4a.py \\
    --input \"$HOME/Library/Mobile Documents/iCloud~com~openplanetsoftware~just-press-record/Documents/2026-08-25/20-05-07.m4a\"
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


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



MLX_MODEL = os.environ.get("JARVIS_TRANSCRIBE_MLX_MODEL", "mlx-community/whisper-large-v3-turbo")
FW_MODEL = os.environ.get("JARVIS_TRANSCRIBE_FW_MODEL", "large-v3")


def _mmss(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 60:02d}:{sec % 60:02d}"


def local_transcribe(wav: Path) -> tuple[str, str]:
    """ローカル Whisper で起こす。(本文, 手段ラベル)。約1分ごとに [mm:ss] を付けて段落にする。"""
    segs: list[tuple[float, str]] = []
    try:
        import mlx_whisper  # noqa: PLC0415

        res = mlx_whisper.transcribe(str(wav), path_or_hf_repo=MLX_MODEL, language="ja",
                                     condition_on_previous_text=False)
        segs = [(float(x["start"]), str(x["text"])) for x in res.get("segments") or []]
        label = f"ローカル Whisper（{MLX_MODEL}）"
    except ImportError:
        from faster_whisper import WhisperModel  # noqa: PLC0415

        model = WhisperModel(FW_MODEL, device="auto", compute_type="int8")
        segments, _ = model.transcribe(str(wav), language="ja", vad_filter=True,
                                       condition_on_previous_text=False)
        segs = [(float(x.start), str(x.text)) for x in segments]
        label = f"ローカル Whisper（faster-whisper {FW_MODEL}）"
    paras: list[str] = []
    cur: list[str] = []
    cur_start = None
    last = None
    for start, text in segs:
        t = " ".join((text or "").split()).strip()
        if not t or t == last:
            continue
        last = t
        if cur_start is None:
            cur_start = start
        cur.append(t)
        if start - cur_start >= 60:
            paras.append(f"[{_mmss(cur_start)}] " + "".join(cur))
            cur, cur_start = [], None
    if cur:
        paras.append(f"[{_mmss(cur_start or 0)}] " + "".join(cur))
    body = "\n\n".join(paras).strip() or "（音声から文字を取り出せませんでした。無音・呼び出し音のみの可能性）"
    return body, label


def flat_summary(body: str) -> str:
    """定額AIで3行要約。作れなければ空。"""
    if len(body) < 80:
        return ""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import jarvis_flat_ai as flat  # noqa: PLC0415

        res = flat.generate(
            "次の電話録音の文字起こしを、日本語で3行以内に要約してください。箇条書き（- ）で、前置きなし。\n\n"
            + body[:12000]
        )
        return res.text.strip()
    except Exception as e:
        print(f"# summary skip: {e}", file=sys.stderr)
        return ""


def main() -> int:
    ap = argparse.ArgumentParser(description="m4a → ローカル Whisper 文字起こし")
    ap.add_argument("--input", "-i", required=True, help=".m4a / .wav パス")
    ap.add_argument("--output", "-o", help="出力 MD（省略時は隣に *_文字起こし.md）")
    ap.add_argument("--stdout", action="store_true", help="ファイル保存せず標準出力のみ")
    args = ap.parse_args()

    src = Path(args.input).expanduser().resolve()
    if not src.is_file():
        raise SystemExit(f"ファイルがありません: {src}")

    validate_media(src)

    with tempfile.TemporaryDirectory(prefix="jarvis_jpr_") as tmp:
        wav = Path(tmp) / f"{src.stem}.wav"
        print(f"# convert: {src.name} → wav", file=sys.stderr)
        to_wav(src, wav)
        print(f"# transcribe locally: {wav.name} ({wav.stat().st_size} bytes)", file=sys.stderr)
        body, via = local_transcribe(wav)
    summary = flat_summary(body)
    if summary:
        body = body + "\n\n## 要約（3行以内）\n\n" + summary

    header = (
        f"# 文字起こし: {src.name}\n\n"
        f"- 元ファイル: `{src}`\n"
        f"- 手段: afconvert → {via}（Jarvis・音声は外に出さない）\n"
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
