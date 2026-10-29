#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vimeo 自動字幕がない WeStudy 動画を、Mac 上のローカル Whisper で文字起こしする（AI 使用料ゼロ）。

- 対象: 取得済み MD（jarvis_westudy_*_vtt_batch.py の出力）で「## 動画 N: Vimeo ID」にキューが無い動画。
- 音声: yt-dlp（Referer=レッスンURL）で音声のみ取得し、文字起こし後に削除。
- 文字起こし: mlx-whisper（Apple Silicon）。無ければ faster-whisper。外部 AI API は使わない（会員限定動画を外へ送らない）。
- 出力: 元 MD の隣に `<元名>__whisper.md`（字幕MDと同じ形式・タイムスタンプつき）と、取込用 manifest。
  元 MD は書き換えない（既存登録の content_sha256 を変えないため）。
- 動画ごとの結果を ~/.cache/kamiooya_whisper/ に保存。途中で止めても続きから再開できる。

例:
  ~/selenium_env/venv/bin/python scripts/jarvis_westudy_whisper_fallback.py \
    --manifest apps/jarvis-dashboard/data/course_transcripts/course2_status.json
  # 基礎講座の字幕なし18本:
  ~/selenium_env/venv/bin/python scripts/jarvis_westudy_whisper_fallback.py \
    --manifest apps/jarvis-dashboard/data/kiso_course_status.json \
    --input-dir ~/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1c_神・大家さん倶楽部_AI推進/基礎講座_文字起こし/jarvis \
    --course 神大家1.基礎
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
CACHE = Path.home() / ".cache" / "kamiooya_whisper"
CORRECTIONS = REPO / "config" / "kamiooya_transcript_corrections.tsv"
MLX_MODEL = "mlx-community/whisper-large-v3-turbo"
FW_MODEL = "large-v3-turbo"


def fmt_ts(sec: float) -> str:
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def missing_videos(md: str) -> list[str]:
    """キューが1つも無い動画IDを返す。"""
    videos: list[list] = []
    for line in md.splitlines():
        m = re.match(r"^## 動画 \d+: Vimeo (\d+)\b", line)
        if m:
            videos.append([m.group(1), 0])
        elif videos and re.match(r"^\[\d+:\d{2}(?::\d{2})?\]\s", line):
            videos[-1][1] += 1
    return [vid for vid, cues in videos if not cues]


def glossary_prompt() -> str:
    """Whisper の初期プロンプト。補正表の「正しい語」を並べて固有名詞の誤変換を減らす。"""
    words: list[str] = []
    for line in CORRECTIONS.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or "\t" not in line:
            continue
        w = line.split("\t", 1)[1].strip()
        if w and w not in words:
            words.append(w)
    return ("神大家さん倶楽部の不動産投資講座です。" + "、".join(words))[:400]


def notta_video_ids() -> set[str]:
    """Notta版が入っている動画（運営の文字起こしを優先し、Whisperで二重に起こさない）。"""
    sys.path.insert(0, str(REPO / "215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/scripts"))
    from embed_to_supabase import load_env, get_client

    load_env()
    rows = get_client().table("knowledge_sources").select("video_id").like("source_key", "notta:%").execute().data
    return {str(r["video_id"]) for r in rows if r.get("video_id")}


class Transcriber:
    def __init__(self, engine: str):
        self.engine = engine
        self.prompt = glossary_prompt()
        if engine == "auto":
            try:
                import mlx_whisper  # noqa: F401
                self.engine = "mlx"
            except ImportError:
                self.engine = "faster"
        if self.engine == "faster":
            from faster_whisper import WhisperModel
            self.model = WhisperModel(FW_MODEL, device="auto", compute_type="int8")

    @property
    def label(self) -> str:
        return f"ローカルWhisper（{MLX_MODEL if self.engine == 'mlx' else FW_MODEL}）"

    def __call__(self, audio: Path) -> list[list]:
        if self.engine == "mlx":
            import mlx_whisper
            res = mlx_whisper.transcribe(
                str(audio), path_or_hf_repo=MLX_MODEL, language="ja",
                initial_prompt=self.prompt, condition_on_previous_text=False,
            )
            segs = [(s["start"], s["end"], s["text"]) for s in res.get("segments") or []]
        else:
            segments, _ = self.model.transcribe(
                str(audio), language="ja", initial_prompt=self.prompt,
                condition_on_previous_text=False, vad_filter=True,
            )
            segs = [(s.start, s.end, s.text) for s in segments]
        cues, last = [], None
        for start, end, text in segs:
            text = re.sub(r"\s+", " ", text or "").strip()
            if not text or text == last:  # 無音区間での同文くり返しを落とす
                continue
            last = text
            cues.append([int(start), int(end), text])
        return cues


