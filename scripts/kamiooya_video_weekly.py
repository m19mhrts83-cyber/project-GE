#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""神大家0〜4の講座動画を週次で差分取込する（Mac launchd・日曜12:00。AI 使用料ゼロ）。

日曜 08:00 の GHA（westudy-raimo-weekly）でレッスン説明文が更新された後に動く。
  1. 新しいレッスンの Vimeo 自動字幕を取得（jarvis_westudy_course_vtt_batch.py）
  2. 字幕のない動画をローカル Whisper で文字起こし（Notta版がある動画は飛ばす）
  3. Supabase・Raimo へ差分登録（補正表で誤記を直してから入れる）
  4. inbox/notta の Notta版を登録し、同じ動画の Whisper版と差し替え（notta_weekly_replace.py）
  5. 新しく入った分の誤記候補 CSV を作る（補正表への追加は松野さんの確認後）
  6. 結果を OneDrive にレポート保存し、#ops へ件数だけ通知
途中のステップが失敗しても残りは進め、失敗はレポートに出す。状態は ~/git-repos/.jarvis_state/kamiooya_video_weekly/。

例:
  ~/selenium_env/venv/bin/python scripts/kamiooya_video_weekly.py --dry-run   # 登録しない
  ~/selenium_env/venv/bin/python scripts/kamiooya_video_weekly.py --post      # 本番（launchd と同じ）
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import jarvis_westudy_course_vtt_batch as batch  # noqa: E402

QA_SCRIPTS = batch.QA_SCRIPTS
STATE = Path.home() / "git-repos/.jarvis_state/kamiooya_video_weekly"
REPORT_DIR = batch.ONEDRIVE_215 / batch.TRANSCRIPT_REL / "週次レポート"
COURSES = ["神大家0.はじめに", "神大家1.基礎", "神大家2.応用", "神大家3.継承", "神大家4.グルコン"]
KISO_MANIFEST = REPO / "apps/jarvis-dashboard/data/kiso_course_status.json"
KISO_DIR = batch.ONEDRIVE_215 / "C1_cursor/1c_神・大家さん倶楽部_AI推進/基礎講座_文字起こし/jarvis"
KISO_ROOT = "215_神・大家さん倶楽部/C1_cursor/1c_神・大家さん倶楽部_AI推進/基礎講座_文字起こし/jarvis"
JST = ZoneInfo("Asia/Tokyo")


def run(step: str, cmd: list[str], log, steps: list[dict]) -> str:
    t0 = time.time()
    print(f"\n## {step}\n$ {' '.join(str(c) for c in cmd)}", file=log, flush=True)
    p = subprocess.run([str(c) for c in cmd], cwd=REPO, capture_output=True, text=True)
    log.write(p.stdout + p.stderr)
    log.flush()
    steps.append({"step": step, "ok": p.returncode == 0, "sec": int(time.time() - t0),
                  "tail": (p.stderr or p.stdout).strip().splitlines()[-1:] if p.returncode else []})
    return p.stdout


def last_json(out: str) -> dict:
    """スクリプト出力の最後の1行 JSON（totals）を読む。"""
    for line in reversed(out.strip().splitlines()):
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass
    return {}


def import_cmd(manifest: Path, course: str, input_dir: Path, graph_root: str, apply: bool) -> list:
    cmd = [sys.executable, QA_SCRIPTS / "import_vimeo_transcripts.py", "--manifest", manifest, "--course", course,
           "--input-dir", input_dir, "--graph-root", graph_root]
    return cmd + (["--apply", "--embed", "--mirror-raimo"] if apply else [])


