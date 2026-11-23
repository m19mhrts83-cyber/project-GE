#!/usr/bin/env python3
"""
Zaim 重複（二重取込）を『集計に含めない』へ直す — 安全な2型だけ。

  型A: レシート内訳の合計＝同日・同額・一意のカード行 → カード行を除外（既存 Watch の both_include 判定を使う）
  型B: 同カード・同日・同額・同店のちょうど2行で、片方だけ品目/メモあり → 記述なし側を除外
  対象外: 3行以上／交通(高速・ETC)／スマートレシート同士／すでに除外済み／記述あり側が除外済み（ルールと逆向き）

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_zaim_dup_exclude.py                    # 既定 = --dry-run（候補と Zaim 上の行特定だけ。変更なし）
  python scripts/jarvis_zaim_dup_exclude.py --no-web           # CSV だけで候補を出す（Zaim を開かない）
  python scripts/jarvis_zaim_dup_exclude.py --apply --yes      # 実際に保存（1回の上限5件。マージ後、ラコの明示指示まで実行しない）
  python scripts/jarvis_zaim_dup_exclude.py --revert 12345678  # Zaim の明細IDで戻す（既定は dry-run。--apply --yes で実行）
  python scripts/jarvis_zaim_dup_exclude.py --revert-run dup-20261124-153000 --apply --yes

記録: .jarvis_state/zaim_dup_exclusions.json（非公開・gitignore 済み）。
Slack: --apply のときだけ。成功は #report、失敗3回（要手動）・ログイン不可は #ops に1回。--dry-run は投稿しない。
行の特定は『ちょうど1件』に絞れたときだけ（0件・複数件は何もしない）。保存後は日別を再読み込みし、
同じ明細IDの行の集計アイコンが変わったかで成功判定する（スクショだけで成功にしない）。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE = REPO / ".jarvis_state"
RECORD_PATH = STATE / "zaim_dup_exclusions.json"
SLACK_POST = REPO / "scripts" / "jarvis_slack_webhook_post.py"
LOG_DIR = Path.home() / "Library" / "Logs" / "jarvis_zaim"
PLAYWRIGHT_LOCK = LOG_DIR / "zaim_playwright.lock"
SYNC_DIR = REPO / "215_kamiooya" / "C1_cursor" / "finance" / "zaim_budget_sync"
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"
EXE = str(PY) if PY.is_file() else sys.executable

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(SYNC_DIR))
import jarvis_zaim_quality_check as qc  # noqa: E402
import zaim_row_match as zmatch  # noqa: E402

MAX_PER_RUN = 5  # 1回の上限（安全弁。引数でも超えられない）
MAX_ATTEMPTS = 3  # 失敗3回で要手動
DEFAULT_SCAN = 25  # 1回に Zaim 上で特定を試す候補数の上限
EXTRA_EXCLUDE_WORDS = ["交通"]  # 高速・ETC は設定の exclude_shop_keywords に加えて交通カテゴリも対象外

ST_EXCLUDED = "excluded"
ST_REVERTED = "reverted"
ST_FAILED = "failed"
ST_MANUAL = "manual_required"


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def new_run_id() -> str:
    return "dup-" + datetime.now(JST).strftime("%Y%m%d-%H%M%S")


# ---------------------------------------------------------------- 候補（CSV）
def _amt(r: dict[str, str]) -> int:
    return int(round(qc.yen(r)))


def has_description(r: dict[str, str]) -> bool:
    """品目またはメモがある（記述あり）。"""
    return bool(qc.nf(r.get("品目") or "") or qc.nf(r.get("メモ") or ""))


def cand_key(c: dict[str, Any]) -> str:
    return "|".join(
        [
            str(c["type"]),
            str(c["date"]),
            str(int(c["amount"])),
            str(c["pay"])[:40],
            qc.shop_key(str(c["shop"]))[:20],
        ]
    )


def _candidate(kind: str, r: dict[str, str]) -> dict[str, Any]:
    return {
        "type": kind,
        "date": r["日付"],
        "amount": _amt(r),
        "shop": r.get("お店") or "",
        "pay": r.get("支払元") or "",
        "item": r.get("品目") or "",
        "memo": r.get("メモ") or "",
    }


def type_a_candidates(
    payments: list[dict[str, str]], cfg: dict[str, Any]
) -> tuple[list[dict[str, Any]], set[tuple], Counter]:
    """型A。既存 find_pairs の both_include（レシート側・カード側とも『含める』）を使う。
    戻り値の2つ目は、レシート突合に出てきたカード行キー（型Bとの二重判定を避ける）。"""
    include = cfg.get("include_label") or qc.INCLUDE
    exclude = cfg.get("exclude_label") or qc.EXCLUDE
    skips: Counter = Counter()
    pair_keys: set[tuple] = set()
    out: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for p in qc.find_pairs(payments, cfg):
        act = p.get("action") or {}
        if act.get("target") != "card":
            continue
        rd, ce, pay40 = str(act.get("date")), int(round(float(act.get("amount") or 0))), str(act.get("pay") or "")
        pair_keys.add((rd, pay40, ce))
        if not p.get("both_include"):
            continue
        key = (rd, pay40, ce)
        if key in seen:
            continue
        seen.add(key)
        rows = [
            r
            for r in payments
            if r.get("日付") == rd and _amt(r) == ce and (r.get("支払元") or "")[:40] == pay40
        ]
        if len(rows) != 1:
            skips["A: カード行が一意でない"] += 1
            continue
        if qc.agg_label(rows[0], include, exclude) != "include":
            skips["A: カード行がすでに除外"] += 1
            continue
        out.append(_candidate("A", rows[0]))
    return out, pair_keys, skips


def type_b_candidates(
    payments: list[dict[str, str]], cfg: dict[str, Any], a_pair_keys: set[tuple]
) -> tuple[list[dict[str, Any]], Counter]:
    include = cfg.get("include_label") or qc.INCLUDE
    exclude = cfg.get("exclude_label") or qc.EXCLUDE
    card_kw = cfg.get("card_pay_keywords") or []
    excl_kw = list(cfg.get("exclude_shop_keywords") or []) + EXTRA_EXCLUDE_WORDS
    skips: Counter = Counter()
    groups: dict[tuple, list[dict[str, str]]] = defaultdict(list)
    for r in payments:
        pay = r.get("支払元") or ""
        if qc.is_smart(pay) or not qc.is_card(pay, card_kw):
            continue
        if qc.yen(r) <= 0:
            continue
        groups[(r.get("日付") or "", pay, _amt(r))].append(r)
    out: list[dict[str, Any]] = []
    for (d, pay, amt), rs in groups.items():
        if len(rs) < 2:
            continue
        if len(rs) >= 3:
            skips["B: 3行以上"] += 1
            continue
        if any(qc.is_excluded_shop(r.get("お店") or "", r.get("カテゴリ") or "", excl_kw) for r in rs):
            skips["B: 交通・高速"] += 1
            continue
        if qc.shop_key(rs[0].get("お店") or "") != qc.shop_key(rs[1].get("お店") or ""):
            skips["B: お店が違う"] += 1
            continue
        described = [r for r in rs if has_description(r)]
        if len(described) != 1:
            skips["B: 記述の有無で分かれない"] += 1
            continue
        desc_row = described[0]
        empty_row = rs[0] if rs[1] is desc_row else rs[1]
        da = qc.agg_label(desc_row, include, exclude)
        ea = qc.agg_label(empty_row, include, exclude)
        if ea == "exclude":
            skips["B: すでに除外済み"] += 1
            continue
        if da == "exclude":
            skips["B: 記述あり側が除外済み（逆向き）"] += 1
            continue
        if da != "include" or ea != "include":
            skips["B: 集計設定が不明"] += 1
            continue
        if (d, pay[:40], amt) in a_pair_keys:
            skips["B: レシート突合（型A）と重なる"] += 1
            continue
        out.append(_candidate("B", empty_row))
    return out, skips


def find_candidates(
    payments: list[dict[str, str]], cfg: dict[str, Any]
) -> tuple[list[dict[str, Any]], Counter]:
    a, a_keys, skip_a = type_a_candidates(payments, cfg)
    b, skip_b = type_b_candidates(payments, cfg, a_keys)
    cands = a + b
    cands.sort(key=lambda c: (c["date"], c["amount"]), reverse=True)  # 新しい日付から
    return cands, skip_a + skip_b


def web_action(c: dict[str, Any]) -> dict[str, Any]:
    """画面での特定に使う条件。型A=カード行が1件、型B=同額2行のうち記述なし側。"""
    return {
        "action": "set_aggregate",
        "value": "exclude",
        "target": "dup_exclude",
        "date": c["date"],
        "amount": c["amount"],
        "shop": c["shop"],
        "pay": c["pay"],
        "group_size": 1 if c["type"] == "A" else 2,
        "described": None if c["type"] == "A" else False,
    }


# ---------------------------------------------------------------- 記録
def load_record(path: Path = RECORD_PATH) -> dict[str, Any]:
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"updated_at": None, "entries": []}


def save_record(data: dict[str, Any], path: Path = RECORD_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = now_iso()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def entry_for(rec: dict[str, Any], key: str) -> dict[str, Any] | None:
    for e in rec.get("entries") or []:
        if e.get("cand_key") == key:
            return e
    return None


def classify_existing(e: dict[str, Any] | None, *, retry_manual: bool) -> str:
    """候補に対する過去の記録の扱い: new / retry / skip。"""
    if e is None:
        return "new"
    st = e.get("status")
    if st in (ST_EXCLUDED, ST_REVERTED):
        return "skip"  # 戻したものを勝手に再除外しない
    if st == ST_MANUAL and not retry_manual:
        return "skip"
    return "retry"


# ---------------------------------------------------------------- Slack
def build_report_text(entries: list[dict[str, Any]], run_id: str) -> str | None:
    ok = [e for e in entries if e.get("status") == ST_EXCLUDED]
    if not ok:
        return None
    a = sum(1 for e in ok if e.get("type") == "A")
    b = sum(1 for e in ok if e.get("type") == "B")
    total = sum(int(e.get("amount") or 0) for e in ok)
    return (
        f"【報告】613 Zaim重複除外｜重複除外 {len(ok)}件(型A {a}・型B {b})／計 ¥{total:,}／"
        f"戻すのは ラコへ「実行ID {run_id} を戻して」"
    )


def build_ops_text(manual: list[dict[str, Any]], run_id: str) -> str | None:
    if not manual:
        return None
    lines = [f"【要手動】613 Zaim重複除外｜{len(manual)}件が{MAX_ATTEMPTS}回失敗（実行ID {run_id}）", ""]
    for e in manual[:8]:
        lines.append(f"・{e.get('date')} ¥{int(e.get('amount') or 0):,} 型{e.get('type')}: {str(e.get('last_message') or '')[:60]}")
    lines += ["", "Zaim で手で『集計に含めない』にするか、ラコへ相談してください。"]
    return "\n".join(lines)


def post_slack(channel: str, text: str, *, username: str = "613 Zaim重複除外") -> int:
    if not SLACK_POST.is_file():
        print(f"# missing {SLACK_POST}", file=sys.stderr)
        return 2
    r = subprocess.run(
        [EXE, str(SLACK_POST), "--channel", channel, "--text", text, "--username", username],
        cwd=str(REPO),
        timeout=60,
    )
    print(f"# slack #{channel} rc={r.returncode}", flush=True)
    return int(r.returncode)


# ---------------------------------------------------------------- 共有ロック
def acquire_lock(*, wait_sec: int = 180) -> bool:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + wait_sec
    while True:
        try:
            os.mkdir(PLAYWRIGHT_LOCK)
            (PLAYWRIGHT_LOCK / "owner.txt").write_text(
                f"dup_exclude pid={os.getpid()} at={now_iso()}\n", encoding="utf-8"
            )
            return True
        except FileExistsError:
            if time.time() >= deadline:
                return False
            time.sleep(2)


def release_lock() -> None:
    try:
        for p in PLAYWRIGHT_LOCK.iterdir():
            p.unlink(missing_ok=True)
        PLAYWRIGHT_LOCK.rmdir()
    except Exception:
        pass


# ---------------------------------------------------------------- 画面（Zaim Web）
def _import_edit():
    import zaim_money_edit as zedit  # Playwright が必要なので遅延 import

    return zedit


def try_exclude(zedit, page, c: dict[str, Any], prior: dict[str, Any] | None, *, apply: bool) -> dict[str, Any]:
    """
    1候補の特定（と apply なら除外）。戻り値: {state, message, zaim_id, prev_agg, verified}
      state: identified(dry-run で特定のみ)/unmatched(絞れず・何もしない)/excluded/failed
    """
    action = web_action(c)
    day, amount = c["date"], int(c["amount"])
    # 前回、保存したが確認できなかった場合: 明細IDで状態を先に確かめる
    if prior and prior.get("zaim_id"):
        ok, _ = zedit.verify_by_id(page, day, amount, str(prior["zaim_id"]), zmatch.CALC_EXCLUDE)
        if ok:
            return {
                "state": "excluded" if apply else "identified",
                "message": "すでに画面で除外を確認",
                "zaim_id": str(prior["zaim_id"]),
                "prev_agg": prior.get("prev_agg") or "10",
                "verified": True,
            }
    row, why = zedit.locate_target(page, action)
    if row is None:
        return {"state": "unmatched", "message": why, "zaim_id": None, "prev_agg": None, "verified": False}
    zaim_id = zmatch.edit_id_from_url(row.get("edit_url")) or ""
    if not apply:
        return {
            "state": "identified",
            "message": "ちょうど1件に特定",
            "zaim_id": zaim_id,
            "prev_agg": zmatch.agg_value_from_title(row.get("calc_title")),
            "verified": False,
        }
    r = zedit.change_aggregate_by_id(
        page,
        day=day,
        amount=amount,
        zaim_id=zaim_id,
        value="exclude",
        expect_prev_value="10",
        shot_prefix=f"dup_{day}",
    )
    return {
        "state": "excluded" if r["ok"] else "failed",
        "message": r["message"],
        "zaim_id": zaim_id,
        "prev_agg": r.get("prev_agg"),
        "verified": bool(r.get("verified")),
    }


def process_candidates(
    cands: list[dict[str, Any]],
    rec: dict[str, Any],
    *,
    apply: bool,
    run_id: str,
    max_apply: int,
    scan: int,
    retry_manual: bool,
    zedit,
    page,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], Counter]:
    """戻り値: (今回の結果 entries, 新たに要手動になった entries, 絞れなかった理由の集計)"""
    results: list[dict[str, Any]] = []
    new_manual: list[dict[str, Any]] = []
    unmatched: Counter = Counter()
    attempted = 0  # 実際に保存を試みた件数（上限 max_apply）
    scanned = 0
    for c in cands:
        if scanned >= scan or (apply and attempted >= max_apply):
            break
        key = cand_key(c)
        prior = entry_for(rec, key)
        mode = classify_existing(prior, retry_manual=retry_manual)
        if mode == "skip":
            continue
        scanned += 1
        prior_attempts = int((prior or {}).get("attempts") or 0) if mode == "retry" else 0
        if retry_manual and prior and prior.get("status") == ST_MANUAL:
            prior_attempts = 0
        last: dict[str, Any] = {}
        for _ in range(max(1, MAX_ATTEMPTS - prior_attempts) if apply else 1):
            try:
                last = try_exclude(zedit, page, c, prior, apply=apply)
            except Exception as e:  # 画面側の想定外は失敗として数える（変更は確認できていない）
                last = {
                    "state": "failed",
                    "message": f"{type(e).__name__}: {str(e)[:80]}",
                    "zaim_id": (prior or {}).get("zaim_id"),
                    "prev_agg": (prior or {}).get("prev_agg"),
                    "verified": False,
                }
            if last["state"] != "failed":
                break
            prior_attempts += 1
            prior = {**(prior or {}), "zaim_id": last.get("zaim_id") or (prior or {}).get("zaim_id"),
                     "prev_agg": last.get("prev_agg") or (prior or {}).get("prev_agg")}
            time.sleep(1.0)
        state = last["state"]
        if state == "unmatched":
            unmatched[last["message"]] += 1
            results.append({"cand": c, "state": "unmatched", "message": last["message"]})
            continue
        if state == "identified":
            results.append({"cand": c, "state": "identified", **last})
            continue
        attempted += 1
        base = {
            "cand_key": key,
            "run_id": run_id,
            "type": c["type"],
            "date": c["date"],
            "amount": c["amount"],
            "shop": c["shop"],
            "card": c["pay"],
            "zaim_id": last.get("zaim_id"),
            "prev_agg": last.get("prev_agg"),
            "executed_at": now_iso(),
            "attempts": prior_attempts + (1 if state == "excluded" else 0),
            "last_message": last["message"],
        }
        if state == "excluded":
            entry = {**base, "status": ST_EXCLUDED, "verified": True,
                     "verification": "日別を再読み込みし、同じ明細IDの行が『常に含めない』になったことを確認"}
        else:
            manual = prior_attempts >= MAX_ATTEMPTS
            entry = {**base, "attempts": prior_attempts, "verified": False,
                     "status": ST_MANUAL if manual else ST_FAILED,
                     "verification": "確認できず"}
            if manual:
                entry["ops_notified"] = False
                new_manual.append(entry)
        _upsert(rec, entry)
        save_record(rec)  # 1件ごとに保存（途中で落ちても記録が残る）
        results.append({"cand": c, "state": entry["status"], **last})
    return results, new_manual, unmatched


def _upsert(rec: dict[str, Any], entry: dict[str, Any]) -> None:
    for i, e in enumerate(rec.setdefault("entries", [])):
        if e.get("cand_key") == entry["cand_key"]:
            rec["entries"][i] = {**e, **entry}
            return
    rec["entries"].append(entry)


# ---------------------------------------------------------------- 戻す
def pick_revert_targets(rec: dict[str, Any], ids: list[str], run_ids: list[str]) -> list[dict[str, Any]]:
    out = []
    for e in rec.get("entries") or []:
        if e.get("status") != ST_EXCLUDED:
            continue
        if (e.get("zaim_id") and str(e["zaim_id"]) in ids) or e.get("run_id") in run_ids:
            out.append(e)
    return out


def revert_entries(zedit, page, targets: list[dict[str, Any]], rec: dict[str, Any], *, run_id: str) -> list[dict[str, Any]]:
    done = []
    for e in targets:
        day, amount, zid = e["date"], int(e["amount"]), str(e["zaim_id"])
        try:
            rows = zedit.rows_for_day(page, day, amount)
            row = zmatch.find_by_id(rows, zid)
            if row is None:
                msg, ok = zmatch.R_ID_NOT_FOUND, False
            elif row.get("calc") != zmatch.CALC_EXCLUDE:
                msg, ok = f"いまの集計アイコンが除外ではない（{row.get('calc')}）— 変更せず", False
            else:
                r = zedit.change_aggregate_by_id(
                    page, day=day, amount=amount, zaim_id=zid, value="include",
                    expect_prev_value="0", shot_prefix=f"revert_{day}",
                )
                ok, msg = bool(r["ok"]), str(r["message"])
        except Exception as ex:
            ok, msg = False, f"{type(ex).__name__}: {str(ex)[:80]}"
        print(f"  {'OK' if ok else 'NG'} 戻す zaim_id={zid}: {msg}", flush=True)
        if ok:
            e.update(status=ST_REVERTED, reverted_at=now_iso(), revert_run_id=run_id)
            save_record(rec)
        done.append({"zaim_id": zid, "ok": ok, "message": msg})
    return done


# ---------------------------------------------------------------- CLI
def load_payments(year: int | None) -> tuple[list[dict[str, str]], dict[str, Any], Path]:
    import csv

    cfg = qc.load_cfg()
    y = year or datetime.now(JST).year
    csv_path = qc.resolve_csv(cfg, y)
    if not csv_path.is_file():
        csv_path = qc.resolve_csv(cfg, y - 1)
    if not csv_path.is_file():
        raise SystemExit(f"Zaim CSV がありません: {qc.resolve_csv(cfg, y)}")
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
    return [r for r in rows if r.get("方法") == "payment"], cfg, csv_path


def print_candidates(cands: list[dict[str, Any]], skips: Counter) -> None:
    ca = sum(1 for c in cands if c["type"] == "A")
    cb = sum(1 for c in cands if c["type"] == "B")
    print(f"# 候補 {len(cands)}件（型A {ca}・型B {cb}）")
    for i, c in enumerate(cands[:50], 1):
        print(f"  {i}. 型{c['type']} {c['date']} ¥{int(c['amount']):,} shop={str(c['shop'])[:20]} card={str(c['pay'])[:20]}")
    if skips:
        print("# 対象外の内訳（CSV 判定）: " + ", ".join(f"{k}={v}" for k, v in skips.most_common()))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="（既定）候補と行の特定だけ。Zaim は変更しない")
    ap.add_argument("--apply", action="store_true", help="実際に保存する（--yes も必要）")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--no-web", action="store_true", help="Zaim を開かず CSV だけで候補を出す")
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--max", type=int, default=MAX_PER_RUN, help=f"1回に保存する上限（最大{MAX_PER_RUN}）")
    ap.add_argument("--scan", type=int, default=DEFAULT_SCAN, help="Zaim 上で特定を試す候補数の上限")
    ap.add_argument("--retry-manual", action="store_true", help="要手動になった候補を再試行する")
    ap.add_argument("--revert", nargs="*", default=None, metavar="ZAIM_ID", help="明細IDで戻す")
    ap.add_argument("--revert-run", nargs="*", default=None, metavar="RUN_ID", help="実行IDの除外を全部戻す")
    ap.add_argument("--no-slack", action="store_true")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--login-method", choices=["email", "google"], default="email")
    ap.add_argument("--lock-wait", type=int, default=180)
    args = ap.parse_args(argv)

    apply = bool(args.apply)
    if apply and not args.yes:
        print("確認: --apply には --yes も必要です", file=sys.stderr)
        return 1
    if apply and args.dry_run:
        print("--dry-run と --apply は同時に指定できません", file=sys.stderr)
        return 1
    max_apply = max(1, min(int(args.max), MAX_PER_RUN))
    run_id = new_run_id()
    rec = load_record()

    # ---- 戻す
    if args.revert is not None or args.revert_run is not None:
        targets = pick_revert_targets(rec, [str(x) for x in (args.revert or [])], list(args.revert_run or []))
        print(f"# 戻す対象 {len(targets)}件（記録: {RECORD_PATH.name}）")
        for e in targets:
            print(f"  zaim_id={e.get('zaim_id')} {e.get('date')} ¥{int(e.get('amount') or 0):,} 型{e.get('type')} 実行ID={e.get('run_id')}")
        if not apply:
            print("# dry-run: --apply --yes を付けると、前の設定（常に含める）へ戻します")
            return 0
        if not targets:
            return 0
        zedit = _import_edit()
        if not acquire_lock(wait_sec=args.lock_wait):
            print("# Playwright 共有ロックを取れません。後で再実行してください", file=sys.stderr)
            return 3
        try:
            with zedit.web_session(headless=not args.headed, login_method=args.login_method) as page:
                done = revert_entries(zedit, page, targets, rec, run_id=run_id)
        finally:
            release_lock()
        ok_n = sum(1 for d in done if d["ok"])
        if ok_n and not args.no_slack:
            post_slack("report", f"【報告】613 Zaim重複除外｜{ok_n}件を元（常に含める）に戻しました（戻し実行ID {run_id}）")
        return 0 if ok_n == len(done) else 2

    # ---- 候補
    payments, cfg, csv_path = load_payments(args.year)
    cands, skips = find_candidates(payments, cfg)
    print(f"# CSV: {csv_path.name}  実行ID: {run_id}  モード: {'APPLY' if apply else 'dry-run'}")
    print_candidates(cands, skips)
    if args.no_web or not cands:
        return 0

    zedit = _import_edit()
    if not acquire_lock(wait_sec=args.lock_wait):
        print("# Playwright 共有ロックを取れません。後で再実行してください", file=sys.stderr)
        return 3
    try:
        try:
            ctx = zedit.web_session(headless=not args.headed, login_method=args.login_method)
            page = ctx.__enter__()
        except Exception as e:  # ログイン不可・認証待ち
            msg = f"Zaim にログインできません（認証待ち・パスワード等）: {type(e).__name__}"
            print(f"# {msg}", file=sys.stderr)
            if apply and not args.no_slack:
                post_slack("ops", f"【要手動】613 Zaim重複除外｜{msg}（実行ID {run_id}）")
            return 4
        try:
            results, new_manual, unmatched = process_candidates(
                cands, rec, apply=apply, run_id=run_id, max_apply=max_apply, scan=args.scan,
                retry_manual=args.retry_manual, zedit=zedit, page=page,
            )
        finally:
            ctx.__exit__(None, None, None)
    finally:
        release_lock()

    # ---- 集計・表示（実額はここ＝手元の端末出力のみ。PR・公開物には書かない）
    states = Counter(r["state"] for r in results)
    print(f"# 結果: 特定できた={states.get('identified', 0)} 除外={states.get(ST_EXCLUDED, 0)} "
          f"失敗={states.get(ST_FAILED, 0)} 要手動={states.get(ST_MANUAL, 0)} 絞れず={states.get('unmatched', 0)}")
    if unmatched:
        print("# 絞れなかった理由: " + ", ".join(f"{k}={v}" for k, v in unmatched.most_common()))
    for r in results:
        c = r["cand"]
        print(f"  [{r['state']}] 型{c['type']} {c['date']} ¥{int(c['amount']):,} id={r.get('zaim_id')} {r.get('message')}")

    if apply and not args.no_slack:
        this_run = [e for e in rec.get("entries") or [] if e.get("run_id") == run_id]
        text = build_report_text(this_run, run_id)
        if text:
            if unmatched:
                text += f"\n（絞れず未適用 {sum(unmatched.values())}件）"
            post_slack("report", text)
        ops = build_ops_text(new_manual, run_id)
        if ops:
            post_slack("ops", ops)
            for e in new_manual:
                e["ops_notified"] = True
            save_record(rec)
    return 0 if states.get(ST_FAILED, 0) + states.get(ST_MANUAL, 0) == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
