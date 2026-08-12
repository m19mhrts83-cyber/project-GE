#!/usr/bin/env python3
"""生命保険の特別勘定比率スナップショット（スクレイプ優先・失敗時は前回維持）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_insurance_allocations.py
  ~/selenium_env/venv/bin/python scripts/jarvis_insurance_allocations.py --skip-web
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
YAML_PATH = REPO / "config" / "insurance_allocations.yaml"
SNAP_PATH = REPO / ".jarvis_state" / "insurance_allocations_snap.json"


def load_yaml() -> dict[str, Any]:
    if not YAML_PATH.is_file():
        return {}
    return yaml.safe_load(YAML_PATH.read_text(encoding="utf-8")) or {}


def load_snap() -> dict[str, Any]:
    if not SNAP_PATH.is_file():
        return {"accounts": {}, "updated_at": None}
    try:
        return json.loads(SNAP_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"accounts": {}, "updated_at": None}


def save_snap(data: dict[str, Any]) -> None:
    SNAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = date.today().isoformat()
    SNAP_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def merge_view() -> dict[str, Any]:
    """YAML をベースに snap で上書きした表示用ビュー。"""
    base = load_yaml()
    snap = load_snap()
    accounts = dict(base.get("accounts") or {})
    for aid, rec in (snap.get("accounts") or {}).items():
        cur = dict(accounts.get(aid) or {})
        if rec.get("funds"):
            cur["funds"] = rec["funds"]
            cur["as_of"] = rec.get("as_of") or cur.get("as_of")
            cur["source"] = rec.get("source") or "web"
        elif rec.get("source"):
            cur["source"] = rec.get("source")
        if rec.get("as_of"):
            cur["as_of"] = rec.get("as_of")
        if rec.get("monthly_yen") is not None:
            cur["monthly_yen"] = rec["monthly_yen"]
        if rec.get("value_jpy") is not None:
            cur["value_jpy"] = rec["value_jpy"]
        accounts[aid] = cur
    return {
        "reference_account": base.get("reference_account") or "axa_life",
        "advisor": base.get("advisor") or {},
        "accounts": accounts,
        "snap_updated_at": snap.get("updated_at"),
    }


def fund_summary(funds: list[dict[str, Any]] | None) -> str:
    if not funds:
        return "—"
    parts = []
    for f in funds:
        name = str(f.get("name") or "")
        pct = f.get("pct")
        if pct is None:
            continue
        parts.append(f"{name} {pct:g}%")
    return " / ".join(parts) if parts else "—"


def compare_to_reference(
    ref_funds: list[dict[str, Any]] | None,
    other_funds: list[dict[str, Any]] | None,
) -> str:
    if not ref_funds:
        return "基準未取得"
    if not other_funds:
        return "未取得"
    ref_map = {str(f.get("name") or "").strip(): float(f.get("pct") or 0) for f in ref_funds}
    oth_map = {str(f.get("name") or "").strip(): float(f.get("pct") or 0) for f in other_funds}
    # 名前が完全一致しない場合は pct セット比較
    if ref_map == oth_map:
        return "一致"
    # ゆるい: 合計差と最大差
    diffs = []
    keys = set(ref_map) | set(oth_map)
    for k in keys:
        diffs.append(abs(ref_map.get(k, 0) - oth_map.get(k, 0)))
    if not diffs:
        return "未取得"
    max_d = max(diffs)
    if max_d <= 1.0:
        return "ほぼ一致"
    return f"ずれ(最大{max_d:.0f}pt)"


def fetch_axa_into_snap(*, headless: bool) -> dict[str, Any]:
    sys.path.insert(0, str(REPO / "scripts"))
    from jarvis_axa_balance import fetch_axa_balance  # noqa: WPS433

    result = fetch_axa_balance(headless=headless, timeout_ms=90000, save_debug=True)
    funds = [{"name": f.name, "pct": f.pct} for f in (result.funds or [])]
    return {
        "value_jpy": result.value_jpy,
        "funds": funds,
        "as_of": result.funds_as_of or date.today().isoformat(),
        "source": result.funds_source or "web",
        "parser_mode": result.parser_mode,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="保険特別勘定スナップショット")
    ap.add_argument("--skip-web", action="store_true", help="スクレイプせず merge 表示のみ")
    ap.add_argument("--no-headless", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    snap = load_snap()
    snap.setdefault("accounts", {})

    if not args.skip_web:
        if os.environ.get("AXA_MYAXA_ID") and os.environ.get("AXA_MYAXA_PASSWORD"):
            try:
                axa = fetch_axa_into_snap(headless=not args.no_headless)
                prev = dict(snap["accounts"].get("axa_life") or {})
                if axa.get("funds"):
                    prev.update(
                        {
                            "funds": axa["funds"],
                            "as_of": axa["as_of"],
                            "source": "web",
                        }
                    )
                else:
                    # 評価だけ取れた場合も value は更新、funds は前回維持
                    prev["source"] = prev.get("source") or "manual_snapshot"
                    print(
                        "# axa funds: 抽出0件 → 前回スナップショットを維持",
                        file=sys.stderr,
                    )
                prev["value_jpy"] = axa.get("value_jpy")
                snap["accounts"]["axa_life"] = prev
                save_snap(snap)
                print(
                    f"# axa_life: value={axa.get('value_jpy')} "
                    f"funds={len(axa.get('funds') or [])} source={prev.get('source')}",
                    file=sys.stderr,
                )
            except Exception as exc:
                print(f"# axa_life: scrape failed ({exc}) → 前回維持", file=sys.stderr)
        else:
            print("# axa_life: AXA_MYAXA_* 未設定 → skip", file=sys.stderr)

    view = merge_view()
    if args.json:
        print(json.dumps(view, ensure_ascii=False))
    else:
        ref = view.get("reference_account") or "axa_life"
        ref_funds = (view.get("accounts") or {}).get(ref, {}).get("funds") or []
        print(f"reference={ref} snap={view.get('snap_updated_at')}")
        for aid, rec in (view.get("accounts") or {}).items():
            role = rec.get("role") or ""
            vs = "参考" if aid == ref else compare_to_reference(ref_funds, rec.get("funds"))
            print(
                f"- {aid} ({role}): monthly={rec.get('monthly_yen')} "
                f"funds={fund_summary(rec.get('funds'))} vs_axa={vs} "
                f"source={rec.get('source')} as_of={rec.get('as_of')}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
