#!/usr/bin/env python3
"""614 ポイント・還元ウォッチ — 参照用ナレッジの自動生成（第3稿 P2・工程36）。

正本（decisions.jsonl・incidents.jsonl）からプログラムで Markdown を作る。手で直さない（二重管理しない）:
  decisions.md          判断履歴（有効な基準／再判断待ち／参考／履歴）
  incident-playbook.md  障害対応事例（連続回数・停止中の自動対策・事例ごとの事実／原因／対策／検証・承認済み対策）

置き場は非公開側（`614_watch/knowledge/`・フォルダ 0700・ファイル 0600）。理由の原文を含み得るので公開リポには置かない。
参照できるのは Mac 上の許可された人・AI 社員（フォルダの権限と非公開リポ運用）だけ。
同じ入力からは同じ出力（時刻は入力の at だけ使う＝決定論）。`--check` で正本と Markdown の食い違い（手編集）を検出する。
実行時に AI は呼ばない。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_614_decisions as dec  # noqa: E402
import jarvis_614_incidents as inc  # noqa: E402
import jarvis_614_runlog as runlog  # noqa: E402

HEADER = ("<!-- 自動生成: jarvis_614_knowledge.py。手で直さない（正本は {src}）。"
          "直すときは CLI で記録して再生成。 -->\n")


def knowledge_dir() -> Path:
    return runlog.log_dir() / "knowledge"


def _cell(v: object) -> str:
    return str(v if v not in (None, "") else "—").replace("|", "／").replace("\n", " ")


def render_decisions(events: list[dict]) -> str:
    view = dec.fold(events)
    items = sorted(view.values(), key=lambda v: str(v.get("decided_at")))
    lines = [HEADER.format(src="decisions.jsonl"), "# 614 判断履歴", ""]
    eff = [v for v in items if dec.standing_state(v) == "effective"]
    exp = [v for v in items if dec.standing_state(v) == "expired"]
    lines += ["## 有効な基準（採用・次回基準・期限内）", ""]
    lines += _table(eff) if eff else ["（なし）", ""]
    lines += ["## 再判断待ち（期限切れ・適用停止。以前の基準へは自動で戻りません）", ""]
    lines += _table(exp) if exp else ["（なし）", ""]
    lines += ["## 全履歴", ""]
    for v in items:
        state = dec.standing_state(v)
        lines.append(f"### {v['decision_id']}｜{_cell(v['topic'])}")
        lines.append(f"- 判断事項: {_cell(v['item'])}")
        lines.append(f"- AIの提案: {_cell(v.get('ai_proposal'))}")
        lines.append(f"- 本人の選択: {dec.CHOICE_LABEL.get(v['choice'], v['choice'])}（{dec.SCOPE_LABEL.get(v['scope'], v['scope'])}）")
        lines.append(f"- 本人が述べた理由（原文）: {_cell(v.get('reason_text')) if v.get('reason_text') else '理由なし（補作しない）'}")
        lines.append(f"- 対象: {_cell(v.get('target'))}｜期限: {_cell(v.get('expires_at')) if v.get('expires_at') else 'なし'}｜状態: {state}")
        lines.append(f"- run_id: {_cell(v.get('run_id'))}｜incident_id: {_cell(', '.join(v['incident_ids']))}")
        if v["revoked"]:
            lines.append(f"- 取消: {v['revoked_at']}（理由: {_cell(v.get('revoke_reason_text')) if v.get('revoke_reason_text') else '理由なし'}）")
        for h in v["history"][1:]:
            if h.get("event") == "revised":
                lines.append(f"- 改定 {h.get('at')}: " + "、".join(f"{k}={_cell(x)}" for k, x in (h.get("changes") or {}).items()))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _table(items: list[dict]) -> list[str]:
    out = ["| decision_id | 基準 | 選択 | 期限 | 判断事項 |", "|---|---|---|---|---|"]
    for v in items:
        out.append(f"| {v['decision_id']} | {_cell(v['topic'])} | {dec.CHOICE_LABEL.get(v['choice'])} | "
                   f"{_cell(v.get('expires_at'))} | {_cell(v['item'])} |")
    return out + [""]


def render_playbook(events: list[dict]) -> str:
    st = inc.fold(events)
    lines = [HEADER.format(src="incidents.jsonl"), "# 614 障害対応ナレッジ（インシデント・プレイブック）", "",
             "## 事前承認された自動対策", "", "| 対策ID | 内容 | 承認 |", "|---|---|---|"]
    for rid, r in inc.REMEDIES.items():
        lines.append(f"| {rid} | {_cell(r['label'])} | {'承認済み' if r.get('approved') else '未承認（自動実行しない）: ' + _cell(r.get('reason'))} |")
    lines += ["", f"同一障害が連続{inc.SUSPEND_AT}回目になったら、その自動対策は実行しません。再開は原因・対策・検証結果の記録と本人の明示承認が必要です。", "",
              "## 連続回数と停止中の自動対策", ""]
    rows = [(k, v) for k, v in sorted(st["keys"].items())]
    if rows:
        lines += ["| 障害（系統｜工程｜分類｜コード） | 連続回数 | 停止中の自動対策 |", "|---|---|---|"]
        for k, v in rows:
            lines.append(f"| {k} | {v['count']} | {_cell(', '.join(v['suspended']))} |")
    else:
        lines.append("（記録なし）")
    lines += ["", "## 事例（新しい順）", ""]
    for i in sorted(st["incidents"].values(), key=lambda x: str(x.get("at")), reverse=True):
        s = inc._inc_summary(i)
        lines.append(f"### {i['incident_id']}｜{i['key']}")
        lines.append(f"- 発生: {i.get('at')}｜run_id: {_cell(i.get('run_id'))}｜連続{i.get('occurrence_no')}回目")
        lines.append(f"- 事実: {_cell(s['fact'])}")
        lines.append(f"- 原因（確認済み）: {_cell('／'.join(s['cause_confirmed']))}")
        lines.append(f"- 原因（推定）: {_cell('／'.join(s['cause_inferred']))}")
        lines.append(f"- 本人判断: {_cell(', '.join(s['decision_ids']))}")
        if s["remedies"]:
            for r in s["remedies"]:
                lines.append(f"- 対策 {r['remedy_id']}（{'自動' if r['auto'] else '人／未実行'}）: {r['outcome']}｜検証: {_cell(r['verification'])}")
        else:
            lines.append("- 対策: 記録なし")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def generate() -> dict[str, str]:
    """正本から2つの Markdown の本文を作る（書かない）。正本を読めなければ例外。期限切れの判定は実行日（期限が過ぎれば内容が変わる）。"""
    d_events = dec.load_events_strict()
    i_events = inc.load_events_strict()
    return {"decisions.md": render_decisions(d_events), "incident-playbook.md": render_playbook(i_events)}


def write(*, out_dir: Path | None = None) -> list[Path]:
    d = out_dir or knowledge_dir()
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    paths = []
    for name, body in generate().items():
        p = d / name
        tmp = d / f".{name}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
        os.replace(tmp, p)
        paths.append(p)
    return paths


def drift(*, out_dir: Path | None = None) -> list[str]:
    """正本から作り直した内容と今のファイルの違い（手編集・作り忘れ）。"""
    d = out_dir or knowledge_dir()
    bad = []
    for name, body in generate().items():
        p = d / name
        if not p.is_file():
            bad.append(f"{name}: 未生成")
        elif p.read_text(encoding="utf-8") != body:
            bad.append(f"{name}: 正本と食い違い（手で直した可能性。再生成で上書きされます）")
    return bad


def regenerate_quiet() -> bool:
    """記録のたびに呼ぶ。失敗しても記録は有効（本線を止めない）。"""
    try:
        write()
        return True
    except Exception:  # noqa: BLE001
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="614 判断履歴・障害対応ナレッジを正本から自動生成（工程36）")
    ap.add_argument("--check", action="store_true", help="書かずに正本との食い違いを調べる")
    a = ap.parse_args(argv)
    try:
        if a.check:
            bad = drift()
            for b in bad:
                print(b)
            return 1 if bad else 0
        for p in write():
            print(f"生成: {p}")
    except (dec.DecisionLogError, inc.IncidentLogError) as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
