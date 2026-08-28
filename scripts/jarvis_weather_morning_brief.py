#!/usr/bin/env python3
"""朝の天気＋カレンダー材料 → JarvisBox（target: weather）。

  cd ~/git-repos
  ~/selenium_env/venv/bin/python scripts/jarvis_weather_morning_brief.py
  ~/selenium_env/venv/bin/python scripts/jarvis_weather_morning_brief.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"
CAL_SCRIPT = REPO / "scripts" / "google_calendar_today.py"
OUTBOX = REPO / "scripts" / "jarvis_bucho_outbox_write.py"

# 豊明市間米町付近（HOME_LAT 未設定時の既定）
DEFAULT_LAT = 35.054
DEFAULT_LON = 137.003


def load_home_lat_lon() -> tuple[float, float]:
    lat = os.environ.get("HOME_LAT", "").strip()
    lon = os.environ.get("HOME_LON", "").strip()
    if lat and lon:
        try:
            return float(lat), float(lon)
        except ValueError:
            pass
    return DEFAULT_LAT, DEFAULT_LON


def fetch_open_meteo(lat: float, lon: float) -> dict:
    params = urllib.parse.urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "daily": "weathercode,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": "Asia/Tokyo",
            "forecast_days": 1,
        }
    )
    url = f"https://api.open-meteo.com/v1/forecast?{params}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


WMO_LABELS = {
    0: "快晴",
    1: "おおむね晴れ",
    2: "一部曇り",
    3: "曇り",
    45: "霧",
    48: "霧氷",
    51: "弱い霧雨",
    61: "雨",
    63: "やや強い雨",
    80: "にわか雨",
    95: "雷雨",
}


def weather_summary(data: dict) -> str:
    daily = data.get("daily") or {}
    code = (daily.get("weathercode") or [0])[0]
    tmax = (daily.get("temperature_2m_max") or [None])[0]
    tmin = (daily.get("temperature_2m_min") or [None])[0]
    pop = (daily.get("precipitation_probability_max") or [None])[0]
    label = WMO_LABELS.get(int(code), f"コード{code}")
    parts = [f"天気: {label}"]
    if tmax is not None and tmin is not None:
        parts.append(f"気温: {tmin:.0f}〜{tmax:.0f}℃")
    if pop is not None:
        parts.append(f"降水確率: {pop}%")
    return " · ".join(parts)


def run_calendar_md() -> str:
    if not CAL_SCRIPT.is_file():
        return "（カレンダー取得スクリプト未配置）"
    proc = subprocess.run(
        [str(PY), str(CAL_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    if proc.returncode != 0:
        return f"（カレンダー取得失敗: {proc.stderr.strip()[:200]}）"
    return proc.stdout.strip()


def build_body(calendar_md: str, weather_line: str) -> str:
    day = datetime.now(JST).strftime("%Y-%m-%d")
    return (
        f"## 天気（{day}）\n{weather_line}\n\n"
        f"## 予定\n{calendar_md}\n\n"
        f"---\n"
        f"target: weather · ホーク参謀傘下 · @天気お知らせ Bot が 6:30 に投稿\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Morning weather + calendar → JarvisBox weather")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    lat, lon = load_home_lat_lon()
    try:
        wx = fetch_open_meteo(lat, lon)
        wx_line = weather_summary(wx)
    except Exception as exc:
        wx_line = f"（天気 API 失敗: {exc}）"

    cal = run_calendar_md()
    body = build_body(cal, wx_line)
    day = datetime.now(JST).strftime("%Y-%m-%d")

    if args.dry_run:
        print(body)
        return 0

    proc = subprocess.run(
        [
            str(PY),
            str(OUTBOX),
            "--title",
            f"朝の天気と予定_{day}",
            "--action",
            "weather_brief",
            "--target",
            "weather",
            "--body",
            body,
        ],
        cwd=str(REPO),
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
