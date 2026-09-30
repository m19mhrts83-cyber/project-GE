#!/usr/bin/env python3
"""天気お知らせ向け · 乗る便（何時何分）の組み立て。

- カレンダー予定から公共交通っぽいものを検出
- Yahoo!路線情報で到着指定の乗換を取得（個人利用）
- 予約メモ（カレンダー／任意 Gmail）があれば優先表示
"""

from __future__ import annotations

import base64
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

TRANSIT_HINTS: list[tuple[str, str]] = [
    (r"飛行機|空港|ANA|JAL|peach|スカイマーク|搭乗|フライト", "飛行機"),
    (r"新幹線|のぞみ|ひかり|こだま|みずほ|さくら|スマートEX|EX予約", "新幹線"),
    (r"電車|JR|名鉄|近鉄|地下鉄|名駅|駅|特急|快速", "電車"),
    (r"バス|高速バス|名鉄バス|市バス", "バス"),
    (r"ホテル|宿泊|チェックイン|Marriott|アソシア|出張", "移動あり"),
]

RESERVATION_PATTERNS = [
    re.compile(r"(予約番号|確認番号|PNR|eチケット番号)[:：\s]*([A-Z0-9\-]{5,20})", re.I),
    re.compile(r"(便名|フライト)[:：\s]*([A-Z]{2}\s?\d{2,4})", re.I),
    re.compile(r"(のぞみ|ひかり|こだま)\s*([0-9]{1,4})", re.I),
    re.compile(r"([0-9]{1,2}:[0-9]{2})\s*(発|出発)", re.I),
]

# 行き先ざっくり → Yahoo 駅名
DEST_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"日能研名駅|名鉄名古屋|名駅校"), "名鉄名古屋"),
    (re.compile(r"名古屋駅|名駅|中村区名駅|Marriott|アソシア|太閤通"), "名古屋"),
    (re.compile(r"金山"), "金山(愛知県)"),
    (re.compile(r"栄|矢場町"), "栄(愛知県)"),
    (re.compile(r"中部国際|セントレア"), "中部国際空港"),
    (re.compile(r"東京駅|東京"), "東京"),
    (re.compile(r"新大阪|大阪"), "新大阪"),
    (re.compile(r"京都"), "京都"),
]


def _blob(ev: dict[str, Any]) -> str:
    return " ".join(str(ev.get(k) or "") for k in ("summary", "location", "description"))


def classify_modes(ev: dict[str, Any]) -> list[str]:
    text = _blob(ev)
    if not text.strip():
        return []
    modes: list[str] = []
    for pat, label in TRANSIT_HINTS:
        if re.search(pat, text, re.I):
            modes.append(label)
    if re.search(r"名駅|名古屋|中村区|金山|栄", text) and "電車" not in modes:
        modes.append("電車")
    seen: set[str] = set()
    out: list[str] = []
    for m in modes:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def guess_yahoo_dest(ev: dict[str, Any]) -> str | None:
    text = _blob(ev)
    for pat, sta in DEST_MAP:
        if pat.search(text):
            return sta
    loc = (ev.get("location") or "").strip()
    if loc and len(loc) < 40 and not re.search(r"https?://|, Japan", loc):
        # 施設名そのままでも Yahoo が拾うことがある
        return loc.split()[0]
    return None


def parse_event_start(ev: dict[str, Any]) -> datetime | None:
    raw = ev.get("start") or ""
    if not raw:
        return None
    try:
        if "T" in raw:
            # 2026-08-29T13:50:00+09:00
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(JST)
        # 終日
        return datetime.strptime(raw[:10], "%Y-%m-%d").replace(
            hour=12, minute=0, tzinfo=JST
        )
    except Exception:
        return None


def extract_reservation_bits(text: str) -> list[str]:
    bits: list[str] = []
    if not text:
        return bits
    for pat in RESERVATION_PATTERNS:
        for m in pat.finditer(text):
            bits.append(" ".join(g for g in m.groups() if g))
    for line in text.splitlines():
        line = line.strip()
        if re.search(r"予約|確認|チケット|乗車|搭乗|席番", line) and len(line) < 120:
            if not re.search(r"password|パスワード|PW", line, re.I):
                bits.append(line[:100])
    # uniq
    seen: set[str] = set()
    out: list[str] = []
    for b in bits:
        if b not in seen:
            seen.add(b)
            out.append(b)
    return out[:8]


