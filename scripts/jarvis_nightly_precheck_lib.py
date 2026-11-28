#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Orca 定時実行「夜のまとめ」用 precheck の共通部品（AI なし）。

使い方（各室の precheck スクリプトから）:
    from jarvis_nightly_precheck_lib import Signal, run_precheck, log_delta_errors, gha_failed_today
    run_precheck(name="room300", collect=collect, state_path=...)

約束（Orca の precheck の終了コード）:
    0 = 実行する（異常あり、または判定できなかった）
    1 = 実行しない（正常の晩。AI を起こさない）
判定中に例外が出たら **0（実行する）**＝黙って止めない。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

JST = timezone(timedelta(hours=9))
RUN, SKIP = 0, 1


@dataclass
class Signal:
    level: str  # "red" = 実行する理由 / "yellow" = 記録だけ（単発では起こさない）
    key: str
    text: str


@dataclass
class Ctx:
    state: dict
    now: datetime
    signals: list = field(default_factory=list)

    def add(self, level: str, key: str, text: str) -> None:
        self.signals.append(Signal(level, key, text))


def load_json(path: Path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def age_hours(iso: str | None, now: datetime) -> float | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    return (now - dt).total_seconds() / 3600


def log_delta_errors(path: Path, state: dict, is_error_line: Callable[[str], bool], *, advance: bool = True) -> list[str]:
    """ログの前回の位置より後ろだけを読み、エラー行を返す（位置は state["offsets"] に残す）。
    ファイルが縮んだ（回転した）ときは頭から読む。無ければ空。"""
    offsets = state.setdefault("offsets", {})
    try:
        size = path.stat().st_size
    except OSError:
        return []
    start = int(offsets.get(str(path), size if str(path) not in offsets else 0))
    if str(path) not in offsets:
        # 初回は「いまの末尾」から（過去ログ全部を今夜の異常にしない）
        start = size
    if size < start:
        start = 0
    errs: list[str] = []
    if size > start:
        with open(path, "rb") as f:
            f.seek(start)
            text = f.read(size - start).decode("utf-8", errors="ignore")
        errs = [ln.strip() for ln in text.splitlines() if ln.strip() and is_error_line(ln)]
    if advance:
        offsets[str(path)] = size
    return errs


def gha_failed_today(repo_slug: str, workflow: str, now: datetime, *, timeout: int = 40) -> tuple[list[str], str | None]:
    """今日（JST）の GHA 実行のうち失敗・取消のものを返す。(失敗の一覧, 読めなかった理由)"""
    try:
        r = subprocess.run(
            ["gh", "run", "list", "-R", repo_slug, "--workflow", workflow, "-L", "20", "--json",
             "conclusion,status,createdAt,databaseId"],
            capture_output=True, text=True, timeout=timeout,
        )
        if r.returncode != 0:
            return [], (r.stderr or "gh 失敗").strip()[:120]
        rows = json.loads(r.stdout or "[]")
    except Exception as e:  # noqa: BLE001
        return [], f"{type(e).__name__}"
    day = now.astimezone(JST).date()
    bad = []
    for x in rows:
        try:
            t = datetime.fromisoformat(x["createdAt"].replace("Z", "+00:00")).astimezone(JST)
        except Exception:  # noqa: BLE001
            continue
        if t.date() == day and x.get("status") == "completed" and x.get("conclusion") not in ("success", "skipped", None):
            bad.append(f"{x.get('databaseId')}:{x.get('conclusion')}")
    return bad, None


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_precheck(
    name: str,
    collect: Callable[[Ctx], None],
    state_path: Path,
    *,
    argv: list[str] | None = None,
    now: datetime | None = None,
) -> int:
    """collect(ctx) が ctx.add(...) で信号を足す。red が1つでもあれば RUN(0)、無ければ SKIP(1)。
    `show` は状態を動かさず JSON を出す（常に 0）。"""
    argv = sys.argv[1:] if argv is None else argv
    show = bool(argv) and argv[0] == "show"
    now = now or datetime.now(JST)
    state = load_json(state_path, {})
    ctx = Ctx(state=state, now=now)
    try:
        collect(ctx)
    except Exception as e:  # noqa: BLE001  判定できない＝実行する（黙って止めない）
        ctx.add("red", "precheck_error", f"事前チェックが例外で終わった: {type(e).__name__}")
    reds = [s for s in ctx.signals if s.level == "red"]
    out = {
        "name": name,
        "at": now.isoformat(timespec="seconds"),
        "verdict": "run" if reds else "skip",
        "signals": [s.__dict__ for s in ctx.signals],
    }
    if show:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return RUN
    state["last_check"] = out
    state["last_verdict"] = out["verdict"]
    if not reds:
        state["last_skip_at"] = out["at"]
    try:
        save_json(state_path, state)
    except OSError:
        pass
    print(json.dumps(out, ensure_ascii=False))
    return RUN if reds else SKIP
