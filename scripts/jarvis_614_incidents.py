#!/usr/bin/env python3
"""614 ポイント・還元ウォッチ — 障害の識別・自動復旧の安全弁・障害対応履歴（第3稿 P2・工程33〜35）。

正本は追記専用の構造化ログ `614_watch/incidents.jsonl`（非公開側）。状態（連続回数・停止中の自動復旧）は
このログから毎回数え直す＝別の state と食い違わない。1行＝1イベント:
  occurred         障害の発生（incident_id・key・run_id・事実・連続回数）
  annotate         原因・関連 decision_id の追記（原因が『事実』か『推定』かを区別して残す）
  remedy           対策とその結果（失敗した対策・止めた対策・未承認で実行しなかった対策も残す）
  suspended        同じ障害が連続3回になり、その自動対策を止めた
  resume_approved  本人の明示承認で自動対策を再開（原因・対策・検証結果の記録が揃っている時だけ）
  reset            次回の通常実行が成功して連続回数を 0 に戻した

規則（TASK 4.11）:
  - 同一障害＝『系統＋工程＋障害分類＋エラーコード』（key）。エラーコードが無い時は no_code
    （症状による代替識別は未決＝実装しない）
  - 事前承認された安全な対策（REMEDIES の approved=True）だけを自動実行してよい。過去に成功したことは根拠にしない
  - 同一障害が連続3回目なら、その自動対策を実行せず停止（3回目の障害に対しては実行しない）。他の系統は止めない
  - 自動復旧が成功しただけでは連続回数を戻さない。次回、その系統・工程の『通常実行が成功』した時だけ戻す。
    正常スキップ・停止中・dry-run・別系統の成功では戻さない
  - 停止した自動対策は、原因・対策・検証結果の記録があり、本人が明示承認した時だけ再開（approve_resume）
  - 履歴検索は決定論（同じ key → 同じ系統＋工程の順）。実行時に AI は呼ばない
  - ログを読めない時は自動対策を実行しない（安全側）
実額・秘密は記録しない（事実は短い文だけ）。保持は継続・年1回点検（自動削除しない）。
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import secrets
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_614_runlog as runlog  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
SUSPEND_AT = 3  # 同一障害の連続回数がこの値に達した（＝3回目の）時、その自動対策を実行しない
NO_CODE = "no_code"
INCIDENT_STATUSES = ("failed", "unverified")  # 障害とみなす工程の結果（部分成功・取得待ちは障害にしない）

# 事前承認された自動対策。コードに書く＝レビューを通ったものだけが承認済み。過去の成功は根拠にしない。
# 連続3回の停止に接続済みなのは save_retry（jarvis_614_verified_state）と repush（jarvis_614_display）。
# Slack の控え保存・投稿のやり直しは台帳（jarvis_614_slack_ledger）で二重投稿を防いでおり、この停止には未接続。
REMEDIES: dict[str, dict[str, Any]] = {
    "save_retry": {
        "label": "保存だけ1回やり直す（外部サイトは取り直さない）", "approved": True, "max_per_occurrence": 1,
    },
    "repush": {
        "label": "保存済み state から画面へ再 push（最大1回）", "approved": True, "max_per_occurrence": 1,
    },
    "draw_retry": {
        "label": "テイチャン抽選の再実行", "approved": False,
        "reason": "抽選済みか不明な時の再実行条件が未確定（二重抽選の恐れ）。自動化は保留（TASK 4.2・4.14）",
    },
}


class IncidentLogError(RuntimeError):
    """障害対応履歴を読めない。自動対策は実行しない（安全側）。"""


def incidents_path() -> Path:
    return runlog.log_dir() / "incidents.jsonl"


def make_key(system: str, stage: str, category: str, error_code: str | None) -> str:
    return "|".join([system, stage, category, (error_code or NO_CODE)])


def new_incident_id(now: datetime | None = None) -> str:
    return f"inc-{(now or datetime.now(JST)).strftime('%Y%m%d')}-{secrets.token_hex(2)}"


# ---------------------------------------------------------------- 読み書き

def load_events_strict(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or incidents_path()
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        raise IncidentLogError(f"{p.name} を読めません（{type(e).__name__}）") from e
    out: list[dict[str, Any]] = []
    for i, ln in enumerate(lines, 1):
        if not ln.strip():
            continue
        try:
            d = json.loads(ln)
        except json.JSONDecodeError as e:
            raise IncidentLogError(f"{p.name} の{i}行目が壊れています（停止した対策の再開を防ぐため読み飛ばさない）") from e
        if not isinstance(d, dict) or not d.get("event"):
            raise IncidentLogError(f"{p.name} の{i}行目の形式が想定外です")
        out.append(d)
    return out


@contextlib.contextmanager
def _locked(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path.with_suffix(".lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _append(ev: dict[str, Any], path: Path) -> bool:
    ev = {**ev, "at": ev.get("at") or runlog.now_iso()}
    return runlog.append_run(ev, path)


def _emergency(line: str) -> None:
    try:
        import jarvis_614_ops as ops
        ops.emergency_log(line)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------- 状態（ログから数え直す）

def fold(events: list[dict[str, Any]]) -> dict[str, Any]:
    """key ごとの連続回数・停止中の対策・発生した incident を、ログから数える。"""
    keys: dict[str, dict[str, Any]] = {}
    incidents: dict[str, dict[str, Any]] = {}

    def k(key: str) -> dict[str, Any]:
        return keys.setdefault(key, {"count": 0, "suspended": {}, "incident_ids": [], "runs": []})

    for ev in events:
        kind = ev.get("event")
        if kind == "occurred":
            key = ev["key"]
            st = k(key)
            st["count"] += 1
            st["incident_ids"].append(ev["incident_id"])
            st["runs"].append(ev.get("run_id"))
            incidents[ev["incident_id"]] = {**ev, "remedies": [], "annotations": [], "decision_ids": list(ev.get("decision_ids") or [])}
        elif kind == "annotate" and ev.get("incident_id") in incidents:
            inc = incidents[ev["incident_id"]]
            inc["annotations"].append(ev)
            for d in ev.get("decision_ids") or []:
                if d not in inc["decision_ids"]:
                    inc["decision_ids"].append(d)
        elif kind == "remedy" and ev.get("incident_id") in incidents:
            incidents[ev["incident_id"]]["remedies"].append(ev)
        elif kind == "suspended":
            k(ev["key"])["suspended"][ev["remedy_id"]] = {"at": ev.get("at"), "incident_id": ev.get("incident_id")}
        elif kind == "resume_approved":
            st = k(ev["key"])
            st["suspended"].pop(ev["remedy_id"], None)
            st["count"] = 0  # 本人が再基準化した。次の発生を1回目として数える
        elif kind == "reset":
            k(ev["key"])["count"] = 0
    return {"keys": keys, "incidents": incidents}


def load_state(path: Path | None = None) -> dict[str, Any]:
    return fold(load_events_strict(path))


# ---------------------------------------------------------------- 工程33: 識別・履歴検索

def search_history(system: str, stage: str, error_code: str | None = None, category: str | None = None,
                   *, limit: int = 5, path: Path | None = None) -> dict[str, Any]:
    """過去の障害対応を決定論で探す。順序: ①同一 key（新しい順）→ ②同じ系統＋工程（新しい順）。

    事実（fact）・推定原因（cause_inferred）・確認済みの原因（cause_confirmed）・本人判断（decision_ids）を分けて返す。"""
    st = load_state(path)
    code = error_code or NO_CODE
    exact: list[dict[str, Any]] = []
    related: list[dict[str, Any]] = []
    for inc in sorted(st["incidents"].values(), key=lambda i: str(i.get("at")), reverse=True):
        if inc["system"] != system or inc["stage"] != stage:
            continue
        item = _inc_summary(inc)
        if inc["error_code"] == code and (category is None or inc["category"] == category):
            exact.append(item)
        else:
            related.append(item)
    return {"key": make_key(system, stage, category or "*", code), "exact": exact[:limit],
            "related": related[:limit]}


def _inc_summary(inc: dict[str, Any]) -> dict[str, Any]:
    causes = [a for a in inc["annotations"] if a.get("cause")]
    return {
        "incident_id": inc["incident_id"], "at": inc.get("at"), "run_id": inc.get("run_id"),
        "category": inc["category"], "error_code": inc["error_code"],
        "fact": inc.get("fact"),  # 事実
        "cause_confirmed": [a["cause"] for a in causes if a.get("cause_kind") == "fact"],
        "cause_inferred": [a["cause"] for a in causes if a.get("cause_kind") != "fact"],
        "remedies": [{"remedy_id": r.get("remedy_id"), "auto": r.get("auto"), "outcome": r.get("outcome"),
                      "verification": r.get("verification")} for r in inc["remedies"]],
        "decision_ids": inc["decision_ids"],  # 本人判断（decisions.jsonl の ID）
        "occurrence_no": inc.get("occurrence_no"),
    }


# ---------------------------------------------------------------- 工程33〜35: 発生の記録と自動対策の可否

class Occurrence:
    """1回の障害。may_auto() で自動対策を実行してよいか確かめ、record_remedy() で結果を残す。"""

    def __init__(self, *, key: str, incident_id: str | None, count: int, system: str, stage: str,
                 run_id: str, path: Path, error: str = "", suspended: dict[str, Any] | None = None,
                 new: bool = False):
        self.key, self.incident_id, self.count, self.new = key, incident_id, count, new
        self.system, self.stage, self.run_id, self.path = system, stage, run_id, path
        self.error = error  # 履歴を読めない・書けない時の理由（自動対策は実行しない）
        self._suspended = suspended or {}

    def may_auto(self, remedy_id: str) -> tuple[bool, str]:
        rem = REMEDIES.get(remedy_id)
        if self.error or not self.incident_id:
            return False, f"障害履歴を扱えないため自動対策は実行しない（{self.error or '記録失敗'}）"
        if rem is None or not rem.get("approved"):
            why = (rem or {}).get("reason") or "事前承認された対策ではない"
            self._remedy(remedy_id, "not_approved", f"自動実行しない: {why}", auto=False)
            return False, f"未承認の対策のため自動実行しない（{why}）"
        if remedy_id in self._suspended:
            self._remedy(remedy_id, "blocked", "停止中の自動対策（本人の明示承認まで再開しない）", auto=False)
            return False, "同一障害の連続発生で停止中（本人の明示承認が必要）"
        if self.count >= SUSPEND_AT:
            self._suspend(remedy_id)
            return False, f"同一障害が連続{self.count}回目のため自動対策『{remedy_id}』を停止"
        return True, ""

    def _suspend(self, remedy_id: str) -> None:
        with _locked(self.path):
            if not _append({"event": "suspended", "key": self.key, "remedy_id": remedy_id,
                            "incident_id": self.incident_id, "run_id": self.run_id,
                            "reason": f"同一障害の連続{self.count}回目"}, self.path):
                _emergency(f"incidents suspended 書込失敗 key={self.key}")
        self._suspended[remedy_id] = {"incident_id": self.incident_id}
        self._remedy(remedy_id, "blocked", f"連続{self.count}回目のため実行せず停止", auto=False)
        try:
            import jarvis_614_ops as ops
            hist = search_history(self.system, self.stage, self.key.split("|")[-1], path=self.path)
            past = len(hist["exact"]) + len(hist["related"])
            ops.notify_ops(
                system=self.system, stage=self.stage,
                cause=f"同じ障害が連続{self.count}回（{self.key.split('|')[-1]}）。自動対策『{remedy_id}』を停止",
                next_action=f"原因・対策・検証結果を記録し、本人の明示承認で再開。過去の関連事例 {past} 件（{self.incident_id}）",
                run_id=self.run_id,
            )
        except Exception as e:  # noqa: BLE001 — 通知の失敗で本線を落とさない
            _emergency(f"incidents suspended 通知失敗 {type(e).__name__}")

    def _remedy(self, remedy_id: str, outcome: str, verification: str | None, *, auto: bool) -> None:
        if not self.incident_id:
            return
        with _locked(self.path):
            if not _append({"event": "remedy", "incident_id": self.incident_id, "remedy_id": remedy_id,
                            "auto": auto, "outcome": outcome, "verification": (verification or "")[:200] or None,
                            "run_id": self.run_id}, self.path):
                _emergency(f"incidents remedy 書込失敗 {self.incident_id}")

    def record_remedy(self, remedy_id: str, outcome: str, verification: str | None = None, *, auto: bool = True) -> None:
        """実行した対策の結果（success／failed）と検証結果。失敗した対策も残す。連続回数は戻さない。"""
        self._remedy(remedy_id, outcome, verification, auto=auto)


def begin_occurrence(*, system: str, stage: str, category: str, error_code: str | None, run_id: str,
                     fact: str = "", path: Path | None = None) -> Occurrence:
    """障害の発生を記録して連続回数を数える。同じ run の同じ key は1回に数える。履歴を扱えなければ error 付き。"""
    p = path or incidents_path()
    key = make_key(system, stage, category, error_code)
    try:
        with _locked(p):
            st = load_state(p)
            cur = st["keys"].get(key, {"count": 0, "suspended": {}})
            same = [i for i in st["incidents"].values() if i["key"] == key and i.get("run_id") == run_id]
            if same:
                inc = same[0]
                return Occurrence(key=key, incident_id=inc["incident_id"], count=cur["count"], system=system,
                                  stage=stage, run_id=run_id, path=p, suspended=dict(cur["suspended"]))
            iid = new_incident_id()
            count = cur["count"] + 1
            ev = {"event": "occurred", "incident_id": iid, "key": key, "system": system, "stage": stage,
                  "category": category, "error_code": error_code or NO_CODE,
                  "code_missing": not error_code, "run_id": run_id, "fact": (fact or "")[:200],
                  "occurrence_no": count, "decision_ids": []}
            if not _append(ev, p):
                raise IncidentLogError("incidents.jsonl へ追記できません")
            return Occurrence(key=key, incident_id=iid, count=count, system=system, stage=stage, run_id=run_id,
                              path=p, suspended=dict(cur["suspended"]), new=True)
    except (IncidentLogError, OSError) as e:
        _emergency(f"incidents 発生の記録失敗 {system}/{stage}/{error_code} run={run_id}: {type(e).__name__}")
        return Occurrence(key=key, incident_id=None, count=0, system=system, stage=stage, run_id=run_id, path=p,
                          error=str(e)[:100])


class Ticket:
    """既存の再試行箇所（保存・再 push）が使う窓口。allowed なら再試行し、done() で結果を残す。"""

    def __init__(self, occ: Occurrence, remedy_id: str):
        self.occ, self.remedy_id = occ, remedy_id
        self.allowed, self.reason = occ.may_auto(remedy_id)

    def done(self, ok: bool, verification: str = "") -> None:
        if self.allowed:
            self.occ.record_remedy(self.remedy_id, "success" if ok else "failed", verification)


def remedy_ticket(system: str, stage: str, error_code: str | None, remedy_id: str, *,
                  run_id: str | None = None, fact: str = "", category: str = "failed") -> Ticket:
    rid = run_id or (os.environ.get("JARVIS_614_RUN_ID") or "").strip() or runlog.new_run_id(system)
    occ = begin_occurrence(system=system, stage=stage, category=category, error_code=error_code, run_id=rid, fact=fact)
    return Ticket(occ, remedy_id)


# ---------------------------------------------------------------- run との連携

def observe_run(run: dict[str, Any], path: Path | None = None) -> dict[str, int]:
    """run の結果から、①失敗・確認不能の工程を障害として記録 ②通常実行の成功で連続回数を戻す。

    リセットするのは dry-run でない run の status=success だけ。skipped／not_applicable／別系統の成功は戻さない。
    同じ run でその工程の障害が起きていたら（自動復旧で成功に見えても）戻さない。"""
    out = {"occurred": 0, "reset": 0}
    if run.get("dry_run"):
        return out
    p = path or incidents_path()
    rid = str(run.get("run_id") or "-")
    failed_stages: set[tuple[str, str]] = set()
    for system, srec in (run.get("systems") or {}).items():
        for stage, s in (srec.get("stages") or {}).items():
            if s.get("status") in INCIDENT_STATUSES:
                failed_stages.add((system, stage))
                occ = begin_occurrence(system=system, stage=stage, category=str(s["status"]),
                                       error_code=s.get("error_code"), run_id=rid, fact=str(s.get("detail") or ""), path=p)
                if occ.new:
                    out["occurred"] += 1
    try:
        with _locked(p):
            st = load_state(p)
            ids_this_run = {(i["system"], i["stage"]) for i in st["incidents"].values() if i.get("run_id") == rid}
            for system, srec in (run.get("systems") or {}).items():
                for stage, s in (srec.get("stages") or {}).items():
                    if s.get("status") != "success" or (system, stage) in failed_stages or (system, stage) in ids_this_run:
                        continue
                    for key, kst in st["keys"].items():
                        ksys, kstage = key.split("|")[:2]
                        if ksys == system and kstage == stage and kst["count"] > 0:
                            if _append({"event": "reset", "key": key, "run_id": rid,
                                        "reason": "次回の通常実行が成功"}, p):
                                out["reset"] += 1
    except (IncidentLogError, OSError) as e:
        _emergency(f"incidents リセット判定失敗 run={rid}: {type(e).__name__}")
    if out["occurred"] or out["reset"]:
        try:
            import jarvis_614_knowledge as kn
            kn.regenerate_quiet()
        except Exception:  # noqa: BLE001
            pass
    return out


# ---------------------------------------------------------------- 工程35: 追記・再開の承認

def annotate(incident_id: str, *, cause: str | None = None, cause_kind: str = "inferred",
             decision_ids: list[str] | None = None, path: Path | None = None) -> None:
    """原因（cause_kind=fact 確認済み／inferred 推定）や関連 decision_id を足す。履歴は消さない。"""
    if cause_kind not in ("fact", "inferred"):
        raise ValueError("cause_kind は fact か inferred")
    p = path or incidents_path()
    with _locked(p):
        if incident_id not in load_state(p)["incidents"]:
            raise ValueError(f"incident_id が見つかりません: {incident_id}")
        if not _append({"event": "annotate", "incident_id": incident_id, "cause": (cause or "").strip() or None,
                        "cause_kind": cause_kind, "decision_ids": list(decision_ids or [])}, p):
            raise IncidentLogError("追記できませんでした")


def resume_blockers(key: str, remedy_id: str, *, path: Path | None = None) -> list[str]:
    """再開の前に足りない記録。空なら承認してよい（承認そのものは本人）。"""
    st = load_state(path)
    kst = st["keys"].get(key)
    miss: list[str] = []
    if not kst or remedy_id not in kst["suspended"]:
        return [f"『{remedy_id}』は停止中ではありません"]
    incs = [st["incidents"][i] for i in kst["incident_ids"] if i in st["incidents"]]
    if not any(a.get("cause") for i in incs for a in i["annotations"]):
        miss.append("原因の記録（annotate --cause）")
    done = [r for i in incs for r in i["remedies"] if r.get("outcome") in ("success", "failed")]  # 実行した対策だけ
    if not any(r.get("verification") for r in done):
        miss.append("対策と検証結果の記録（remedy --verification）")
    return miss


def approve_resume(key: str, remedy_id: str, approval_note: str, *, path: Path | None = None) -> None:
    """本人が明示承認した時だけ、停止した自動対策を再開する。承認の文言は本人の原文を残す。"""
    note = (approval_note or "").strip()
    if not note:
        raise ValueError("本人の承認の文言が必要です")
    p = path or incidents_path()
    with _locked(p):
        miss = resume_blockers(key, remedy_id, path=p)
        if miss:
            raise ValueError("再開できません。足りない記録: " + "、".join(miss))
        if not _append({"event": "resume_approved", "key": key, "remedy_id": remedy_id,
                        "approval_note": note[:300]}, p):
            raise IncidentLogError("追記できませんでした")


def human_brief(system: str, stage: str, error_code: str | None, *, path: Path | None = None) -> str:
    """未承認・安全条件外の時に本人へ出す『過去事例と対策候補』（短文）。"""
    h = search_history(system, stage, error_code, path=path)
    lines = [f"過去の同一障害 {len(h['exact'])} 件／同じ工程の別障害 {len(h['related'])} 件"]
    for it in (h["exact"] or h["related"])[:3]:
        rem = "・".join(f"{r['remedy_id']}={r['outcome']}" for r in it["remedies"]) or "対策の記録なし"
        cause = "・".join(it["cause_confirmed"] + [f"（推定）{c}" for c in it["cause_inferred"]]) or "原因は未記録"
        lines.append(f"- {it['incident_id']}: {cause}｜{rem}")
    cands = [f"{rid}: {r['label']}" for rid, r in REMEDIES.items() if r.get("approved")]
    lines.append("承認済みの自動対策の候補: " + "／".join(cands))
    return "\n".join(lines)


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="614 障害対応履歴（工程33〜35）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="過去の障害対応を探す")
    s.add_argument("system")
    s.add_argument("stage")
    s.add_argument("--error-code")
    sub.add_parser("list", help="連続回数と停止中の自動対策")
    an = sub.add_parser("annotate", help="原因・関連 decision_id を足す")
    an.add_argument("incident_id")
    an.add_argument("--cause")
    an.add_argument("--kind", choices=("fact", "inferred"), default="inferred")
    an.add_argument("--decision-id", action="append", default=[])
    rm = sub.add_parser("remedy", help="人が行った対策と検証結果を記録")
    rm.add_argument("incident_id")
    rm.add_argument("--remedy-id", required=True)
    rm.add_argument("--outcome", required=True, choices=("success", "failed"))
    rm.add_argument("--verification", required=True)
    ap_ = sub.add_parser("approve-resume", help="本人の明示承認で停止した自動対策を再開")
    ap_.add_argument("key")
    ap_.add_argument("remedy_id")
    ap_.add_argument("--approval", required=True, help="本人の承認の文言（原文）")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "search":
            print(json.dumps(search_history(a.system, a.stage, a.error_code), ensure_ascii=False, indent=2))
        elif a.cmd == "list":
            st = load_state()
            for key, k in sorted(st["keys"].items()):
                print(f"{key}｜連続{k['count']}回｜停止中: {','.join(k['suspended']) or 'なし'}")
        elif a.cmd == "annotate":
            annotate(a.incident_id, cause=a.cause, cause_kind=a.kind, decision_ids=a.decision_id)
            print("追記しました")
        elif a.cmd == "remedy":
            p = incidents_path()
            with _locked(p):
                if a.incident_id not in load_state(p)["incidents"]:
                    raise ValueError(f"incident_id が見つかりません: {a.incident_id}")
                _append({"event": "remedy", "incident_id": a.incident_id, "remedy_id": a.remedy_id,
                         "auto": False, "outcome": a.outcome, "verification": a.verification[:200]}, p)
            print("対策と検証結果を記録しました")
        elif a.cmd == "approve-resume":
            approve_resume(a.key, a.remedy_id, a.approval)
            print("再開を承認として記録しました")
    except (ValueError, IncidentLogError) as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    if a.cmd in ("annotate", "remedy", "approve-resume"):
        try:
            import jarvis_614_knowledge as kn
            kn.regenerate_quiet()
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