def yahoo_arrival_search(
    *,
    from_sta: str,
    to_sta: str,
    arrive_at: datetime,
    buffer_min: int = 15,
) -> dict[str, Any] | None:
    """到着時刻指定で Yahoo 乗換の先頭ルートを返す。失敗時 None。"""
    target = arrive_at - timedelta(minutes=max(0, buffer_min))
    y, m, d = target.strftime("%Y"), target.strftime("%m"), target.strftime("%d")
    hh = target.strftime("%H")
    mm_i = int(target.strftime("%M"))
    # Yahoo 分は十の位=m1・一の位=m2（m2=35 だと無視され朝の既定になる）
    m1, m2 = str(mm_i // 10), str(mm_i % 10)
    # type=4 = 到着
    qs = urllib.parse.urlencode(
        {
            "from": from_sta,
            "to": to_sta,
            "y": y,
            "m": m,
            "d": d,
            "hh": hh,
            "m1": m1,
            "m2": m2,
            "type": "4",
            "ticket": "ic",
            "expkind": "1",
            "ws": "3",
            "s": "0",
            "al": "1",
            "shin": "1",
            "ex": "1",
            "hb": "1",
            "b": "1",
            "rail": "1",
        }
    )
    url = f"https://transit.yahoo.co.jp/search/result?{qs}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; JarvisWeather/1.0)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html,
        re.S,
    )
    if not m:
        return {"url": url, "error": "next_data_missing"}
    try:
        data = json.loads(m.group(1))
    except Exception:
        return {"url": url, "error": "json_parse"}
    features = (
        ((data.get("props") or {}).get("pageProps") or {})
        .get("naviSearchParam", {})
        .get("featureInfoList")
        or []
    )
    if not features:
        # otherQuery might mean ambiguous station
        return {"url": url, "error": "no_routes"}

    def _hm_to_min(hm: str | None) -> int | None:
        if not hm or ":" not in hm:
            return None
        try:
            h, mi = hm.split(":")[:2]
            return int(h) * 60 + int(mi)
        except Exception:
            return None

    # 到着指定時刻までに着く候補のうち、できるだけ遅く出る便を採用
    deadline = _hm_to_min(target.strftime("%H:%M")) or 0
    scored: list[tuple[int, dict[str, Any]]] = []
    for feat in features:
        s = feat.get("summaryInfo") or {}
        arr_m = _hm_to_min(s.get("arrivalTime"))
        dep_m = _hm_to_min(s.get("departureTime"))
        if arr_m is None or dep_m is None:
            continue
        if arr_m <= deadline:
            scored.append((dep_m, feat))
    top = max(scored, key=lambda x: x[0])[1] if scored else features[0]
    summary = top.get("summaryInfo") or {}
    cal = summary.get("calendarData") or {}
    return {
        "url": url,
        "departure": summary.get("departureTime"),
        "arrival": summary.get("arrivalTime"),
        "total_time": summary.get("totalTime"),
        "transfer": summary.get("transferCount"),
        "fare": summary.get("totalPrice"),
        "detail": (cal.get("description") or "").strip(),
        "from": from_sta,
        "to": to_sta,
        "arrive_by": target.strftime("%H:%M"),
        "event_at": arrive_at.strftime("%H:%M"),
    }


def format_ride_line(route: dict[str, Any]) -> str:
    dep = route.get("departure") or "?"
    arr = route.get("arrival") or "?"
    detail = (route.get("detail") or "").replace("\n", " / ")
    # 先頭の列車行を強調
    first_train = ""
    for part in (route.get("detail") or "").split("\n"):
        if "名鉄" in part or "JR" in part or "新幹線" in part or "地下鉄" in part or "バス" in part:
            first_train = part.strip()
            break
    head = f"**{dep}発 → {arr}着**（余裕あり · 到着指定 {route.get('arrive_by')}）"
    if first_train:
        return f"{head}\n  乗る: {first_train}\n  詳細: {detail[:200]}"
    return f"{head}\n  詳細: {detail[:200]}"


