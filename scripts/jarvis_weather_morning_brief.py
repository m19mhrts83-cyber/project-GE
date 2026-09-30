#!/usr/bin/env python3
"""朝の天気＋カレンダー＋交通ヒント → JarvisBox（target: weather）。

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
OUTBOX = REPO / "scripts" / "jarvis_bucho_outbox_write.py"
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"

sys.path.insert(0, str(REPO / "scripts"))
from google_calendar_today import fetch_events, format_md  # noqa: E402
from jarvis_weather_transit_hints import (  # noqa: E402
    build_transit_section,
    gmail_reservation_snippets,
)

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
    53: "霧雨",
    55: "強い霧雨",
    61: "雨",
    63: "やや強い雨",
    65: "強い雨",
    80: "にわか雨",
    81: "強いのにわか雨",
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


def _gmail_service_admin():
    """admin Gmail（カレンダーと同系 token）。失敗時 None。"""
    try:
        sys.path.insert(0, str(MANUAL))
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        token = MANUAL / "token_livingsupport.json"
        if not token.is_file():
            token = MANUAL / "token_calendar.json"
        if not token.is_file():
            return None
        scopes = [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/calendar.events",
        ]
        creds = Credentials.from_authorized_user_file(str(token), scopes)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return build("gmail", "v1", credentials=creds)
    except Exception:
        return None


def build_body(
    calendar_md: str,
    weather_line: str,
    transit_md: str,
    gmail_lines: list[str],
) -> str:
    day = datetime.now(JST).strftime("%Y-%m-%d")
    gmail_block = ""
    if gmail_lines:
        gmail_block = "## 予約メール断片（Gmail · 参考）\n" + "\n".join(gmail_lines) + "\n\n"
    return (
        f"## 天気（{day}）\n{weather_line}\n\n"
        f"## 予定\n{calendar_md}\n"
        f"{transit_md}\n"
        f"{gmail_block}"
        f"---\n"
        f"target: weather · ホーク参謀傘下 · @天気お知らせ Bot が 6:30 に投稿\n"
        f"指示: 「## 乗る便（何時何分）」の発時刻・列車名／便名をそのまま投稿に載せる。"
        f"予約があれば予約優先。パスワード禁止。時刻をでっち上げない。\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Morning weather + calendar → JarvisBox weather")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-gmail", action="store_true")
    args = ap.parse_args()

    lat, lon = load_home_lat_lon()
    try:
        wx = fetch_open_meteo(lat, lon)
        wx_line = weather_summary(wx)
    except Exception as exc:
        wx_line = f"（天気 API 失敗: {exc}）"

    day = datetime.now(JST).strftime("%Y-%m-%d")
    try:
        events = fetch_events(login_hint="admin@livingsupport-matsu.co.jp")
        cal = format_md(events, day)
        transit = build_transit_section(events)
    except Exception as exc:
        cal = f"（カレンダー取得失敗: {exc}）"
        transit = "## 交通・予約ヒント\n- （カレンダー失敗のためスキップ）\n"
        events = []

    gmail_lines: list[str] = []
    if not args.skip_gmail:
        svc = _gmail_service_admin()
        if svc is not None:
            gmail_lines = gmail_reservation_snippets(service=svc, day=day)

    body = build_body(cal, wx_line, transit, gmail_lines)

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
