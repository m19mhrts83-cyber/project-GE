#!/usr/bin/env python3
"""615 円動向報告係 — USD/JPY 推移取得・グラフ・Slack短報。

売買推奨は出さない（報告のみ）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_yen_rate_watch.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_yen_rate_watch.py --apply --push
  ~/selenium_env/venv/bin/python scripts/jarvis_yen_rate_watch.py --apply --push --with-news

停止: JARVIS_YEN_RATE_WATCH_DISABLE=1 または state disabled
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_trade_common import fetch_yahoo_daily  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
STATE_PATH = REPO / ".jarvis_state" / "yen_rate_watch.json"
REPORTS_DIR = (
    REPO
    / "docs"
    / "AIエージェントチーム"
    / "600_リソース・家計室"
    / "615_円動向報告係"
    / "reports"
)
CHARTS_DIR = REPORTS_DIR / "charts"
POST = REPO / "scripts" / "jarvis_slack_webhook_post.py"
AGENT_ID = "615"
AGENT_NAME = "円動向報告係"
SYMBOL_YAHOO = "USDJPY=X"
FRANKFURTER = "https://api.frankfurter.app"


def _now() -> datetime:
    return datetime.now(JST)


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _disabled(state: dict[str, Any]) -> bool:
    if os.environ.get("JARVIS_YEN_RATE_WATCH_DISABLE", "").strip() in ("1", "true", "yes"):
        return True
    return bool(state.get("disabled"))


def _fetch_frankfurter(days: int = 800) -> list[dict[str, Any]]:
    """ECB系。USD→JPY を日次で返す。"""
    end = date.today()
    start = end - timedelta(days=days)
    url = (
        f"{FRANKFURTER}/{start.isoformat()}..{end.isoformat()}"
        f"?from=USD&to=JPY"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "JarvisYenWatch/0.1"})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=45, context=ctx) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    rates = payload.get("rates") or {}
    rows: list[dict[str, Any]] = []
    for d, obj in sorted(rates.items()):
        jpy = (obj or {}).get("JPY")
        if jpy is None:
            continue
        rows.append(
            {
                "symbol": "USDJPY",
                "trade_date": d,
                "close": float(jpy),
                "high": float(jpy),
                "low": float(jpy),
                "source": "frankfurter",
            }
        )
    return rows


def fetch_series() -> tuple[list[dict[str, Any]], str]:
    try:
        rows = fetch_yahoo_daily(SYMBOL_YAHOO, range_="2y")
        if rows:
            return rows, "yahoo"
    except Exception as e:
        print(f"⚠️ Yahoo fetch failed: {e}", file=sys.stderr)
    rows = _fetch_frankfurter()
    if not rows:
        raise RuntimeError("USD/JPY 系列を取得できませんでした（Yahoo/Frankfurter）")
    return rows, "frankfurter"


def split_series(
    rows: list[dict[str, Any]], *, daily_days: int = 31, monthly_months: int = 24
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not rows:
        return [], []
    last = date.fromisoformat(rows[-1]["trade_date"])
    daily_cut = last - timedelta(days=daily_days - 1)
    monthly_cut = last - timedelta(days=monthly_months * 31)
    daily = [r for r in rows if date.fromisoformat(r["trade_date"]) >= daily_cut]
    older = [
        r
        for r in rows
        if monthly_cut <= date.fromisoformat(r["trade_date"]) < daily_cut
    ]
    by_month: dict[str, list[dict[str, Any]]] = {}
    for r in older:
        key = r["trade_date"][:7]
        by_month.setdefault(key, []).append(r)
    monthly: list[dict[str, Any]] = []
    for key in sorted(by_month):
        chunk = by_month[key]
        closes = [float(x["close"]) for x in chunk]
        highs = [float(x.get("high") or x["close"]) for x in chunk]
        lows = [float(x.get("low") or x["close"]) for x in chunk]
        monthly.append(
            {
                "trade_date": chunk[-1]["trade_date"],
                "close": closes[-1],
                "high": max(highs),
                "low": min(lows),
                "month": key,
            }
        )
    return daily, monthly


def stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    closes = [float(r["close"]) for r in rows]
    highs = [float(r.get("high") or r["close"]) for r in rows]
    lows = [float(r.get("low") or r["close"]) for r in rows]
    last = closes[-1]
    prev = closes[-2] if len(closes) > 1 else last
    hi = max(highs)
    lo = min(lows)
    hi_i = highs.index(hi)
    lo_i = lows.index(lo)
    return {
        "last": last,
        "prev": prev,
        "change": last - prev,
        "change_pct": ((last - prev) / prev * 100.0) if prev else 0.0,
        "high": hi,
        "high_date": rows[hi_i]["trade_date"],
        "low": lo,
        "low_date": rows[lo_i]["trade_date"],
        "first": closes[0],
        "first_date": rows[0]["trade_date"],
        "last_date": rows[-1]["trade_date"],
        "n": len(rows),
    }


def render_chart(
    daily: list[dict[str, Any]],
    monthly: list[dict[str, Any]],
    out_path: Path,
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=False)
    fig.suptitle("USD/JPY (615)", fontsize=12)

    def _plot(ax, series: list[dict[str, Any]], title: str) -> None:
        if not series:
            ax.set_title(f"{title}（データなし）")
            return
        xs = [datetime.fromisoformat(r["trade_date"]) for r in series]
        ys = [float(r["close"]) for r in series]
        ax.plot(xs, ys, color="#1f4e79", linewidth=1.5)
        hi = max(ys)
        lo = min(ys)
        hi_i = ys.index(hi)
        lo_i = ys.index(lo)
        ax.scatter([xs[hi_i]], [hi], color="#c0392b", zorder=5, label=f"高 {hi:.2f}")
        ax.scatter([xs[lo_i]], [lo], color="#27ae60", zorder=5, label=f"安 {lo:.2f}")
        ax.axhline(ys[-1], color="#888", linestyle="--", linewidth=0.8, alpha=0.7)
        ax.set_title(title)
        ax.legend(loc="best", fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        ax.tick_params(axis="x", rotation=30)

    _plot(axes[0], daily, "Last 31d (daily)")
    _plot(axes[1], monthly, "Prior ~24m (monthly)")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path


def _optional_news() -> str:
    key = (os.environ.get("TAVILY_API_KEY") or "").strip()
    if not key:
        return ""
    try:
        payload = json.dumps(
            {
                "api_key": key,
                "query": "円ドル 為替 日銀",
                "search_depth": "basic",
                "max_results": 3,
                "include_answer": True,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        answer = (data.get("answer") or "").strip()
        if answer:
            return answer[:400]
        titles = []
        for r in (data.get("results") or [])[:3]:
            t = (r.get("title") or "").strip()
            if t:
                titles.append(t)
        return " / ".join(titles)[:400]
    except Exception as e:
        print(f"⚠️ Tavily news skip: {e}", file=sys.stderr)
        return ""


def build_text(
    *,
    source: str,
    st_all: dict[str, Any],
    st_daily: dict[str, Any],
    chart_rel: str,
    news: str,
) -> str:
    lines = [
        f"【{AGENT_ID} {AGENT_NAME}｜USDJPY】",
        f"・終値: {st_all.get('last', 0):.2f} 円（{st_all.get('last_date')}）",
        f"・前日比: {st_all.get('change', 0):+.2f}（{st_all.get('change_pct', 0):+.2f}%）",
        f"・期間高値: {st_all.get('high', 0):.2f}（{st_all.get('high_date')}）",
        f"・期間安値: {st_all.get('low', 0):.2f}（{st_all.get('low_date')}）",
        f"・直近31日: n={st_daily.get('n', 0)} 高{st_daily.get('high', 0):.2f}/安{st_daily.get('low', 0):.2f}",
        f"・ソース: {source}",
        f"・チャート: {chart_rel}",
        "・注: 報告のみ。売買・ポジション指図はしない。",
    ]
    if news:
        lines.append(f"・ニュース要約: {news}")
    return "\n".join(lines)


def _slack_post(text: str, *, channel: str = "report") -> int:
    if not POST.is_file():
        print("⚠️ slack post script missing", file=sys.stderr)
        return 1
    env = os.environ.copy()
    proc = subprocess.run(
        [sys.executable, str(POST), "--channel", channel, "--text", text],
        cwd=str(REPO),
        env=env,
    )
    return int(proc.returncode)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="reports/state に書き込む")
    ap.add_argument("--push", action="store_true", help="Slack #report へ投稿")
    ap.add_argument("--dry-run", action="store_true", help="取得・文章のみ（既定に近い）")
    ap.add_argument("--with-news", action="store_true", help="Tavily 短要約を付ける")
    ap.add_argument("--json", action="store_true", help="統計を JSON でも出す")
    args = ap.parse_args()

    state = _load_state()
    if _disabled(state):
        print("📎 615: disabled — skip")
        return 0

    try:
        rows, source = fetch_series()
    except Exception as e:
        msg = f"【{AGENT_ID} {AGENT_NAME}｜失敗】\n・{e}"
        print(msg, file=sys.stderr)
        if args.push and not args.dry_run:
            _slack_post(msg, channel="ops")
        return 1

    daily, monthly = split_series(rows)
    st_all = stats(rows)
    st_daily = stats(daily)
    day = _now().strftime("%Y-%m-%d")
    chart_path = CHARTS_DIR / f"{day}_usdjpy.png"
    chart_rel = str(chart_path.relative_to(REPO))

    news = _optional_news() if args.with_news else ""
    text = build_text(
        source=source,
        st_all=st_all,
        st_daily=st_daily,
        chart_rel=chart_rel,
        news=news,
    )
    print(text)
    if args.json:
        print(
            json.dumps(
                {"source": source, "all": st_all, "daily": st_daily, "n": len(rows)},
                ensure_ascii=False,
            )
        )

    write = args.apply or args.push
    if write and not args.dry_run:
        try:
            render_chart(daily, monthly, chart_path)
            print(f"📎 chart: {chart_rel}")
        except Exception as e:
            print(f"⚠️ chart failed: {e}", file=sys.stderr)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        md_path = REPORTS_DIR / f"{day}.md"
        md_path.write_text(
            f"# 615 USD/JPY — {day}\n\n```\n{text}\n```\n\n![chart](charts/{day}_usdjpy.png)\n",
            encoding="utf-8",
        )
        print(f"📎 report: {md_path.relative_to(REPO)}")
        state.update(
            {
                "last_run_at": _now().isoformat(timespec="seconds"),
                "last_source": source,
                "last": st_all,
                "chart": chart_rel,
            }
        )
        _save_state(state)
        if args.push:
            rc = _slack_post(text, channel="report")
            if rc != 0:
                return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