def build_transit_section(
    events: list[dict[str, Any]],
    *,
    home_station: str = "豊明",
    buffer_min: int = 15,
) -> str:
    blocks: list[str] = []
    for ev in events:
        modes = classify_modes(ev)
        if not modes:
            continue
        start = parse_event_start(ev)
        if start is None:
            continue
        # 終日ホテルは「帰宅／移動」用に朝の便は出さない（当日の有時刻予定のみ）
        raw_start = ev.get("start") or ""
        if "T" not in raw_start and "ホテル" in _blob(ev):
            continue
        title = ev.get("summary") or "(無題)"
        dest = guess_yahoo_dest(ev)
        res_bits = extract_reservation_bits(ev.get("description") or "")
        lines = [
            f"### {start.strftime('%H:%M')} {title}",
            f"- 想定: {'／'.join(modes)}",
        ]
        if res_bits:
            lines.append("- 予約（カレンダー）: " + " · ".join(res_bits[:4]))
            # 予約に発時刻があればそれを正とする
            time_bits = [b for b in res_bits if re.search(r"\d{1,2}:\d{2}", b)]
            if time_bits:
                lines.append(f"- **乗る便（予約）**: {time_bits[0]}")
        if dest and "飛行機" not in modes:
            route = yahoo_arrival_search(
                from_sta=home_station,
                to_sta=dest,
                arrive_at=start,
                buffer_min=buffer_min,
            )
            if route and route.get("departure"):
                lines.append(f"- 乗換検索: {home_station} → {dest}")
                lines.append("- " + format_ride_line(route).replace("\n", "\n  "))
                lines.append(f"- 出典: Yahoo!路線情報 {route.get('url','')[:120]}")
            elif route and route.get("url"):
                lines.append(
                    f"- 乗換検索URL（要確認）: {route.get('url')} （{route.get('error')}）"
                )
            else:
                lines.append(f"- 乗換: {home_station}→{dest} の取得失敗（Grok が Web で時刻確認）")
        elif "飛行機" in modes:
            lines.append("- 飛行機: 予約便の**出発時刻**を正。空港には出発の2時間前目安")
        blocks.append("\n".join(lines))

    if not blocks:
        return "## 乗る便（何時何分）\n- （公共交通の時刻案内が必要な予定なし）\n"
    return (
        "## 乗る便（何時何分）— Jarvis 取得\n"
        "Grok は下の **発時刻・列車名** をそのまま投稿に使う。"
        "予約がある場合は予約を優先。\n\n"
        + "\n\n".join(blocks)
        + "\n"
    )


def gmail_reservation_snippets(
    *,
    service: Any,
    day: str,
    max_msgs: int = 8,
) -> list[str]:
    q = (
        "(新幹線 OR のぞみ OR スマートEX OR EX予約 OR eチケット OR 搭乗 OR "
        "航空券 OR ANA OR JAL OR 予約確認 OR 乗車票) newer_than:21d"
    )
    try:
        res = (
            service.users()
            .messages()
            .list(userId="me", q=q, maxResults=max_msgs)
            .execute()
        )
    except Exception:
        return []
    out: list[str] = []
    for m in res.get("messages") or []:
        try:
            full = (
                service.users()
                .messages()
                .get(userId="me", id=m["id"], format="full")
                .execute()
            )
        except Exception:
            continue
        headers = {
            (h.get("name") or "").lower(): h.get("value") or ""
            for h in (full.get("payload") or {}).get("headers") or []
        }
        subj = headers.get("subject", "")[:80]
        body = _gmail_body_text(full.get("payload") or {})[:2500]
        bits = extract_reservation_bits(subj + "\n" + body)
        tag = "本日関連" if day in body or day.replace("-", "/") in body else "直近"
        if bits:
            out.append(f"- 【{tag}】{subj}: " + " · ".join(bits[:3]))
    return out[:6]


def _gmail_body_text(payload: dict[str, Any]) -> str:
    def walk(p: dict[str, Any]) -> str:
        mime = p.get("mimeType") or ""
        data = (p.get("body") or {}).get("data")
        if data and mime.startswith("text/"):
            try:
                return base64.urlsafe_b64decode(data + "==").decode(
                    "utf-8", errors="replace"
                )
            except Exception:
                return ""
        return "\n".join(walk(x) for x in (p.get("parts") or []))

    return walk(payload)
