#!/usr/bin/env python3
"""
Zaim 銀行・カード連携の鮮度チェック（Phase1: 特定＋手動更新プレイブック）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_zaim_bank_sync_check.py
  python scripts/jarvis_zaim_bank_sync_check.py --year 2026
  python scripts/jarvis_zaim_bank_sync_check.py --mark-prompted   # 金曜促し記録
  python scripts/jarvis_zaim_bank_sync_check.py --status

CSV の支払元/入金先の最終日付と、CSV 全体の最新日の差で「止まっていそう」を検知。
さらに Zaim 連携設定ページの「最終更新」とエラー表示（jarvis_zaim_online_accounts.py が週2回
取得したスナップショット）も見て、取引がなくても連携が生きていれば遅れ扱いにしない。
更新日時が確かめられないときは従来の CSV 判定に戻し、その旨を表示する（安全側）。
値（パスワード等）は出力しない。env_hint の変数名のみ示す。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_zaim_online_accounts as zonline  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
CFG_PATH = REPO / "config" / "zaim_bank_sync_watch.yaml"
OUT_PATH = REPO / ".jarvis_state" / "zaim_bank_sync.json"
EXAMPLE_PATH = REPO / ".jarvis_state" / "zaim_bank_sync.example.json"


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def load_cfg() -> dict[str, Any]:
    return yaml.safe_load(CFG_PATH.read_text(encoding="utf-8")) or {}


def resolve_csv(cfg: dict[str, Any], year: int) -> Path:
    base = Path(os.environ.get("ZAIM_CSV_BASE_DIR") or cfg.get("csv_base_dir") or "").expanduser()
    return base / f"{year}年度" / f"Zaim.{year}年度.csv"


def parse_d(s: str) -> date | None:
    s = (s or "").strip()[:10]
    if len(s) < 10:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def scan_csv(path: Path) -> tuple[date | None, dict[str, dict[str, Any]]]:
    """source_name -> {last, count, as_pay, as_deposit}"""
    sources: dict[str, dict[str, Any]] = {}
    csv_max: date | None = None
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            d = parse_d(row.get("日付") or "")
            if d and (csv_max is None or d > csv_max):
                csv_max = d
            for col, flag in (("支払元", "as_pay"), ("入金先", "as_deposit")):
                name = (row.get(col) or "").strip()
                if not name or name == "-":
                    continue
                bucket = sources.setdefault(
                    name,
                    {"last": None, "count": 0, "as_pay": 0, "as_deposit": 0},
                )
                bucket["count"] += 1
                bucket[flag] += 1
                if d and (bucket["last"] is None or d > bucket["last"]):
                    bucket["last"] = d
    return csv_max, sources


def match_account(
    acc: dict[str, Any], sources: dict[str, dict[str, Any]]
) -> tuple[str | None, dict[str, Any] | None]:
    needle = str(acc.get("match") or "")
    if not needle:
        return None, None
    hits = [(n, info) for n, info in sources.items() if needle in n]
    if not hits:
        return None, None
    # 最も新しい最終日の名前を採用
    hits.sort(key=lambda x: x[1].get("last") or date.min, reverse=True)
    return hits[0][0], hits[0][1]


def env_present(names: list[str]) -> list[str]:
    ok = []
    for n in names:
        if (os.environ.get(n) or "").strip():
            ok.append(n)
    return ok


def parse_iso(s: Any) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(s).replace("+0900", "+09:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=JST)


# sync_state（連携の状態）。stale / ok の判定とは別に持つ印。
SYNC_ALIVE = "alive"  # 更新日時が閾値内・エラー表示なし
SYNC_ALIVE_NO_TXN = "alive_no_txn"  # 上に加え、CSV の最終取引が古い（取引がないだけ）
SYNC_NEEDS_REAUTH = "needs_reauth"  # Zaim が再ログイン要・連携できないを表示
SYNC_ERROR = "sync_error"  # Zaim がエラー表示（再ログイン以外）
SYNC_STOPPED = "sync_stopped"  # 更新日時が閾値より古い
SYNC_UNVERIFIED = "unverified"  # 更新日時を確かめられなかった（従来の CSV 判定のまま）

OnlineInfo = tuple[list[dict[str, Any]], "datetime | None", dict[str, Any]]


def judge_sync(
    csv_stale: bool,
    online_row: dict[str, Any] | None,
    thresh_days: int,
    fetched_at: datetime | None,
) -> tuple[bool, str, dict[str, Any]]:
    """(stale か, sync_state, 追加情報)。

    (a) 更新日時が閾値内かつエラー表示なし → 取引が古くても stale にしない
    (b) 更新日時が古い／エラー表示あり → stale（要再認証は needs_reauth）
    (c) 更新日時が取れない → 従来の CSV 判定に戻す（unverified）
    """
    if not online_row or fetched_at is None:
        return csv_stale, SYNC_UNVERIFIED, {}
    updated = parse_iso(online_row.get("last_updated"))
    if updated is None:
        return csv_stale, SYNC_UNVERIFIED, {}
    age = max(0.0, (fetched_at - updated).total_seconds() / 86400)
    extra: dict[str, Any] = {
        "zaim_updated_at": online_row.get("last_updated"),
        "zaim_update_age_days": round(age, 1),
        "zaim_group": online_row.get("group"),
    }
    if zonline.has_zaim_error(online_row):
        extra["zaim_notice"] = (online_row.get("notice") or "")[:60] or None
        reauth = (
            zonline.is_reauth_notice(online_row.get("notice"))
            or bool(online_row.get("link_broken"))
            or online_row.get("group") == "更新再開の操作待ち"
        )
        return True, (SYNC_NEEDS_REAUTH if reauth else SYNC_ERROR), extra
    if age >= thresh_days:
        return True, SYNC_STOPPED, extra
    return False, (SYNC_ALIVE_NO_TXN if csv_stale else SYNC_ALIVE), extra


def load_online(cfg: dict[str, Any]) -> OnlineInfo:
    """Zaim 口座一覧のスナップショット。使えないときは ([], None, {status, reason})。"""
    conf = cfg.get("online_status") or {}
    if conf.get("enabled") is False or os.environ.get("JARVIS_ZAIM_ONLINE_STATUS_DISABLE") == "1":
        return [], None, {"status": "disabled", "reason": "設定でオフ"}
    snap = zonline.load_snapshot()
    ok, why = zonline.snapshot_usable(
        snap, max_age_days=float(conf.get("snapshot_max_age_days") or 5)
    )
    if not ok:
        return [], None, {"status": "unavailable", "reason": why, "last_failed": snap.get("last_failed")}
    return (
        list(snap.get("accounts") or []),
        parse_iso(snap.get("fetched_at")),
        {"status": "ok", "fetched_at": snap.get("fetched_at")},
    )


def evaluate(
    cfg: dict[str, Any], year: int, online: OnlineInfo | None = None
) -> dict[str, Any]:
    path = resolve_csv(cfg, year)
    if not path.is_file():
        return {
            "updated_at": now_iso(),
            "year": year,
            "csv": str(path),
            "level": "warn",
            "summary": f"CSV なし: {path.name}",
            "detail": "zaim_csv_weekly_runner.sh で CSV を取ってから再実行",
            "stale": [],
            "missing": [],
            "ok": [],
            "unlinkable": [],
            "phase1_steps": [],
        }

    csv_max, sources = scan_csv(path)
    default_days = int(cfg.get("default_stale_days") or 12)
    online_accounts, online_fetched, online_info = (
        online if online is not None else load_online(cfg)
    )
    alive_no_txn: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    ok_list: list[dict[str, Any]] = []
    unlinkable: list[dict[str, Any]] = []

    for acc in cfg.get("accounts") or []:
        aid = str(acc.get("id") or "")
        label = str(acc.get("label") or aid)
        note = str(acc.get("note") or "")
        hints = list(acc.get("env_hint") or [])
        hints_ok = env_present(hints)
        row: dict[str, Any] = {
            "id": aid,
            "label": label,
            "match": acc.get("match"),
            "note": note,
            "env_hint": hints,
            "env_hint_ready": hints_ok,
            "env_hint_missing": [h for h in hints if h not in hints_ok],
        }
        if acc.get("unlinkable"):
            row["status"] = "unlinkable"
            unlinkable.append(row)
            continue

        name, info = match_account(acc, sources)
        if not info or not name:
            row["status"] = "missing"
            row["csv_name"] = None
            row["last"] = None
            row["lag_days"] = None
            missing.append(row)
            continue

        last: date | None = info.get("last")
        lag = (csv_max - last).days if csv_max and last else None
        thresh = int(acc.get("stale_days") or default_days)
        row.update(
            {
                "csv_name": name,
                "last": last.isoformat() if last else None,
                "count": info.get("count"),
                "lag_days": lag,
                "stale_days_threshold": thresh,
            }
        )
        csv_stale = lag is not None and lag >= thresh
        needles = acc.get("online_match") or acc.get("match")
        online_row = zonline.match_online_account(needles, online_accounts)
        is_stale, sync_state, extra = judge_sync(csv_stale, online_row, thresh, online_fetched)
        row["sync_state"] = sync_state
        row["online_checked"] = sync_state != SYNC_UNVERIFIED
        row.update(extra)
        if is_stale:
            row["status"] = "stale"
            stale.append(row)
        else:
            row["status"] = "ok"
            ok_list.append(row)
            if sync_state == SYNC_ALIVE_NO_TXN:
                alive_no_txn.append(row)

    for note in cfg.get("unlinkable_notes") or []:
        unlinkable.append(
            {
                "id": "note",
                "label": str(note),
                "status": "unlinkable",
                "note": str(note),
                "env_hint": [],
                "env_hint_ready": [],
                "env_hint_missing": [],
            }
        )

    level = "ok"
    if missing or stale:
        level = "attention"
    if not ok_list and (missing or stale):
        level = "warn"

    unverified = [
        r for r in ok_list + stale if r.get("sync_state") == SYNC_UNVERIFIED
    ]
    lines: list[str] = []
    if stale:
        lines.append("■ 連携が止まっていそう")
        for s in stale:
            state = s.get("sync_state")
            if state == SYNC_NEEDS_REAUTH:
                why = f"Zaim が再ログイン要・連携不可を表示（最終更新 {s.get('zaim_update_age_days')}日前）"
            elif state == SYNC_ERROR:
                why = f"Zaim がエラーを表示（最終更新 {s.get('zaim_update_age_days')}日前）"
            elif state == SYNC_STOPPED:
                why = (
                    f"Zaim の最終更新が {s.get('zaim_update_age_days')}日前"
                    f"（閾値{s.get('stale_days_threshold')}日）"
                )
            else:
                why = (
                    f"CSV最終 {s.get('last') or '—'}（{s.get('lag_days')}日遅れ・閾値{s.get('stale_days_threshold')}日）"
                    "／Zaim の更新日時は確かめられなかった"
                )
            lines.append(f"- {s['label']}: {why}" + (f" / {s['note']}" if s.get("note") else ""))
    if alive_no_txn:
        lines.append("■ 取引がないだけ・連携は生きている（Zaim の更新日時は閾値内）")
        for s in alive_no_txn:
            lines.append(
                f"- {s['label']}: 最終取引 {s.get('last') or '—'}／Zaim 最終更新 {s.get('zaim_update_age_days')}日前"
            )
    if online_info.get("status") != "ok":
        lines.append(
            "■ Zaim の更新日時は確かめられなかった"
            f"（{online_info.get('reason') or online_info.get('status')}）→ CSV の最終日だけで判定"
        )
    elif unverified:
        lines.append("■ 次の口座は Zaim 画面で見つからず、更新日時は確かめられなかった（CSV の最終日だけで判定）")
        for s in unverified:
            lines.append(f"- {s['label']}")
    if missing:
        lines.append("■ CSV に見当たらない（未連携 or 名称変更）")
        for s in missing:
            lines.append(f"- {s['label']}（match={s.get('match')}）")
    if unlinkable:
        lines.append("■ 事情により連携できない／既知スキップ")
        for s in unlinkable:
            lines.append(f"- {s.get('label') or s.get('note')}")

    phase1: list[str] = [
        "1. Zaim Web にログイン（ZAIM_LOGIN_EMAIL / ZAIM_PASSWORD）",
        f"2. 口座一覧（連携設定）を開く: {cfg.get('zaim_accounts_url') or 'https://zaim.net/online_accounts'}",
        "3. 上の『止まっていそう』口座ごとに『連携設定』→『連携データを更新』（または jarvis_zaim_bank_sync_manual.py）",
        "4. OTP・追加認証が出たら Jarvis に『回答して』→ .env.jarvis_private の env_hint を使う（値はチャットに貼らない）",
        "5. 更新後: launchd/zaim_csv_weekly_runner.sh または zaim_csv_export で CSV 再取得 → 本スクリプト再実行で lag 解消を確認",
        "6. Phase2: 手順が安定したら Playwright 定期実行へ（未実装）",
    ]
    if stale or missing:
        phase1.insert(
            3,
            "対象: "
            + "、".join(
                [s["label"] for s in stale[:8]] + [s["label"] for s in missing[:4]]
            ),
        )

    summary_parts = []
    if stale:
        summary_parts.append(f"連携遅れ {len(stale)}件")
    if alive_no_txn:
        summary_parts.append(f"取引なし・連携OK {len(alive_no_txn)}件")
    if online_info.get("status") != "ok":
        summary_parts.append("更新日時は確認できず（CSVのみで判定）")
    elif unverified:
        summary_parts.append(f"更新日時未確認 {len(unverified)}件")
    if missing:
        summary_parts.append(f"未検出 {len(missing)}件")
    if unlinkable:
        summary_parts.append(f"連携不可(既知) {len(unlinkable)}件")
    if not summary_parts:
        summary_parts.append(f"監視口座 OK（{len(ok_list)}件）")
    summary_parts.append(f"CSV最新 {csv_max.isoformat() if csv_max else '—'}")

    return {
        "updated_at": now_iso(),
        "year": year,
        "csv": str(path),
        "csv_max_date": csv_max.isoformat() if csv_max else None,
        "level": level,
        "summary": " · ".join(summary_parts),
        "detail": "\n".join(lines) if lines else "監視対象の銀行・カードは鮮度 OK",
        "stale": stale,
        "missing": missing,
        "ok": ok_list,
        "alive_no_txn": alive_no_txn,
        "unlinkable": unlinkable,
        "online_check": {
            **{k: v for k, v in online_info.items() if k != "last_failed"},
            "last_failed": online_info.get("last_failed"),
            "unverified_n": len(unverified),
        },
        "phase1_steps": phase1,
        "zaim_accounts_url": cfg.get("zaim_accounts_url"),
    }


def load_state() -> dict[str, Any]:
    if OUT_PATH.is_file():
        return json.loads(OUT_PATH.read_text(encoding="utf-8"))
    return {}


def save_result(result: dict[str, Any], *, merge_prompt: dict[str, Any] | None = None) -> None:
    prev = load_state()
    out = dict(result)
    if merge_prompt:
        out.update(merge_prompt)
    else:
        for k in ("last_prompted_at", "last_check_friday"):
            if k in prev:
                out[k] = prev[k]
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not EXAMPLE_PATH.is_file():
        EXAMPLE_PATH.write_text(
            json.dumps(
                {
                    "disabled": False,
                    "note": "runner / jarvis_zaim_bank_sync_check.py が更新。秘密は書かない",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def format_block(result: dict[str, Any]) -> str:
    lines = [
        "📎 Zaim銀行連携（週次・金曜）",
        f"- 判定: {result.get('summary')}",
        f"- level: {result.get('level')}",
    ]
    if result.get("detail"):
        for ln in str(result["detail"]).splitlines()[:28]:
            lines.append(f"  {ln}")
    lines.append("- Phase1 次の一手:")
    for s in (result.get("phase1_steps") or [])[:8]:
        lines.append(f"  · {s}")
    return "\n".join(lines)


def should_prompt_friday(cfg: dict[str, Any], state: dict[str, Any]) -> bool:
    if state.get("disabled") or os.environ.get("JARVIS_ZAIM_BANK_SYNC_DISABLE") == "1":
        return False
    today = datetime.now(JST).date()
    # Friday = 4 in Python weekday() if Mon=0... wait: Monday=0, Friday=5
    want = int(cfg.get("friday_weekday", 5))
    if today.weekday() != want:
        return False
    last = state.get("last_prompted_at") or state.get("last_check_friday")
    if last:
        try:
            dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=JST)
            age = (datetime.now(JST) - dt.astimezone(JST)).days
            if age < int(cfg.get("prompt_interval_days") or 6):
                return False
        except ValueError:
            pass
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=datetime.now(JST).year)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--mark-prompted", action="store_true")
    ap.add_argument("--force-prompt", action="store_true", help="金曜以外でもブロック出力")
    args = ap.parse_args(argv)

    cfg = load_cfg()
    result = evaluate(cfg, args.year)
    save_result(result)

    if args.status:
        print(json.dumps(load_state(), ensure_ascii=False, indent=2))
        return 0

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    state = load_state()
    show = args.force_prompt or args.mark_prompted or should_prompt_friday(cfg, state)
    # 常に stderr に要約、ブロックは金曜 or force
    print(f"# wrote {OUT_PATH} level={result.get('level')} {result.get('summary')}", file=sys.stderr)
    if show or result.get("level") in ("attention", "warn"):
        if args.mark_prompted or should_prompt_friday(cfg, state) or args.force_prompt:
            save_result(
                result,
                merge_prompt={
                    "last_prompted_at": now_iso(),
                    "last_check_friday": date.today().isoformat(),
                },
            )
        print(format_block(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
