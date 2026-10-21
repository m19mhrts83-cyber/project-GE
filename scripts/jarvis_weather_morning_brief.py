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

# 降水確率の時間帯（JST）— Slack UI FB 2026-10-22
# 午前 5–11 / 午後 12–16 / 夕方 17–20 / 夜 21–4
POP_BUCKETS: tuple[tuple[str, range], ...] = (
    ("午前", range(5, 12)),
    ("午後", range(12, 17)),
    ("夕方", range(17, 21)),
    ("夜", range(21, 24)),  # 0–4 は別途 night_early
)


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
            "hourly": "precipitation_probability",
            "timezone": "Asia/Tokyo",
            "forecast_days": 2,
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


def _day_prefix(iso_day: str) -> str:
    return iso_day[:10]


def precip_buckets_for_day(data: dict, day: str) -> dict[str, int | None]:
    """指定日の時間帯別・最大降水確率（%）。"""
    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    pops = hourly.get("precipitation_probability") or []
    buckets: dict[str, list[int]] = {name: [] for name, _ in POP_BUCKETS}
    target = _day_prefix(day)
    for t, p in zip(times, pops):
        if not isinstance(t, str) or len(t) < 13:
            continue
        if _day_prefix(t) != target:
            continue
        if p is None:
            continue
        try:
            h = int(t[11:13])
            val = int(p)
        except (TypeError, ValueError):
            continue
        if h < 5:
            buckets["夜"].append(val)
            continue
        for name, hours in POP_BUCKETS:
            if h in hours:
                buckets[name].append(val)
                break
    return {k: (max(v) if v else None) for k, v in buckets.items()}


def format_pop_buckets(buckets: dict[str, int | None]) -> str:
    parts: list[str] = []
    for name, _ in POP_BUCKETS:
        v = buckets.get(name)
        if v is None:
            parts.append(f"{name}—")
        else:
            parts.append(f"{name}{v}%")
    return " / ".join(parts)


def weather_summary(data: dict, *, day: str | None = None) -> str:
    """材料用・複数行。項目間は空行前提で Grok が Slack に載せる。"""
    daily = data.get("daily") or {}
    dates = daily.get("time") or []
    idx = 0
    if day and dates:
        target = _day_prefix(day)
        for i, d in enumerate(dates):
            if _day_prefix(str(d)) == target:
                idx = i
                break
    code = (daily.get("weathercode") or [0] * (idx + 1))[idx]
    tmax = (daily.get("temperature_2m_max") or [None] * (idx + 1))[idx]
    tmin = (daily.get("temperature_2m_min") or [None] * (idx + 1))[idx]
    day_key = day or (str(dates[idx]) if dates else datetime.now(JST).strftime("%Y-%m-%d"))
    buckets = precip_buckets_for_day(data, day_key)
    label = WMO_LABELS.get(int(code), f"コード{code}")
    lines = [f"天気: {label}"]
    if tmax is not None and tmin is not None:
        lines.append(f"気温: {tmin:.0f}〜{tmax:.0f}℃")
    pop_line = format_pop_buckets(buckets)
    if any(v is not None for v in buckets.values()):
        lines.append(f"降水確率: {pop_line}")
    else:
        pop = (daily.get("precipitation_probability_max") or [None] * (idx + 1))[idx]
        if pop is not None:
            lines.append(f"降水確率: {pop}%（日最大・時間帯不明）")
    return "\n".join(lines)


def weather_summary_tomorrow(data: dict, *, today: str) -> str | None:
    daily = data.get("daily") or {}
    dates = daily.get("time") or []
    if len(dates) < 2:
        return None
    tomorrow = str(dates[1])
    if _day_prefix(tomorrow) == _day_prefix(today):
        return None
    return weather_summary(data, day=tomorrow)


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
    weather_today: str,
    transit_md: str,
    gmail_lines: list[str],
    *,
    weather_tomorrow: str | None = None,
) -> str:
    day = datetime.now(JST).strftime("%Y-%m-%d")
    gmail_block = ""
    if gmail_lines:
        gmail_block = "## 予約メール断片（Gmail · 参考）\n" + "\n".join(gmail_lines) + "\n\n"
    tomorrow_block = ""
    if weather_tomorrow:
        tomorrow_block = f"## 明日の天気\n{weather_tomorrow}\n\n"
    return (
        f"## 天気（{day}）\n{weather_today}\n\n"
        f"{tomorrow_block}"
        f"## 予定\n{calendar_md}\n"
        f"{transit_md}\n"
        f"{gmail_block}"
        f"---\n"
        f"target: weather · ホーク参謀傘下 · @天気お知らせ Bot が 6:30 に投稿\n"
        f"指示: 「## 乗る便（何時何分）」の発時刻・列車名／便名をそのまま投稿に載せる。"
        f"予約があれば予約優先。パスワード禁止。時刻をでっち上げない。\n"
        f"投稿レイアウト（Slack UI FB 2026-10-22）:\n"
        f"- 各項目（今日の天気／予定／乗る便／明日／メモ）は1行ずつ。項目のあいだに空行を入れる。\n"
        f"- 本日の降水確率は 午前／午後／夕方／夜 の4帯で書く"
        f"（材料の「降水確率: 午前…」をそのまま使う。ざっくり1値にまとめない）。\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Morning weather + calendar → JarvisBox weather")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-gmail", action="store_true")
    args = ap.parse_args()

    lat, lon = load_home_lat_lon()
    day = datetime.now(JST).strftime("%Y-%m-%d")
    wx_tomorrow: str | None = None
    try:
        wx = fetch_open_meteo(lat, lon)
        wx_today = weather_summary(wx, day=day)
        wx_tomorrow = weather_summary_tomorrow(wx, today=day)
    except Exception as exc:
        wx_today = f"（天気 API 失敗: {exc}）"

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

    body = build_body(
        cal,
        wx_today,
        transit,
        gmail_lines,
        weather_tomorrow=wx_tomorrow,
    )

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