class EmbedResolver:
    """player URL で落とせない限定公開動画用に、ログインしてレッスンの iframe src（?h=… 付き）を取る。"""

    def __init__(self):
        self.open = False

    def __call__(self, slug: str, vid: str) -> str | None:
        import jarvis_westudy_lesson_vtt_to_md as vtt
        from selenium.webdriver.common.by import By
        import time

        if not self.open:
            vtt.open_logged_in_driver(headless=True)
            self.open = True
        vtt.wlp.driver.get(f"https://westudy.co.jp/lesson/{slug}")
        time.sleep(4)
        for frame in vtt.wlp.driver.find_elements(By.TAG_NAME, "iframe"):
            src = frame.get_attribute("src") or ""
            if f"/video/{vid}" in src:
                return src
        return None

    def close(self):
        if self.open:
            import jarvis_westudy_lesson_vtt_to_md as vtt
            vtt.close_driver()


def ensure_ffmpeg() -> None:
    """yt-dlp と Whisper は PATH 上の `ffmpeg` を探す。Homebrew が無い Mac では venv の imageio-ffmpeg を
    `ffmpeg` という名前で PATH に足す（同梱バイナリは ffmpeg-macos-… という名前なので、そのままでは見つからない）。"""
    if shutil.which("ffmpeg"):
        return
    import os
    import imageio_ffmpeg

    link_dir = CACHE / "bin"
    link_dir.mkdir(parents=True, exist_ok=True)
    link = link_dir / "ffmpeg"
    if not link.exists():
        link.symlink_to(imageio_ffmpeg.get_ffmpeg_exe())
    os.environ["PATH"] = f"{link_dir}{os.pathsep}{os.environ.get('PATH', '')}"


def download_audio(url: str, referer: str, workdir: Path) -> Path:
    ytdlp = shutil.which("yt-dlp") or str(Path(sys.executable).with_name("yt-dlp"))
    cmd = [ytdlp, "-q", "--no-warnings", "-f", "bestaudio/best", "--referer", referer,
           "-o", str(workdir / "audio.%(ext)s"), url]
    subprocess.run(cmd, check=True, timeout=3600)
    files = [p for p in workdir.iterdir() if p.name.startswith("audio.")]
    if not files:
        raise RuntimeError("音声ファイルが取れませんでした")
    return files[0]