def build_message(day: str, totals: dict, notta: dict, steps: list[dict], typo: Path | None, report: Path) -> str:
    ng = [s for s in steps if not s["ok"]]
    lines = [f"神大家 動画の週次取込（{day}）",
             f"・新規登録: {totals['videos']}動画 / {totals['chunks']}チャンク（Whisper {totals['whisper_videos']}本）",
             f"・Notta差し替え: {notta.get('replaced', 0)}本、新規 {notta.get('new', 0)}本、要確認 {len(notta.get('hold') or [])}件"]
    if typo:
        lines.append(f"・誤記候補: {typo.name}（確認後に補正表へ追加）")
    if ng:
        lines.append("・失敗: " + "、".join(s["step"] for s in ng))
    lines.append(f"・レポート: {report.name}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="字幕取得・Whisperまでは行い、登録はしない")
    ap.add_argument("--post", action="store_true", help="#ops へ通知")
    ap.add_argument("--course", action="append", help="対象コース（未指定は0〜4すべて）")
    args = ap.parse_args()
    apply = not args.dry_run
    courses = args.course or COURSES
    now = datetime.now(JST)
    day = now.strftime("%Y%m%d")
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "logs").mkdir(exist_ok=True)
    py = sys.executable
    steps: list[dict] = []
    totals = {"videos": 0, "chunks": 0, "whisper_videos": 0}
    manifests: list[Path] = []

    with (STATE / "logs" / f"{day}.log").open("a", encoding="utf-8") as log:
        # 1. 字幕（新しいレッスンだけ。取込済み・基礎manifest分は batch 側で除外）
        cmd = [py, REPO / "scripts/jarvis_westudy_course_vtt_batch.py", "--status-dir", STATE]
        for c in courses:
            cmd += ["--course", c]
        run("字幕取得", cmd, log, steps)

        jobs = [(STATE / f"{batch.course_code(c)}_status.json", c, batch.course_dir(c), batch.graph_root(c))
                for c in courses]
        if "神大家1.基礎" in courses:  # 基礎の字幕なし動画（旧フォルダ）も Whisper で埋める
            jobs.append((KISO_MANIFEST, "神大家1.基礎", KISO_DIR, KISO_ROOT))
        for manifest, course, src, root in jobs:
            if not manifest.exists():
                continue
            # 2. Whisper（同じ manifest の隣に *_whisper.json）
            whisper_manifest = manifest.with_name(manifest.stem.replace("_status", "") + "_whisper.json")
            if manifest == KISO_MANIFEST:  # リポジトリ内に書かないよう state へ写してから回す
                local = STATE / "kiso_status.json"
                local.write_text(manifest.read_text(encoding="utf-8"), encoding="utf-8")
                manifest, whisper_manifest = local, STATE / "kiso_whisper.json"
            run(f"Whisper {course}", [py, REPO / "scripts/jarvis_westudy_whisper_fallback.py", "--manifest", manifest,
                                      "--input-dir", src, "--course", course, "--skip-notta"], log, steps)
            # 3. 登録（差分のみ。基礎の旧manifestは取込済みなので Whisper 分だけ）
            pairs = [(whisper_manifest, True)] if manifest.name == "kiso_status.json" else [(manifest, False), (whisper_manifest, True)]
            for m, is_whisper in pairs:
                if not m.exists():
                    continue
                out = run(f"登録 {course}{'（Whisper）' if is_whisper else ''}", import_cmd(m, course, src, root, apply), log, steps)
                t = last_json(out)
                added = t.get("supabase_added", 0) if apply else t.get("chunks", 0)
                if added:
                    totals["chunks"] += added
                    vids = t.get("videos_added", 0) if apply else t.get("videos", 0)
                    totals["videos"] += vids
                    totals["whisper_videos"] += vids if is_whisper else 0
                    manifests.append(m)

        # 4. Notta 差し替え
        notta_report = STATE / f"notta_{day}.json"
        cmd = [py, QA_SCRIPTS / "notta_weekly_replace.py", "--report", notta_report] + (["--apply"] if apply else [])
        run("Notta差し替え", cmd, log, steps)
        notta = json.loads(notta_report.read_text(encoding="utf-8")) if notta_report.exists() else {}

        # 5. 誤記候補（新しく入った分だけ）
        typo = None
        if manifests:
            typo = REPORT_DIR / f"誤記候補_週次_{day}.csv"
            REPORT_DIR.mkdir(parents=True, exist_ok=True)
            cmd = [py, REPO / "scripts/jarvis_westudy_typo_candidates.py", "--out", typo]
            for m in manifests:
                cmd += ["--manifest", m]
            run("誤記候補", cmd, log, steps)
            if not typo.exists():
                typo = None

    # 6. レポート・通知
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = REPORT_DIR / f"動画取込_{day}.md"
    msg = build_message(now.strftime("%m/%d"), totals, notta, steps, typo, report)
    body = [f"# {msg.splitlines()[0]}", "", *msg.splitlines()[1:], "", "## ステップ", ""]
    body += [f"- {'✅' if s['ok'] else '❌'} {s['step']}（{s['sec']}秒）{' ' + ' '.join(s['tail']) if s['tail'] else ''}" for s in steps]
    if notta.get("hold"):
        body += ["", "## Notta 要確認", ""] + [f"- {h['file']}: {h.get('why', '')}" for h in notta["hold"]]
    body += ["", f"モード: {'本番' if apply else 'dry-run（登録なし）'}", f"ログ: {STATE / 'logs' / (day + '.log')}"]
    report.write_text("\n".join(body) + "\n", encoding="utf-8")
    (STATE / "last_run.json").write_text(json.dumps({"at": now.isoformat(timespec="seconds"), "apply": apply,
                                                     "totals": totals, "steps": steps}, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
    print(msg)
    changed = totals["videos"] or notta.get("replaced") or notta.get("new") or notta.get("hold") or any(not s["ok"] for s in steps)
    if args.post and changed:
        subprocess.run([py, REPO / "scripts/jarvis_slack_webhook_post.py", "--channel", "ops", "--text", msg], cwd=REPO)
    return 1 if any(not s["ok"] for s in steps) else 0


if __name__ == "__main__":
    raise SystemExit(main())
