#!/usr/bin/env python3
"""614 ポイント・還元ウォッチ係 — 年間特典ウォッチ（Olive Infinite / Marriott Bonvoy の2枚だけ）。

2枚のカードの年間特典が「届くペースか」を見て、今月どちらに支払いを寄せるかの判断材料を出す。
決めるのは松野さん。ここは材料を出すだけ（支払い操作・送金はしない）。

  条件の線   config/card_benefit_watch.yaml（公式確認の度合いを threshold_status で持つ）
  実額       .jarvis_state/card_benefit_watch.json（gitignore 済み。リポジトリには置かない）
             JARVIS_STATE_DIR で別の state フォルダを指せる（worktree から Mac の state を読む時）

  # 画面・Slack 用の計算結果を表示（ネットワークなし。state だけで再計算）
  python scripts/jarvis_card_benefit_watch.py --show [--mask]
  # Olive: Gmail 月次メール『各種特典条件達成状況』（三井住友カード）を orca gmail で読んで確定値を state へ
  python scripts/jarvis_card_benefit_watch.py --fetch-olive
  # Bonvoy: Zaim 取込行（.jarvis_state/zaim_learn_csv_index.json）から概算を集計して state へ
  python scripts/jarvis_card_benefit_watch.py --refresh-bonvoy
  # 両方
  python scripts/jarvis_card_benefit_watch.py --refresh

確定値（メール由来）と概算（Zaim 由来）は区別して持つ。Zaim は取込日ベースで、
アメックスの画面の数字とずれる。基準日と「概算」を必ず付ける。
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO / "config" / "card_benefit_watch.yaml"
DAYS_PER_MONTH = 30.4375

STATUS_LABEL = {
    "confirmed": "確認済み",
    "estimated": "推定",
    "needs_check": "要確認",
    "unknown": "未確認",
}
VERDICT_REACH = "届く"
VERDICT_TIGHT = "厳しい"
VERDICT_FAR = "届かない見込み"
VERDICT_DONE = "達成"
VERDICT_MISSED = "未達（期間終了）"
VERDICT_NODATA = "データなし"


def state_dir() -> Path:
    env = (os.environ.get("JARVIS_STATE_DIR") or "").strip()
    return Path(env).expanduser() if env else REPO / ".jarvis_state"


def state_path() -> Path:
    return state_dir() / "card_benefit_watch.json"


def zaim_index_path() -> Path:
    return state_dir() / "zaim_learn_csv_index.json"


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_state(path: Path | None = None) -> dict[str, Any]:
    p = path or state_path()
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(data: dict[str, Any], path: Path | None = None) -> Path:
    p = path or state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(JST).isoformat(timespec="seconds")
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------- 期間

def _d(s: str) -> date:
    return date.fromisoformat(s)


def period_for(card_cfg: dict[str, Any], today: date) -> tuple[date, date]:
    per = card_cfg.get("period") or {}
    if per.get("type") == "fixed":
        return _d(str(per["start"])), _d(str(per["end"]))
    # annual_from: 毎年 month/day 起点の1年
    m, dd = int(per["month"]), int(per["day"])
    y = today.year if (today.month, today.day) >= (m, dd) else today.year - 1
    start = date(y, m, dd)
    end = date(y + 1, m, dd) - timedelta(days=1)
    return start, end


# ---------------------------------------------------------------- 実額の取り込み

_RE_ASOF = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日現在")
_RE_YEN = re.compile(r"([\d,]+)円（税込）")


def parse_olive_mail(body: str) -> tuple[str, int] | None:
    """三井住友カードの月次メール本文から (基準日, 利用額) を取る。取れなければ None。"""
    m = _RE_ASOF.search(body or "")
    y = _RE_YEN.search(body or "")
    if not m or not y:
        return None
    as_of = date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    return as_of, int(y.group(1).replace(",", ""))


def _orca_json(args: list[str], timeout: int = 60) -> dict[str, Any] | None:
    try:
        proc = subprocess.run(
            ["orca", "gmail", *args, "--json"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return json.loads(proc.stdout) if proc.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None


def fetch_olive(state: dict[str, Any], *, newer_than_days: int = 200) -> tuple[int, str]:
    """Gmail の月次メールから Olive の確定値を state へ追加。返り値=(追加件数, メモ)。"""
    acct = (os.environ.get("CARD_BENEFIT_GMAIL_ACCOUNT") or "").strip()
    extra = ["--account", acct] if acct else []
    q = f"subject:各種特典条件達成状況 subject:Olive from:vpass.ne.jp newer_than:{newer_than_days}d"
    res = _orca_json(["search", q, "--limit", "20", *extra])
    if not res or not res.get("ok"):
        return 0, "Gmail 検索に失敗（orca gmail／アカウント連携を確認）"
    threads = (res.get("result") or {}).get("threads") or []
    snaps = state.setdefault("olive", {}).setdefault("snapshots", [])
    have = {s.get("as_of") for s in snaps}
    added = 0
    for t in threads:
        ref = t.get("ref")
        if not ref:
            continue
        rd = _orca_json(["read", ref, *extra])
        msgs = ((rd or {}).get("result") or {}).get("messages") or []
        for msg in msgs:
            parsed = parse_olive_mail(msg.get("body") or "")
            if not parsed or parsed[0] in have:
                continue
            snaps.append(
                {"as_of": parsed[0], "usage_yen": parsed[1], "source": "gmail", "ref": ref}
            )
            have.add(parsed[0])
            added += 1
    snaps.sort(key=lambda s: s.get("as_of") or "")
    return added, f"メール {len(threads)} 通を確認・新規 {added} 件"


def aggregate_zaim(
    index: dict[str, Any], card_cfg: dict[str, Any], period: tuple[date, date]
) -> dict[str, Any] | None:
    """Zaim 取込行から期間内の概算利用額。該当行なしなら None。"""
    rows = index.get("rows") if isinstance(index.get("rows"), dict) else {}
    needle = str(card_cfg.get("zaim_pay_contains") or "").upper()
    excl = [str(k) for k in (card_cfg.get("zaim_exclude_keywords") or [])]
    if not needle:
        return None
    total, n, last = 0, 0, ""
    for r in rows.values():
        if not isinstance(r, dict) or needle not in str(r.get("pay") or "").upper():
            continue
        ds = str(r.get("date") or "")
        try:
            dd = _d(ds)
        except ValueError:
            continue
        if not (period[0] <= dd <= period[1]):
            continue
        text = f"{r.get('shop') or ''}{r.get('item') or ''}"
        if any(k in text for k in excl):
            continue
        total += int(r.get("amount") or 0)
        n += 1
        last = max(last, ds)
    if n == 0:
        return None
    return {
        "usage_yen": total,
        "rows": n,
        "as_of": last,
        "index_updated_at": index.get("updated_at"),
    }


def aggregate_zaim_transfers(
    csv_path: Path, card_cfg: dict[str, Any], period: tuple[date, date]
) -> dict[str, Any]:
    """Zaim CSV の transfer 行のうち、支払元がカード・入金先が設定キーワードのもの（例: Amazon 購入）。

    インデックス（zaim_learn 用）は payment 行だけなので、CSV を直接読む。
    カード引落（銀行→カード）と balance 行は支払元/方法が違うので入らない。"""
    needle = str(card_cfg.get("zaim_pay_contains") or "").upper()
    kws = [str(k) for k in (card_cfg.get("zaim_transfer_to_include") or []) if str(k)]
    excl = [str(k) for k in (card_cfg.get("zaim_exclude_keywords") or [])]
    out = {"usage_yen": 0, "rows": 0, "as_of": ""}
    if not needle or not kws or not csv_path.is_file():
        return out
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if (r.get("方法") or "") != "transfer":
                continue
            if needle not in str(r.get("支払元") or "").upper():
                continue
            if not any(k in str(r.get("入金先") or "") for k in kws):
                continue
            ds = str(r.get("日付") or "")[:10].replace("/", "-")
            try:
                dd = _d(ds)
            except ValueError:
                continue
            if not (period[0] <= dd <= period[1]):
                continue
            text = f"{r.get('お店') or ''}{r.get('品目') or ''}"
            if any(k in text for k in excl):
                continue
            try:
                amt = int(round(float(r.get("振替") or 0)))
            except ValueError:
                continue
            if amt <= 0:
                continue
            out["usage_yen"] += amt
            out["rows"] += 1
            out["as_of"] = max(out["as_of"], ds)
    return out


def refresh_bonvoy(state: dict[str, Any], cfg: dict[str, Any], today: date) -> str:
    p = zaim_index_path()
    if not p.is_file():
        return "Zaim 取込 index が見つからない"
    try:
        index = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "Zaim 取込 index を読めない"
    card_cfg = cfg["cards"]["bonvoy"]
    period = period_for(card_cfg, today)
    agg = aggregate_zaim(index, card_cfg, period)
    csv_p = str(index.get("csv") or "")
    if csv_p and card_cfg.get("zaim_transfer_to_include"):
        try:
            tr = aggregate_zaim_transfers(Path(csv_p).expanduser(), card_cfg, period)
        except (OSError, csv.Error):
            tr = {"rows": 0}
        if tr["rows"]:
            if agg is None:
                agg = {"usage_yen": 0, "rows": 0, "as_of": "", "index_updated_at": index.get("updated_at")}
            agg["usage_yen"] += tr["usage_yen"]
            agg["rows"] += tr["rows"]
            agg["as_of"] = max(agg["as_of"], tr["as_of"])
            agg["transfer_rows"] = tr["rows"]
    if agg is None:
        return "期間内の該当行なし"
    agg["computed_at"] = datetime.now(JST).isoformat(timespec="seconds")
    state.setdefault("bonvoy", {})["zaim"] = agg
    return f"Zaim 該当 {agg['rows']} 行（基準日 {agg['as_of']}）"


# ---------------------------------------------------------------- 計算

def _latest_usage(card_cfg: dict[str, Any], state: dict[str, Any]) -> dict[str, Any] | None:
    """{usage_yen, as_of, kind(confirmed|estimate), source_label}"""
    if card_cfg.get("usage_source") == "gmail_monthly":
        snaps = [
            s for s in (state.get("olive") or {}).get("snapshots") or []
            if isinstance(s, dict) and s.get("usage_yen") is not None and s.get("as_of")
        ]
        if not snaps:
            return None
        s = max(snaps, key=lambda x: x["as_of"])
        return {
            "usage_yen": int(s["usage_yen"]),
            "as_of": s["as_of"],
            "kind": "confirmed",
            "source_label": "三井住友カードの月次メール（確定値）",
        }
    z = (state.get("bonvoy") or {}).get("zaim")
    if isinstance(z, dict) and z.get("usage_yen") is not None and z.get("as_of"):
        return {
            "usage_yen": int(z["usage_yen"]),
            "as_of": z["as_of"],
            "kind": "estimate",
            "source_label": "Zaim 取込行の概算",
        }
    return None


def _verdict(need_pm: float, pace_pm: float, pace_cfg: dict[str, Any]) -> str:
    reach = float(pace_cfg.get("reach_ratio", 1.0))
    tight = float(pace_cfg.get("tight_ratio", 1.5))
    if pace_pm <= 0:
        return VERDICT_FAR
    ratio = need_pm / pace_pm
    if ratio <= reach:
        return VERDICT_REACH
    if ratio <= tight:
        return VERDICT_TIGHT
    return VERDICT_FAR


def compute_card(
    card_id: str, cfg: dict[str, Any], state: dict[str, Any], today: date
) -> dict[str, Any]:
    c = cfg["cards"][card_id]
    start, end = period_for(c, today)
    days_left = max((end - today).days, 0)
    months_left = round(days_left / DAYS_PER_MONTH, 1)
    out: dict[str, Any] = {
        "id": card_id,
        "name": c.get("name"),
        "short": c.get("short") or c.get("name"),
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "days_left": days_left,
        "months_left": months_left,
        "counts_note": c.get("counts_note"),
        "grant_note": c.get("grant_note"),
        "usage_yen": None,
        "usage_as_of": None,
        "usage_kind": None,
        "usage_source": None,
        "usage_stale_days": None,
        "pace_per_month_yen": None,
        "tiers": [],
    }
    usage = _latest_usage(c, state)
    if usage is None:
        out["note"] = "実額がまだ state にありません（--fetch-olive / --refresh-bonvoy）"
        for t in c.get("tiers") or []:
            out["tiers"].append(_tier_base(t) | {"verdict": VERDICT_NODATA})
        return out
    as_of = _d(usage["as_of"])
    elapsed_months = max((as_of - start).days / DAYS_PER_MONTH, 1.0)
    pace = usage["usage_yen"] / elapsed_months
    out.update(
        usage_yen=usage["usage_yen"],
        usage_as_of=usage["as_of"],
        usage_kind=usage["kind"],
        usage_source=usage["source_label"],
        usage_stale_days=(today - as_of).days,
        pace_per_month_yen=int(pace),
    )
    if usage["kind"] == "estimate":
        out["usage_caveat"] = str(cfg.get("zaim_note") or "概算")
        out["usage_stale"] = (today - as_of).days > int(cfg.get("zaim_stale_days", 10))
    else:
        out["usage_stale"] = (today - as_of).days > int(c.get("stale_days", 45))
    for t in c.get("tiers") or []:
        thr = int(t["threshold_yen"])
        remaining = max(thr - usage["usage_yen"], 0)
        row = _tier_base(t)
        row.update(
            achieved_pct=round(usage["usage_yen"] * 100 / thr, 1) if thr else None,
            remaining_yen=remaining,
        )
        if remaining == 0:
            row.update(need_per_month_yen=0, verdict=VERDICT_DONE)
        elif days_left == 0:
            row.update(need_per_month_yen=None, verdict=VERDICT_MISSED)
        else:
            need_pm = remaining / max(days_left / DAYS_PER_MONTH, 1.0)
            row.update(
                need_per_month_yen=int(math.ceil(need_pm)),
                verdict=_verdict(need_pm, pace, cfg.get("pace") or {}),
            )
        out["tiers"].append(row)
    return out


def _tier_base(t: dict[str, Any]) -> dict[str, Any]:
    st = str(t.get("threshold_status") or "unknown")
    return {
        "id": t.get("id"),
        "label": t.get("label"),
        "threshold_yen": int(t["threshold_yen"]),
        "reward": t.get("reward"),
        "threshold_status": st,
        "threshold_status_label": STATUS_LABEL.get(st, "未確認"),
        "source_note": t.get("source_note"),
    }


def _first_open_tier(card: dict[str, Any]) -> dict[str, Any] | None:
    for t in card.get("tiers") or []:
        if t.get("verdict") not in (VERDICT_DONE, VERDICT_NODATA, VERDICT_MISSED):
            return t
    return None


def recommend(cards: list[dict[str, Any]]) -> dict[str, Any]:
    """今月どちらを使うか（判断材料）。決めるのは松野さん。

    各カードの「次に狙う未達の線」のうち、届く＞厳しいを候補にし、
    必要月額が小さい（＝いちばん手が届く）方を挙げる。どちらも届かない見込みなら
    寄せ先は満足度で決める材料として、そう書く。
    """
    rank = {VERDICT_REACH: 0, VERDICT_TIGHT: 1}
    cands: list[tuple[int, int, dict[str, Any], dict[str, Any]]] = []
    for c in cards:
        t = _first_open_tier(c)
        if t and t.get("verdict") in rank:
            cands.append((rank[t["verdict"]], int(t.get("need_per_month_yen") or 0), c, t))
    if not cands:
        if all(c.get("usage_yen") is None for c in cards):
            return {"card": None, "line": "実額が未取得のため今月の寄せ先は出せません"}
        return {
            "card": None,
            "line": "どちらも届かない見込み。寄せ先は特典への満足度で決める材料にしてください",
        }
    cands.sort(key=lambda x: (x[0], x[1]))
    _, _, c, t = cands[0]
    return {
        "card": c["id"],
        "short": c["short"],
        "tier": t["label"],
        "verdict": t["verdict"],
        "line": f"{c['short']}（{t['label']}を狙えるペース：{t['verdict']}）",
    }


EXIT_STATUS_LABEL = {"confirmed": "確認済み", "notice": "注意", "unconfirmed": "未確認"}


def build_olive_history(cfg: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """Olive 履歴: 達成済み（入会特典など）と これから（継続特典）を分ける。

    進呈済みの記録（pt・日付）は state の olive.grants（手書き・gitignore）にだけ置く。
    """
    olive = state.get("olive") if isinstance(state.get("olive"), dict) else {}
    achieved = [
        g for g in (olive.get("grants") or [])
        if isinstance(g, dict) and g.get("status") == "granted"
    ]
    achieved.sort(key=lambda g: str(g.get("granted_on") or ""))
    cont = (cfg.get("olive_history") or {}).get("continuous") or {}
    upcoming = {
        "label": cont.get("label"),
        "period_start": cont.get("period_start"),
        "period_end": cont.get("period_end"),
        "grant_timing": cont.get("grant_timing"),
        "mail_status": olive.get("continuous_mail_status"),
    }
    return {"achieved": achieved, "upcoming": upcoming}


def build_vpoint_exits(cfg: dict[str, Any]) -> dict[str, Any]:
    ex = cfg.get("vpoint_exits") or {}
    items = []
    for it in ex.get("items") or []:
        st = str(it.get("status") or "unconfirmed")
        items.append(
            {
                "label": it.get("label"),
                "status": st,
                "status_label": EXIT_STATUS_LABEL.get(st, "未確認"),
                "checked_on": it.get("checked_on"),
                "source": it.get("source"),
                "featured": bool(it.get("featured")),
                "note": it.get("note"),
                "extra_notes": [str(n) for n in (it.get("extra_notes") or [])],
            }
        )
    items.sort(key=lambda x: not x["featured"])  # 先頭＝最優先（投資）。同順位は設定順
    return {"items": items, "official_sources": ex.get("official_sources") or []}


def compute(cfg: dict[str, Any], state: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    today = today or datetime.now(JST).date()
    cards = [compute_card(cid, cfg, state, today) for cid in cfg["cards"]]
    return {
        "olive_history": build_olive_history(cfg, state),
        "vpoint_exits": build_vpoint_exits(cfg),
        "today": today.isoformat(),
        "computed_at": datetime.now(JST).isoformat(timespec="seconds"),
        "cards": cards,
        "recommendation": recommend(cards),
        "scope_note": "いまは Olive Infinite と Marriott Bonvoy の2枚だけを見る（汎用化しない）",
    }


def compute_from_files(today: date | None = None) -> dict[str, Any]:
    return compute(load_config(), load_state(), today)


# ---------------------------------------------------------------- 表示

def fmt_yen(n: int | None, mask: bool = False) -> str:
    if n is None:
        return "—"
    return "＊＊＊円" if mask else f"{n:,}円"


def fmt_man(n: int | None, mask: bool = False) -> str:
    """万円表示（Slack 用）。"""
    if n is None:
        return "—"
    if mask:
        return "＊＊万円"
    return f"{round(n / 10000):,}万円"


def render_text(result: dict[str, Any], *, mask: bool = False) -> str:
    lines: list[str] = []
    for c in result["cards"]:
        lines.append(f"■ {c['name']}（期間 {c['period_start']}〜{c['period_end']}／残り{c['days_left']}日）")
        if c.get("usage_yen") is None:
            lines.append(f"  {c.get('note') or 'データなし'}")
            continue
        kind = "確定値" if c["usage_kind"] == "confirmed" else "概算"
        lines.append(f"  利用額 {fmt_yen(c['usage_yen'], mask)}（{kind}・{c['usage_as_of']}時点・{c['usage_source']}）")
        for t in c["tiers"]:
            lines.append(
                f"  - {t['label']} {t['threshold_yen'] // 10000}万円［{t['threshold_status_label']}］"
                f" 達成{t.get('achieved_pct')}% あと{fmt_yen(t.get('remaining_yen'), mask)}"
                f" 月あたり{fmt_yen(t.get('need_per_month_yen'), mask)} → {t['verdict']}"
            )
    lines.append(f"おすすめ: {result['recommendation']['line']}")
    return "\n".join(lines)


def build_slack_text(result: dict[str, Any], *, header: str, dash_url: str, mask: bool = False) -> str:
    """iPhone 前提: 番号＋短い役割語、1項目2行以内、末尾に『今月はこちら』1行。"""
    lines = [header]
    for i, c in enumerate(result["cards"], 1):
        t = _first_open_tier(c)
        if c.get("usage_yen") is None:
            lines.append(f"{i}. {c['short']}: 実額まだ未取得")
            lines.append("   Gmail／Zaim の取込待ち")
            continue
        kind = "確定" if c["usage_kind"] == "confirmed" else "概算"
        md = c["usage_as_of"][5:].replace("-", "/").lstrip("0")
        if t is None:
            top = c["tiers"][-1] if c["tiers"] else {}
            lines.append(f"{i}. {c['short']}: 条件に届いた（{kind}・{md}時点）")
            lines.append(f"   {top.get('label', '')}まで達成")
            continue
        lines.append(
            f"{i}. {c['short']}: {t['label']} {t['achieved_pct']:.0f}%"
            f"（{kind}・{md}時点）"
        )
        lines.append(
            f"   あと{fmt_man(t['remaining_yen'], mask)}・月{fmt_man(t['need_per_month_yen'], mask)}"
            f"必要→{t['verdict']}"
        )
    # 概算元（Zaim）が古いときは必ず知らせる
    for c in result["cards"]:
        if not c.get("usage_stale"):
            continue
        d = c["usage_as_of"]
        md = f"{int(d[5:7])}/{int(d[8:])}"
        if c["usage_kind"] == "confirmed":
            lines.append(f"・{c['short']}は{md}現在の確定値（古い）")
            lines.append("  新しい月次メール待ち")
        else:
            lines.append(f"・Zaim が古い（基準日{md}）")
            lines.append(f"  取込が進むまで{c['short']}は目安")
    # 条件の確からしさ（ここを省かない）
    weak = sorted(
        {
            f"{c['short']}={t['threshold_status_label']}"
            for c in result["cards"]
            for t in c["tiers"]
            if t["threshold_status"] != "confirmed"
        }
    )
    if weak:
        lines.append(f"{len(result['cards']) + 1}. 条件の金額: " + " / ".join(weak))
        lines.append("   公式で確認できるまで目安扱い")
    lines.append(f"見る: {dash_url}")
    lines.append(f"今月はこちらを使うのがおすすめ: {result['recommendation']['line']}（判断はあなた）")
    return "\n".join(lines)


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", action="store_true", help="計算結果を表示（state だけで再計算）")
    ap.add_argument("--json", action="store_true", help="計算結果を JSON で表示")
    ap.add_argument("--mask", action="store_true", help="表示で金額を伏せる（ログ共有用）")
    ap.add_argument("--fetch-olive", action="store_true")
    ap.add_argument("--refresh-bonvoy", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="--fetch-olive と --refresh-bonvoy")
    args = ap.parse_args(argv)

    cfg = load_config()
    today = datetime.now(JST).date()
    if args.fetch_olive or args.refresh or args.refresh_bonvoy:
        st = load_state()
        if args.fetch_olive or args.refresh:
            _, note = fetch_olive(st)
            print(f"Olive: {note}")
        if args.refresh_bonvoy or args.refresh:
            print(f"Bonvoy: {refresh_bonvoy(st, cfg, today)}")
        p = save_state(st)
        print(f"state 更新: {p.name}")
    result = compute(cfg, load_state(), today)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.show or args.fetch_olive or args.refresh or args.refresh_bonvoy:
        print(render_text(result, mask=args.mask))
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
