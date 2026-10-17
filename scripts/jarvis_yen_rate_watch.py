#!/usr/bin/env python3
"""615 円動向報告係 — USD/JPY 推移取得・グラフ・Slack短報。

売買推奨は出さない（報告のみ）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_yen_rate_watch.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_yen_rate_watch.py --apply --push
  ~/selenium_env/venv/bin/python scripts/jarvis_yen_rate_watch.py --apply --push --with-news
  # --apply 時: reports + Supabase yen_rate_daily / watch_status（/yen）
  # --push: Slack #report

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


def _row_on_or_before(
    rows: list[dict[str, Any]], target: date
) -> dict[str, Any] | None:
    """target 当日以前で最も近い行（休日は直前営業日）。"""
    best: dict[str, Any] | None = None
    for r in rows:
        d = date.fromisoformat(r["trade_date"])
        if d > target:
            break
        best = r
    return best


def compare_windows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """前日・約1ヶ月前・約1年前との比較行を返す。"""
    if len(rows) < 2:
        return []
    last = rows[-1]
    last_d = date.fromisoformat(last["trade_date"])
    last_px = float(last["close"])
    specs = [
        ("前日比", rows[-2]),
        ("約1ヶ月前", _row_on_or_before(rows, last_d - timedelta(days=30))),
        ("約1年前", _row_on_or_before(rows, last_d - timedelta(days=365))),
    ]
    out: list[dict[str, Any]] = []
    for label, ref in specs:
        if not ref:
            out.append(
                {
                    "label": label,
                    "ref_date": "—",
                    "ref": None,
                    "change": None,
                    "change_pct": None,
                    "missing": True,
                }
            )
            continue
        ref_px = float(ref["close"])
        ch = last_px - ref_px
        pct = (ch / ref_px * 100.0) if ref_px else 0.0
        out.append(
            {
                "label": label,
                "ref_date": ref["trade_date"],
                "ref": ref_px,
                "change": ch,
                "change_pct": pct,
                "missing": False,
            }
        )
    return out


def _fmt_signed(n: float | None, *, digits: int = 2, suffix: str = "") -> str:
    if n is None:
        return "—"
    return f"{n:+.{digits}f}{suffix}"


def _fmt_px(n: float | None) -> str:
    if n is None:
        return "—"
    return f"{n:.2f}"


def _table_ascii(compares: list[dict[str, Any]]) -> list[str]:
    """Slack向け固定幅テーブル。"""
    headers = ("比較", "参照日", "当時", "差分(円)", "変化率")
    rows_s: list[tuple[str, str, str, str, str]] = [headers]
    for c in compares:
        if c.get("missing"):
            rows_s.append((c["label"], "—", "—", "—", "—"))
            continue
        rows_s.append(
            (
                c["label"],
                str(c["ref_date"]),
                _fmt_px(c["ref"]),
                _fmt_signed(c["change"]),
                _fmt_signed(c["change_pct"], suffix="%"),
            )
        )
    widths = [max(len(r[i]) for r in rows_s) for i in range(5)]
    lines = []
    for i, row in enumerate(rows_s):
        line = "  ".join(row[j].ljust(widths[j]) for j in range(5))
        lines.append(line)
        if i == 0:
            lines.append("  ".join("-" * widths[j] for j in range(5)))
    return lines


def _table_markdown(compares: list[dict[str, Any]]) -> str:
    lines = [
        "| 比較 | 参照日 | 当時(円) | 差分(円) | 変化率 |",
        "|---|---|---:|---:|---:|",
    ]
    for c in compares:
        if c.get("missing"):
            lines.append(f"| {c['label']} | — | — | — | — |")
            continue
        lines.append(
            f"| {c['label']} | {c['ref_date']} | {_fmt_px(c['ref'])} | "
            f"{_fmt_signed(c['change'])} | {_fmt_signed(c['change_pct'], suffix='%')} |"
        )
    return "\n".join(lines)


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


def build_evaluation(
    *,
    st_all: dict[str, Any],
    compares: list[dict[str, Any]],
    news: str,
) -> str:
    """Phase2 評価コメント（確率表現・売買指図なし）。

    あかつき外債・Bloomo 等の円換算感度の文脈だけ。デイトレ勧誘はしない。
    """
    last = float(st_all.get("last") or 0)
    parts: list[str] = []
    mom = next((c for c in compares if c.get("label") == "約1ヶ月前"), None)
    yoy = next((c for c in compares if c.get("label") == "約1年前"), None)
    if mom and not mom.get("missing") and mom.get("change_pct") is not None:
        pct = float(mom["change_pct"])
        if abs(pct) >= 2.0:
            direction = "円安寄り" if pct > 0 else "円高寄り"
            parts.append(
                f"直近1ヶ月は終値比 {pct:+.1f}%（{direction}）。"
                "海外資産の円換算は、同方向に感度が出やすい時期とみる余地がある。"
            )
        else:
            parts.append(
                f"直近1ヶ月の振れは小さめ（終値比 {pct:+.1f}%）。"
                "円換算の短期ノイズは抑えめ、と読むのが無難。"
            )
    if yoy and not yoy.get("missing") and yoy.get("change_pct") is not None:
        ypct = float(yoy["change_pct"])
        parts.append(
            f"1年前比は {ypct:+.1f}%（当時 {_fmt_px(yoy.get('ref'))} → いま {last:.2f}）。"
            "長期の水準変化として把握する程度でよい。"
        )
    hi = st_all.get("high")
    lo = st_all.get("low")
    if hi is not None and lo is not None and last:
        span = float(hi) - float(lo)
        if span > 0:
            pos = (last - float(lo)) / span
            if pos >= 0.75:
                parts.append(
                    "取得期間のレンジでは高め帯付近。円建てで見る外貨建て資産は、"
                    "円安寄りの水準感が出やすい。"
                )
            elif pos <= 0.25:
                parts.append(
                    "取得期間のレンジでは低め帯付近。円高寄りのときの円換算感度に注意。"
                )
            else:
                parts.append("取得期間レンジの中ほど。極端な片側バイアスは読みにくい。")
    if news:
        parts.append(f"ニュース要約を踏まえると: {news[:220]}")
    parts.append(
        "※評価は参考の見立てのみ。売買・ポジション・レバレッジの指図はしない。"
        "コア（NISA等）の方針は変えない。"
    )
    return " ".join(parts)


def _sb_rest(
    base: str,
    key: str,
    table: str,
    rows: list[dict[str, Any]] | dict[str, Any],
    *,
    on_conflict: str,
) -> None:
    """PostgREST upsert（supabase-py 不要・GHA向け）。"""
    url = f"{base.rstrip('/')}/rest/v1/{table}?on_conflict={on_conflict}"
    body = json.dumps(rows, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
            "User-Agent": "JarvisYenWatch/0.2",
        },
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
        resp.read()


def push_dashboard(
    *,
    rows: list[dict[str, Any]],
    source: str,
    st_all: dict[str, Any],
    st_daily: dict[str, Any],
    compares: list[dict[str, Any]],
    evaluation: str,
    news: str,
    chart_rel: str,
) -> dict[str, Any]:
    """yen_rate_daily + watch_status へ投影。秘密未設定なら soft-fail。"""
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        return {"ok": False, "reason": "JARVIS_SUPABASE_* missing"}
    now = _now().isoformat(timespec="seconds")
    upsert_rows: list[dict[str, Any]] = []
    for r in rows:
        upsert_rows.append(
            {
                "trade_date": r["trade_date"],
                "symbol": "USDJPY",
                "close": float(r["close"]),
                "high": float(r.get("high") or r["close"]),
                "low": float(r.get("low") or r["close"]),
                "source": r.get("source") or source,
                "payload": {},
                "updated_at": now,
            }
        )
    n = 0
    for i in range(0, len(upsert_rows), 100):
        chunk = upsert_rows[i : i + 100]
        _sb_rest(url, key, "yen_rate_daily", chunk, on_conflict="trade_date,symbol")
        n += len(chunk)
    last = st_all.get("last")
    last_date = st_all.get("last_date")
    summary = (
        f"USD/JPY {last:.2f}（{last_date}）"
        if isinstance(last, (int, float))
        else "USD/JPY 取得済"
    )
    payload = {
        "symbol": "USDJPY",
        "source": source,
        "last": st_all,
        "daily": st_daily,
        "compares": compares,
        "evaluation": evaluation,
        "news": news or None,
        "chart": chart_rel,
        "href": "/yen",
        "n_rows": n,
    }
    _sb_rest(
        url,
        key,
        "watch_status",
        {
            "id": "yen_rate",
            "title": "円動向（USD/JPY）",
            "category": "finance",
            "level": "info",
            "summary": summary,
            "detail": (evaluation[:500] if evaluation else summary),
            "source": "jarvis_yen_rate_watch",
            "status": "active",
            "checked_at": now,
            "payload": payload,
            "updated_at": now,
        },
        on_conflict="id",
    )
    _sb_rest(
        url,
        key,
        "sync_meta",
        {
            "key": "yen_rate_pushed_at",
            "value": now,
            "updated_at": now,
        },
        on_conflict="key",
    )
    return {"ok": True, "n": n}


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
    compares: list[dict[str, Any]],
    chart_rel: str,
    news: str,
    evaluation: str = "",
) -> str:
    last = st_all.get("last", 0) or 0
    last_date = st_all.get("last_date") or "—"
    lines = [
        f"【{AGENT_ID} {AGENT_NAME}｜USDJPY】",
        f"終値 {last:.2f} 円（{last_date}）／ソース: {source}",
        "",
        "■ 比較（終値との差）",
        *_table_ascii(compares),
        "",
        "■ レンジ",
        f"取得期間  高 {_fmt_px(st_all.get('high'))}（{st_all.get('high_date')}）"
        f"  /  安 {_fmt_px(st_all.get('low'))}（{st_all.get('low_date')}）",
        f"直近31日  高 {_fmt_px(st_daily.get('high'))}  /  安 {_fmt_px(st_daily.get('low'))}"
        f"  （n={st_daily.get('n', 0)}）",
        "",
        f"チャート: {chart_rel}",
        "ダッシュ: /yen",
        "注: 報告のみ。売買・ポジション指図はしない。",
    ]
    if evaluation:
        lines.extend(["", f"見立て: {evaluation}"])
    elif news:
        lines.extend(["", f"ニュース要約: {news}"])
    return "\n".join(lines)


def build_report_md(
    *,
    day: str,
    text: str,
    compares: list[dict[str, Any]],
    st_all: dict[str, Any],
    st_daily: dict[str, Any],
    source: str,
    evaluation: str = "",
) -> str:
    """reports/*.md 用（Markdown表を正とする）。"""
    blocks = [
        f"# 615 USD/JPY — {day}",
        "",
        f"**終値** {st_all.get('last', 0):.2f} 円（{st_all.get('last_date')}）／ソース: `{source}`",
        "",
        "## 比較（終値との差）",
        "",
        _table_markdown(compares),
        "",
        "## レンジ",
        "",
        "| 範囲 | 高値 | 安値 |",
        "|---|---|---|",
        f"| 取得期間 | {_fmt_px(st_all.get('high'))}（{st_all.get('high_date')}） | "
        f"{_fmt_px(st_all.get('low'))}（{st_all.get('low_date')}） |",
        f"| 直近31日（n={st_daily.get('n', 0)}） | {_fmt_px(st_daily.get('high'))} | "
        f"{_fmt_px(st_daily.get('low'))} |",
        "",
    ]
    if evaluation:
        blocks.extend(["## 見立て（売買指図なし）", "", evaluation, ""])
    blocks.extend(
        [
            "## Slack短報（控え）",
            "",
            "```",
            text,
            "```",
            "",
            f"![chart](charts/{day}_usdjpy.png)",
            "",
            "ダッシュボード: `/yen`",
            "",
        ]
    )
    return "\n".join(blocks)


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
    ap.add_argument("--apply", action="store_true", help="reports/state/Supabase に書き込む")
    ap.add_argument("--push", action="store_true", help="Slack #report へ投稿")
    ap.add_argument("--dry-run", action="store_true", help="取得・文章のみ（既定に近い）")
    ap.add_argument("--with-news", action="store_true", help="Tavily 短要約を付ける")
    ap.add_argument("--no-dashboard", action="store_true", help="Supabase /yen 投影をスキップ")
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
    compares = compare_windows(rows)
    day = _now().strftime("%Y-%m-%d")
    chart_path = CHARTS_DIR / f"{day}_usdjpy.png"
    chart_rel = str(chart_path.relative_to(REPO))

    news = _optional_news() if args.with_news else ""
    evaluation = build_evaluation(st_all=st_all, compares=compares, news=news)
    text = build_text(
        source=source,
        st_all=st_all,
        st_daily=st_daily,
        compares=compares,
        chart_rel=chart_rel,
        news=news,
        evaluation=evaluation,
    )
    print(text)
    if args.json:
        print(
            json.dumps(
                {
                    "source": source,
                    "all": st_all,
                    "daily": st_daily,
                    "compares": compares,
                    "evaluation": evaluation,
                    "n": len(rows),
                },
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
            build_report_md(
                day=day,
                text=text,
                compares=compares,
                st_all=st_all,
                st_daily=st_daily,
                source=source,
                evaluation=evaluation,
            ),
            encoding="utf-8",
        )
        print(f"📎 report: {md_path.relative_to(REPO)}")
        state.update(
            {
                "last_run_at": _now().isoformat(timespec="seconds"),
                "last_source": source,
                "last": st_all,
                "compares": compares,
                "evaluation": evaluation,
                "chart": chart_rel,
            }
        )
        _save_state(state)
        if args.apply and not args.no_dashboard:
            try:
                dash = push_dashboard(
                    rows=rows,
                    source=source,
                    st_all=st_all,
                    st_daily=st_daily,
                    compares=compares,
                    evaluation=evaluation,
                    news=news,
                    chart_rel=chart_rel,
                )
                if dash.get("ok"):
                    print(f"📎 dashboard: yen_rate_daily n={dash.get('n')} → /yen")
                else:
                    print(f"⚠️ dashboard skip: {dash.get('reason')}", file=sys.stderr)
            except Exception as e:
                print(f"⚠️ dashboard push failed: {e}", file=sys.stderr)
        if args.push:
            rc = _slack_post(text, channel="report")
            if rc != 0:
                return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