def transcribe_video(slug: str, vid: str, transcribe: Transcriber, resolver: EmbedResolver) -> dict:
    cache = CACHE / f"{vid}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    referer = f"https://westudy.co.jp/lesson/{slug}"
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        try:
            audio = download_audio(f"https://player.vimeo.com/video/{vid}", referer, work)
        except Exception:
            src = resolver(slug, vid)
            if not src:
                raise
            audio = download_audio(src, referer, work)
        cues = transcribe(audio)
    result = {"video_id": vid, "label": transcribe.label, "cues": cues,
              "at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")}
    CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def render(lesson: dict, results: list[dict], course: str) -> str:
    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %z")
    lines = [
        f"# {course} 文字起こし（ローカルWhisper） — {lesson['slug']}", "",
        f"更新: {now}", f"レッスン: {lesson.get('url')}", f"タイトル: {lesson.get('title', '')}",
        "取得元: jarvis_westudy_whisper_fallback.py（Vimeo字幕なしの動画を Mac 上で文字起こし）", "",
    ]
    for i, r in enumerate(results, 1):
        lines += [f"## 動画 {i}: Vimeo {r['video_id']} — {r['label']}", "", f"キュー数: {len(r['cues'])}", ""]
        lines += [f"[{fmt_ts(s)}] {t}" for s, _e, t in r["cues"]]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--input-dir", type=Path, help="元MDの場所（course manifest は transcript_dir を使う）")
    ap.add_argument("--course", help="course 名（未指定は manifest の course）")
    ap.add_argument("--engine", choices=["auto", "mlx", "faster"], default="auto")
    ap.add_argument("--limit", type=int, help="動画N本で止める（動作確認用）")
    ap.add_argument("--skip-notta", action="store_true", help="Notta版が登録済みの動画は起こさない（Supabaseを参照）")
    args = ap.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    course = args.course or manifest.get("course") or ""
    src_dir = args.input_dir or Path(manifest["transcript_dir"])
    out_manifest = args.manifest.with_name(args.manifest.stem.replace("_status", "") + "_whisper.json")
    prev = json.loads(out_manifest.read_text(encoding="utf-8")) if out_manifest.exists() else {"lessons": []}
    done = {L["slug"]: L for L in prev.get("lessons") or []}

    skip_vids = notta_video_ids() if args.skip_notta else set()
    targets = []
    for L in manifest.get("lessons") or []:
        name = L.get("jarvis_file")
        if not name or L["slug"] in done or not (src_dir / name).exists():
            continue
        vids = [v for v in missing_videos((src_dir / name).read_text(encoding="utf-8")) if v not in skip_vids]
        if vids:
            targets.append((L, vids))
    total = sum(len(v) for _, v in targets)
    print(f"# {course}: 字幕なし {len(targets)} レッスン / {total} 動画", flush=True)

    if targets:
        ensure_ffmpeg()
    transcribe = Transcriber(args.engine)
    resolver = EmbedResolver()
    count, failed = 0, []
    try:
        for L, vids in targets:
            results = []
            for vid in vids:
                if args.limit and count >= args.limit:
                    break
                try:
                    r = transcribe_video(L["slug"], vid, transcribe, resolver)
                    results.append(r)
                    print(f"  ✅ {L['slug']} Vimeo {vid} cues={len(r['cues'])}", flush=True)
                except Exception as e:
                    failed.append({"slug": L["slug"], "video_id": vid, "error": f"{type(e).__name__}: {str(e)[:200]}"})
                    print(f"  ❌ {L['slug']} Vimeo {vid}: {failed[-1]['error']}", flush=True)
                count += 1
            # レッスン内の全動画を試してから一度だけ書く（後から MD が変わって登録済みと食い違わないように）
            if len(results) + sum(f["slug"] == L["slug"] for f in failed) < len(vids):
                break  # --limit で途中終了
            results = [r for r in results if r["cues"]]
            if results:
                name = Path(L["jarvis_file"]).stem + "__whisper.md"
                (src_dir / name).write_text(render(L, results, course), encoding="utf-8")
                done[L["slug"]] = {"slug": L["slug"], "title": L.get("title"), "url": L.get("url"),
                                   "section": L.get("section"), "jarvis_file": name, "status": "vtt_ready",
                                   "transcript_provider": "local_whisper",
                                   "videos": [{"video_id": r["video_id"], "cues": len(r["cues"])} for r in results]}
            out_manifest.write_text(json.dumps({
                "course": course, "transcript_dir": str(src_dir),
                "graph_root": manifest.get("graph_root"),
                "updated": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                "lessons": list(done.values()), "failed": failed,
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finally:
        resolver.close()
    print(json.dumps({"course": course, "lessons_done": len(done), "videos_tried": count, "failed": len(failed),
                      "manifest": str(out_manifest)}, ensure_ascii=False))
    return 1 if failed else 0  # 失敗を週次レポートで ❌ にする


if __name__ == "__main__":
    raise SystemExit(main())
