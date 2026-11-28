#!/usr/bin/env python3
"""614 ポイント・還元ウォッチ — ダッシュボード反映の照合（P1・工程17/18）。

push の戻り値 0 は『送れた』であって『画面に出た』ではない。保存済み state から push したあと、
画面（/vpoint・/etc）が読む行（Supabase watch_status の payload）を読み戻し、state と主な値を照合する。
不一致または push 失敗は、保存済み state から最大1回だけ再 push して再照合する。
画面反映の失敗は取得・保存の成功とは別に記録する（月印を取り消さない）。

  vpoint 行      : 年間特典（各カードの基準日・数値・取得元の状態・信頼性・推奨）／テイチャンの最終確認日時
  etc_mileage 行 : 還元履歴の最新（対象月・還元額）

実額は返り値・ログに出さない（不一致の項目名だけ）。人による画面の目視は初回・変更時・障害時が中心（工程18）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_card_benefit_watch as cbw  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
PUSH = REPO / "scripts" / "jarvis_dashboard_push.py"


def _state(name: str) -> dict[str, Any]:
    try:
        d = json.loads((cbw.state_dir() / name).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def card_benefit_view(cb: Any) -> dict[str, Any] | None:
    """画面に出る年間特典の主な値（computed_at など毎回変わる欄は含めない）。"""
    if not isinstance(cb, dict):
        return None
    cards = {}
    for c in cb.get("cards") or []:
        if isinstance(c, dict):
            cards[str(c.get("id"))] = {
                k: c.get(k) for k in ("usage_yen", "usage_as_of", "usage_kind", "source_status", "reliable")
            }
    rec = cb.get("recommendation") if isinstance(cb.get("recommendation"), dict) else {}
    return {"cards": cards, "recommendation": rec.get("line"), "withheld": bool(rec.get("withheld"))}


def expected_for(watch_id: str) -> dict[str, Any]:
    """保存済み state から、その行に出るはずの主な値。"""
    if watch_id == "vpoint":
        cb = cbw.compute_from_files() if cbw.state_path().is_file() else None
        return {
            "card_benefit": card_benefit_view(cb),
            "teiki_last_check_at": _state("teiki_barai_chance.json").get("last_check_at"),
        }
    if watch_id == "etc_mileage":
        hist = [h for h in (_state("etc_monthly.json").get("rebate_history") or []) if isinstance(h, dict)]
        top = hist[0] if hist else {}
        return {"latest_target_month": top.get("target_month"), "latest_rebate_yen": top.get("rebate_yen")}
    raise ValueError(watch_id)


def actual_from_row(watch_id: str, row: dict[str, Any] | None) -> dict[str, Any]:
    payload = (row or {}).get("payload") if isinstance((row or {}).get("payload"), dict) else {}
    if watch_id == "vpoint":
        teiki = payload.get("teiki_barai") if isinstance(payload.get("teiki_barai"), dict) else {}
        return {
            "card_benefit": card_benefit_view(payload.get("card_benefit")),
            "teiki_last_check_at": teiki.get("last_check_at"),
        }
    hist = [h for h in (payload.get("rebate_history") or []) if isinstance(h, dict)]
    top = hist[0] if hist else {}
    return {"latest_target_month": top.get("target_month"), "latest_rebate_yen": top.get("rebate_yen")}


def diff_fields(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    """不一致の項目名（値は出さない）。"""
    out = []
    for k, v in expected.items():
        if isinstance(v, dict) and isinstance(actual.get(k), dict):
            for kk in sorted(set(v) | set(actual[k])):
                if v.get(kk) != actual[k].get(kk):
                    out.append(f"{k}.{kk}")
        elif v != actual.get(k):
            out.append(k)
    return out


def private_env() -> dict[str, str]:
    """.env.jarvis_private の値（Supabase の資格情報など）。ログには出さない。無ければ空。"""
    out: dict[str, str] = {}
    try:
        for line in (REPO / ".env.jarvis_private").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip("\"'")
    except OSError:
        pass
    return out


_last_push_tail = ""


def default_pusher() -> int:
    global _last_push_tail
    py = Path.home() / "selenium_env" / "venv" / "bin" / "python"
    exe = str(py) if py.is_file() else sys.executable
    env = os.environ.copy()
    for k, v in private_env().items():
        env.setdefault(k, v)
    _last_push_tail = ""
    try:
        proc = subprocess.run(
            [exe, str(PUSH), "--watch-only"], cwd=str(REPO), env=env, check=False, timeout=240,
            capture_output=True, text=True,
        )
    except (OSError, subprocess.SubprocessError) as e:
        _last_push_tail = type(e).__name__
        return 1
    if proc.returncode != 0:
        # 失敗の理由が分かるよう最後の1行だけ（値は出さない。長さも抑える）
        lines = [ln for ln in (proc.stderr or proc.stdout or "").strip().splitlines() if ln.strip()]
        _last_push_tail = lines[-1][:120] if lines else ""
    return proc.returncode


def default_row_fetcher(ids: list[str]) -> dict[str, dict[str, Any] | None]:
    import jarvis_dashboard_push as dp  # supabase が要る（無ければ ImportError → unverified）

    for k, v in private_env().items():
        os.environ.setdefault(k, v)
    try:
        sb = dp.client()
    except SystemExit as e:  # 資格情報なし（client() は SystemExit を投げる）→ 読み戻せない＝unverified
        raise RuntimeError("Supabase の資格情報なし") from e
    rows = sb.table("watch_status").select("id,payload,updated_at").in_("id", ids).execute().data or []
    got = {r["id"]: r for r in rows if isinstance(r, dict) and r.get("id")}
    return {i: got.get(i) for i in ids}


def sync_and_verify(
    ids: list[str],
    *,
    pusher: Callable[[], int] | None = None,
    fetcher: Callable[[list[str]], dict[str, dict[str, Any] | None]] | None = None,
    retries: int = 1,
) -> dict[str, Any]:
    """保存済み state から push → 行を読み戻して照合。失敗・不一致は最大 retries 回だけ再 push。

    返り値: {push: success|failed, display: success|failed|unverified, attempts, mismatches, error}
    display=unverified は『読み戻せなかった（資格情報・ネットワーク等）』。成功に数えない。"""
    res: dict[str, Any] = {"push": "failed", "display": "unverified", "attempts": 0, "mismatches": [], "error": ""}
    try:
        return _sync_and_verify(ids, pusher or default_pusher, fetcher or default_row_fetcher, retries, res)
    except Exception as e:  # noqa: BLE001 — 画面反映の失敗で呼び出し元（月印・短報）を落とさない
        res["display"] = "unverified"
        res["error"] = f"画面反映の確認中に想定外のエラー（{type(e).__name__}）"
        return res


def _sync_and_verify(ids, push, fetch, retries, res) -> dict[str, Any]:
    expected = {i: expected_for(i) for i in ids}
    for attempt in range(retries + 1):
        res["attempts"] = attempt + 1
        rc = push()
        res["push"] = "success" if rc == 0 else "failed"
        if rc != 0:
            res["display"] = "unverified"
            res["error"] = f"push exit {rc}" + (f"（{_last_push_tail}）" if _last_push_tail else "")
            continue
        try:
            rows = fetch(ids)
        except Exception as e:  # noqa: BLE001 — 資格情報なし・ネットワーク・ImportError
            res["display"] = "unverified"
            res["error"] = f"読み戻せず（{type(e).__name__}）"
            return res  # 読めない時に再 push しても確認できるようにはならない
        mism: list[str] = []
        for i in ids:
            mism += [f"{i}:{f}" for f in diff_fields(expected[i], actual_from_row(i, rows.get(i)))]
        res["mismatches"] = mism
        if not mism:
            res["display"] = "success"
            res["error"] = ""
            return res
        res["display"] = "failed"
        res["error"] = "画面の値が保存済み state と違う: " + ", ".join(mism[:6])
    return res
