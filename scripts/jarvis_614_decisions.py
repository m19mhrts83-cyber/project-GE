#!/usr/bin/env python3
"""614 ポイント・還元ウォッチ — 判断ログと有効基準（第3稿 P2・工程22〜24）。

正本は追記専用の構造化ログ `614_watch/decisions.jsonl`（非公開側・gitignore 済み）。1行＝1イベント:
  decided  新しい判断（decision_id・判断事項・AI案・本人の選択・理由の原文・対象・今回だけ／次回基準・期限・run/incident）
  revised  改定（選択・理由・対象・範囲・期限の変更。元の履歴は消さない）
  revoked  取消（理由は任意。補作しない）

守ること:
  - 本人の述べた理由は原文のまま。無ければ None のまま保存し、AI／プログラムが補作しない
  - 見送り（declined）・保留（held）・今回だけ（this_time）は次回の基準に採用しない
  - 採用（adopted）＋次回基準（standing）＋期限内＋取消なしだけが有効な基準
  - 期限切れは適用を止め『再判断待ち』にする。過去の判断は参考表示。以前の基準へ自動復帰しない
  - 基準ログを読めない時は『基準なし』とみなさず、その系統の基準に依存する出力だけ安全側に止める
    （壊れた1行を読み飛ばすと取消が効かなくなるため、読み飛ばさず読取失敗にする）
  - 実行時に AI は呼ばない。実額・秘密はここでは扱わない（理由の原文は本人が書いた通りに残る＝非公開側のみ）

期限は `YYYY-MM-DD` で、その日の終わりまで有効（JST）。
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import secrets
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_614_runlog as runlog  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
CHOICES = ("adopted", "declined", "held")
CHOICE_LABEL = {"adopted": "採用", "declined": "見送り", "held": "保留"}
SCOPES = ("this_time", "standing")
SCOPE_LABEL = {"this_time": "今回だけ", "standing": "次回基準"}

# 系統ごとに『判断に依存する出力』を持つ基準キー。ここにあるキーだけが実行前の取得・適用の対象。
# 登録がまだ無いキーの間は従来どおり動く（既存の挙動を変えない）。基準が登録された後は期限切れ・読取失敗で
# その出力だけが止まる。他の系統へ広げる時はここに足し、読む側のコードも同じ PR で足す。
CRITERIA_CONSUMERS: dict[str, dict[str, str]] = {
    "card_benefit": {"card_benefit.allocation": "寄せ先（Olive／Bonvoy）の推奨の判断基準（D1）"},
}


class DecisionLogError(RuntimeError):
    """判断ログを読めない（壊れた行・権限）。基準なしとはみなさず、依存する出力を止める。"""


def decisions_path() -> Path:
    return runlog.log_dir() / "decisions.jsonl"


def new_decision_id(now: datetime | None = None) -> str:
    return f"dec-{(now or datetime.now(JST)).strftime('%Y%m%d')}-{secrets.token_hex(2)}"


# ---------------------------------------------------------------- 読み書き

def load_events_strict(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or decisions_path()
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        raise DecisionLogError(f"{p.name} を読めません（{type(e).__name__}）") from e
    for i, ln in enumerate(lines, 1):
        if not ln.strip():
            continue
        try:
            d = json.loads(ln)
        except json.JSONDecodeError as e:
            raise DecisionLogError(f"{p.name} の{i}行目が壊れています（読み飛ばさず停止）") from e
        if not isinstance(d, dict) or not d.get("event") or not d.get("decision_id"):
            raise DecisionLogError(f"{p.name} の{i}行目の形式が想定外です")
        out.append(d)
    return out


def append_event(ev: dict[str, Any], path: Path | None = None) -> bool:
    return runlog.append_run(ev, path or decisions_path())


def _lock_fd(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path.with_suffix(".lock"), os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def _need_text(name: str, v: str | None) -> str:
    if not v or not str(v).strip():
        raise ValueError(f"{name} が空です")
    return str(v).strip()


def _check_date(v: str | None) -> str | None:
    if v is None or str(v).strip() == "":
        return None
    try:
        return date.fromisoformat(str(v).strip()).isoformat()
    except ValueError as e:
        raise ValueError(f"期限は YYYY-MM-DD で指定してください: {v}") from e


def record_decision(
    *, topic: str, item: str, choice: str, scope: str, ai_proposal: str | None = None,
    reason_text: str | None = None, target: str | None = None, expires_at: str | None = None,
    run_id: str | None = None, incident_ids: list[str] | None = None, system: str | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """判断を1件追記する。reason_text は本人の原文（無ければ None のまま。補作しない）。"""
    if choice not in CHOICES:
        raise ValueError(f"choice は {CHOICES} のどれか")
    if scope not in SCOPES:
        raise ValueError(f"scope は {SCOPES} のどれか")
    ev = {
        "event": "decided",
        "decision_id": new_decision_id(),
        "at": runlog.now_iso(),
        "topic": _need_text("topic", topic),
        "system": (system or topic.split(".")[0]).strip(),
        "item": _need_text("item", item),
        "ai_proposal": (ai_proposal or "").strip() or None,
        "choice": choice,
        "reason_text": (reason_text.strip() if reason_text and reason_text.strip() else None),
        "target": (target or "").strip() or None,
        "scope": scope,
        "expires_at": _check_date(expires_at),
        "run_id": run_id or None,
        "incident_ids": list(incident_ids or []),
    }
    p = path or decisions_path()
    fd = _lock_fd(p)
    try:
        load_events_strict(p)  # 壊れたログへは追記しない（取消が効かなくなるのを防ぐ）
        if not append_event(ev, p):
            raise DecisionLogError("判断ログへ追記できませんでした")
    finally:
        os.close(fd)
    return ev


_REVISABLE = ("choice", "reason_text", "target", "scope", "expires_at", "ai_proposal", "item")


def revise_decision(decision_id: str, changes: dict[str, Any], *, run_id: str | None = None,
                    path: Path | None = None) -> dict[str, Any]:
    p = path or decisions_path()
    fd = _lock_fd(p)
    try:
        view = fold(load_events_strict(p))
        if decision_id not in view:
            raise ValueError(f"decision_id が見つかりません: {decision_id}")
        if view[decision_id]["revoked"]:
            raise ValueError("取消済みの判断は改定できません（新しい判断として記録してください）")
        ch: dict[str, Any] = {}
        for k, v in changes.items():
            if k not in _REVISABLE:
                raise ValueError(f"改定できない項目: {k}")
            if k == "choice" and v not in CHOICES:
                raise ValueError(f"choice は {CHOICES} のどれか")
            if k == "scope" and v not in SCOPES:
                raise ValueError(f"scope は {SCOPES} のどれか")
            if k == "expires_at":
                v = _check_date(v)
            if k == "reason_text":
                v = v.strip() if isinstance(v, str) and v.strip() else None
            ch[k] = v
        if not ch:
            raise ValueError("変更する項目がありません")
        ev = {"event": "revised", "decision_id": decision_id, "at": runlog.now_iso(), "changes": ch,
              "run_id": run_id or None}
        if not append_event(ev, p):
            raise DecisionLogError("判断ログへ追記できませんでした")
    finally:
        os.close(fd)
    return ev


def revoke_decision(decision_id: str, reason_text: str | None = None, *, run_id: str | None = None,
                    path: Path | None = None) -> dict[str, Any]:
    p = path or decisions_path()
    fd = _lock_fd(p)
    try:
        view = fold(load_events_strict(p))
        if decision_id not in view:
            raise ValueError(f"decision_id が見つかりません: {decision_id}")
        if view[decision_id]["revoked"]:
            raise ValueError("すでに取消済みです")
        ev = {"event": "revoked", "decision_id": decision_id, "at": runlog.now_iso(),
              "reason_text": (reason_text.strip() if reason_text and reason_text.strip() else None),
              "run_id": run_id or None}
        if not append_event(ev, p):
            raise DecisionLogError("判断ログへ追記できませんでした")
    finally:
        os.close(fd)
    return ev


# ---------------------------------------------------------------- 現在の姿

def fold(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """イベントを順に当てはめた『今の判断』。history に全イベントを残す（上書きで消さない）。"""
    view: dict[str, dict[str, Any]] = {}
    for ev in events:
        did = str(ev["decision_id"])
        kind = ev.get("event")
        if kind == "decided":
            if did in view:
                continue  # 同じ ID の二重 decided は無視（最初を正）
            v = {k: ev.get(k) for k in ("decision_id", "topic", "system", "item", "ai_proposal", "choice",
                                        "reason_text", "target", "scope", "expires_at", "run_id")}
            v["incident_ids"] = list(ev.get("incident_ids") or [])
            v["decided_at"] = ev.get("at")
            v["revoked"] = False
            v["revoked_at"] = None
            v["revoke_reason_text"] = None
            v["history"] = [ev]
            view[did] = v
        elif did in view:
            v = view[did]
            v["history"].append(ev)
            if kind == "revised":
                for k, val in (ev.get("changes") or {}).items():
                    if k in _REVISABLE:
                        v[k] = val
                v["revised_at"] = ev.get("at")
            elif kind == "revoked":
                v["revoked"] = True
                v["revoked_at"] = ev.get("at")
                v["revoke_reason_text"] = ev.get("reason_text")
    return view


def _today(now: datetime | None) -> date:
    return (now or datetime.now(JST)).astimezone(JST).date()


def standing_state(v: dict[str, Any], now: datetime | None = None) -> str:
    """effective（有効な基準）／expired（期限切れ・再判断待ち）／revoked／not_adopted（見送り・保留）／this_time。"""
    if v["revoked"]:
        return "revoked"
    if v["choice"] != "adopted":
        return "not_adopted"
    if v["scope"] != "standing":
        return "this_time"
    exp = v.get("expires_at")
    if exp and _today(now) > date.fromisoformat(exp):
        return "expired"
    return "effective"


def _brief(v: dict[str, Any]) -> dict[str, Any]:
    """表示・記録に使う要約（実額・秘密は入れない。理由は参考表示用に原文のまま）。"""
    return {k: v.get(k) for k in ("decision_id", "topic", "item", "choice", "scope", "expires_at",
                                  "reason_text", "decided_at")}


def criteria_for(system: str, now: datetime | None = None, path: Path | None = None) -> dict[str, Any]:
    """実行前に、この系統が使う基準を取得する（工程24）。

    返り値 status:
      none        この系統に登録された基準キーが無い（従来どおり）
      ok          取得できた。applied=適用する判断／waiting=期限切れで再判断待ち／reference=参考表示
      read_error  判断ログを読めない。基準が要る出力は止める（『基準なし』にしない）
    """
    keys = CRITERIA_CONSUMERS.get(system) or {}
    out: dict[str, Any] = {"system": system, "status": "none", "applied": [], "waiting": [],
                           "reference": [], "error": "", "keys": list(keys)}
    if not keys:
        return out
    try:
        view = fold(load_events_strict(path))
    except DecisionLogError as e:
        out["status"] = "read_error"
        out["error"] = str(e)
        return out
    out["status"] = "ok"
    for key, label in keys.items():
        mine = [v for v in view.values() if v["topic"] == key and not v["revoked"]]
        mine.sort(key=lambda v: str(v.get("decided_at")))
        adopted = [v for v in mine if v["choice"] == "adopted" and v["scope"] == "standing"]
        latest = adopted[-1] if adopted else None
        if latest is not None:
            st = standing_state(latest, now)
            if st == "effective":
                out["applied"].append({**_brief(latest), "key": key, "result": "applied"})
            elif st == "expired":
                out["waiting"].append({**_brief(latest), "key": key, "label": label})
        # 参考表示: 適用しない過去の判断（期限切れ・見送り・保留・今回だけ・古い採用）
        applied_ids = {a["decision_id"] for a in out["applied"]}
        for v in mine:
            if v["decision_id"] not in applied_ids:
                out["reference"].append({**_brief(v), "key": key, "state": standing_state(v, now)})
    return out


def gate_recommendation(rec: dict[str, Any], criteria: dict[str, Any] | None) -> dict[str, Any]:
    """基準に依存する推奨を、基準の状態で止める。取得済みの事実・数値は呼び出し側が引き続き表示する。"""
    if not criteria or criteria.get("status") == "none":
        return rec
    if criteria["status"] == "read_error":
        return {"card": None, "withheld": True, "criteria_hold": "read_error",
                "line": "寄せ先の推奨は保留（判断基準を読めませんでした）。取れた数値はそのまま表示"}
    if criteria["waiting"]:
        w = criteria["waiting"][0]
        past = CHOICE_LABEL.get(str(w.get("choice")), "?")
        return {
            "card": None, "withheld": True, "criteria_hold": "redecision",
            "line": f"寄せ先の推奨は停止（判断基準が期限切れ・再判断待ち。期限 {w.get('expires_at')}）。"
                    f"取れた数値はそのまま表示。以前の判断（参考・{past}・{w.get('decision_id')}）は自動では使いません",
            "reference": [w["decision_id"]],
        }
    if criteria["applied"]:
        return {**rec, "criteria_applied": [a["decision_id"] for a in criteria["applied"]]}
    return rec


# ---------------------------------------------------------------- CLI

def _print_view(v: dict[str, Any], now: datetime | None = None) -> None:
    st = standing_state(v, now)
    reason = v.get("reason_text") if v.get("reason_text") else "（理由なし）"
    print(f"{v['decision_id']} [{st}] {v['topic']}｜{CHOICE_LABEL.get(v['choice'])}・{SCOPE_LABEL.get(v['scope'])}"
          f"・期限 {v.get('expires_at') or 'なし'}｜{v['item']}｜理由: {reason}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="614 判断ログ（工程22〜24）。本人の判断を記録する。理由は原文のまま")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record", help="判断を記録")
    r.add_argument("--topic", required=True, help="基準キー例: card_benefit.allocation")
    r.add_argument("--item", required=True, help="判断事項")
    r.add_argument("--choice", required=True, choices=CHOICES)
    r.add_argument("--scope", required=True, choices=SCOPES)
    r.add_argument("--ai-proposal")
    r.add_argument("--reason", help="本人が述べた理由の原文。無ければ省略（補作しない）")
    r.add_argument("--target")
    r.add_argument("--expires", help="期限 YYYY-MM-DD（省略=期限なし）")
    r.add_argument("--run-id")
    r.add_argument("--incident-id", action="append", default=[])
    v = sub.add_parser("revise", help="改定")
    v.add_argument("decision_id")
    for k in ("choice", "scope", "reason", "target", "expires", "ai-proposal", "item"):
        v.add_argument(f"--{k}")
    rv = sub.add_parser("revoke", help="取消")
    rv.add_argument("decision_id")
    rv.add_argument("--reason")
    sub.add_parser("list", help="判断の一覧")
    c = sub.add_parser("criteria", help="系統の有効基準を取得して表示")
    c.add_argument("system")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "record":
            ev = record_decision(topic=a.topic, item=a.item, choice=a.choice, scope=a.scope,
                                 ai_proposal=a.ai_proposal, reason_text=a.reason, target=a.target,
                                 expires_at=a.expires, run_id=a.run_id, incident_ids=a.incident_id)
            print(f"記録しました: {ev['decision_id']}")
        elif a.cmd == "revise":
            mapping = {"choice": a.choice, "scope": a.scope, "reason_text": a.reason, "target": a.target,
                       "expires_at": a.expires, "ai_proposal": a.ai_proposal, "item": a.item}
            revise_decision(a.decision_id, {k: val for k, val in mapping.items() if val is not None})
            print("改定を記録しました（元の履歴は残っています）")
        elif a.cmd == "revoke":
            revoke_decision(a.decision_id, a.reason)
            print("取消を記録しました")
        elif a.cmd == "list":
            for v_ in fold(load_events_strict()).values():
                _print_view(v_)
        elif a.cmd == "criteria":
            print(json.dumps(criteria_for(a.system), ensure_ascii=False, indent=2))
    except (ValueError, DecisionLogError) as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    if a.cmd in ("record", "revise", "revoke"):
        try:  # 記録のたびに参照用 Markdown を作り直す（失敗しても記録は有効）
            import jarvis_614_knowledge as kn
            kn.regenerate_quiet()
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
