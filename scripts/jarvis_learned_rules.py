#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ルール帳（各社員フォルダの learned_rules.md）を読んで、候補に効かせる。

ループウェアの「ルールを読む側」。判断ログ（owner_decisions）から 314 が週次で作り、
松野さんが loopware で「採用」したルールだけが ## 確定ルール に入る。

1行1ルール（| 区切り）:

    - R116-001 | hide | from:news@example.com | scope=partner | v1 2026-11-08 | 根拠 1234,1240 | 宣伝メール

  1. ルール番号（R<社員>-<連番>。取り消し・効果測定はこの番号で数える）
  2. 効き目: hide（出さない）/ boost+N（上げる。既定20）/ demote-N（下げる。既定20）
             / rewrite（下書きの言い回し。条件は無くてよい）/ keep（例外：hide・demote を打ち消す）
  3. 条件: from:addr@x / from:@domain / domain:x.co.jp / subject:語 / partner:名 / lane:partner / kind:mail
     「&」で複数（すべて満たすとき）。「*」は全部。
  4. 以降は任意: scope=once|partner|always、版と日付、根拠（判断ログの id）、メモ

節:
  ## 確定ルール … 効かせる（最大10行。超えた分は効かせず警告）
  ## 仮説       … 効かせない（週次で確かめる候補）
  ## 例外       … keep として効かせる
  ## 参照例     … 読むだけ（下書きの手本）

使ったルール番号は候補の applied_rules に入り、triage_items.payload.applied_rules →
DB トリガーで owner_decisions.payload.applied_rules に写る（効いたかを週次で数える）。

  python scripts/jarvis_learned_rules.py docs/.../116_メール要対応係/learned_rules.md   # 中身の点検
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

REPO = Path(__file__).resolve().parents[1]
TEAM = REPO / "docs" / "AIエージェントチーム"
MAX_CONFIRMED = 10
DEFAULT_STEP = 20

# 社員番号 → フォルダ（ルール帳の置き場）
EMPLOYEE_DIRS = {
    "111": "100_連絡・物件動向把握室/111_パートナー連絡整理係",
    "116": "100_連絡・物件動向把握室/116_メール要対応係",
    "211": "200_返信・案内文面制作室/211_返信案内下書き係",
    "814": "800_俯瞰UI・投影更新室/814_Jarvisダッシュボード更新係",
    "815": "800_俯瞰UI・投影更新室/815_KURASHIFT更新係",
}

SECTION_STATUS = {
    "確定ルール": "confirmed",
    "仮説": "hypothesis",
    "例外": "exception",
    "参照例": "example",
}

_ID_RE = re.compile(r"^R[0-9A-Za-z]+-\d{1,4}$")
_EFFECT_RE = re.compile(r"^(hide|keep|rewrite|boost|demote)([+-]\d{1,3})?$")


@dataclass
class Rule:
    id: str
    effect: str
    step: int
    conds: list[tuple[str, str]]
    status: str
    scope: str = "always"
    version: str = ""
    evidence: list[str] = field(default_factory=list)
    note: str = ""
    text: str = ""  # rewrite のときの言い回し（メモ欄）

    def matches(self, row: dict[str, Any]) -> bool:
        if not self.conds:
            return self.effect == "rewrite"
        return all(_cond_ok(k, v, row) for k, v in self.conds)


@dataclass
class RuleBook:
    path: str
    rules: list[Rule]
    warnings: list[str]

    @property
    def confirmed(self) -> list[Rule]:
        return [r for r in self.rules if r.status == "confirmed"]

    @property
    def exceptions(self) -> list[Rule]:
        return [r for r in self.rules if r.status == "exception"]

    @property
    def hypotheses(self) -> list[Rule]:
        return [r for r in self.rules if r.status == "hypothesis"]


def _addr(s: str) -> str:
    m = re.search(r"[\w.+-]+@[\w.-]+", s or "")
    return (m.group(0) if m else (s or "")).strip().lower()


def _cond_ok(key: str, val: str, row: dict[str, Any]) -> bool:
    v = val.strip().lower()
    if key == "*":
        return True
    if key == "from":
        addr = _addr(str(row.get("from_email") or ""))
        return addr.endswith(v) if v.startswith("@") else addr == v
    if key == "domain":
        addr = _addr(str(row.get("from_email") or ""))
        dom = addr.split("@", 1)[-1]
        return dom == v or dom.endswith("." + v)
    if key == "subject":
        return v in str(row.get("subject") or "").lower()
    if key in ("partner", "lane", "kind", "channel", "account"):
        return str(row.get(key) or "").strip().lower() == v
    return False


def _parse_conds(s: str) -> list[tuple[str, str]] | None:
    s = s.strip()
    if s in ("*", "全部"):
        return [("*", "")]
    if s in ("", "-"):
        return []
    out: list[tuple[str, str]] = []
    for part in s.split("&"):
        part = part.strip()
        if ":" not in part:
            return None
        k, v = part.split(":", 1)
        k = k.strip().lower()
        if k not in ("from", "domain", "subject", "partner", "lane", "kind", "channel", "account") or not v.strip():
            return None
        out.append((k, v.strip()))
    return out


def parse_rule_line(line: str, status: str) -> tuple[Rule | None, str | None]:
    body = line.strip()[1:].strip()  # 先頭の「-」を外す
    cols = [c.strip() for c in body.split("|")]
    if len(cols) < 3:
        return None, f"列が足りません: {line.strip()[:80]}"
    rid, eff, cond = cols[0], cols[1].replace(" ", ""), cols[2]
    if not _ID_RE.match(rid):
        return None, f"ルール番号の形が違います: {rid}"
    m = _EFFECT_RE.match(eff)
    if not m:
        return None, f"{rid}: 効き目が分かりません: {eff}"
    effect = m.group(1)
    step = abs(int(m.group(2))) if m.group(2) else DEFAULT_STEP
    conds = _parse_conds(cond)
    if conds is None:
        return None, f"{rid}: 条件が分かりません: {cond}"
    if not conds and effect != "rewrite":
        return None, f"{rid}: 条件がありません（全部に効かせるなら *）"
    r = Rule(id=rid, effect=effect, step=step, conds=conds, status=status)
    rest = cols[3:]
    notes: list[str] = []
    for c in rest:
        if c.startswith("scope="):
            r.scope = c.split("=", 1)[1].strip() or "always"
        elif re.match(r"^v\d+", c):
            r.version = c
        elif c.startswith("根拠"):
            r.evidence = re.findall(r"\d+", c)
        elif c:
            notes.append(c)
    r.note = " / ".join(notes)
    if effect == "rewrite":
        r.text = r.note
    if status == "exception" and effect != "keep":
        r.effect = "keep"
    return r, None


def parse_rulebook(text: str, path: str = "") -> RuleBook:
    rules: list[Rule] = []
    warns: list[str] = []
    status: str | None = None
    seen: set[str] = set()
    for line in text.splitlines():
        h = re.match(r"^##\s+(.+?)\s*$", line)
        if h:
            title = h.group(1)
            status = next((v for k, v in SECTION_STATUS.items() if title.startswith(k)), None)
            continue
        if status is None or status == "example":
            continue
        if not re.match(r"^\s*-\s+R", line):
            continue
        r, err = parse_rule_line(line, status)
        if err:
            warns.append(err)
            continue
        assert r is not None
        if r.id in seen:
            warns.append(f"{r.id}: 番号が重複しています（後の行は無視）")
            continue
        seen.add(r.id)
        rules.append(r)
    conf = [r for r in rules if r.status == "confirmed"]
    if len(conf) > MAX_CONFIRMED:
        over = {r.id for r in conf[MAX_CONFIRMED:]}
        warns.append(f"確定ルールが {len(conf)} 行（上限 {MAX_CONFIRMED}）。{', '.join(sorted(over))} は効かせません")
        rules = [r for r in rules if r.id not in over]
    return RuleBook(path=path, rules=rules, warnings=warns)


def rulebook_path(employee: str) -> Path | None:
    d = EMPLOYEE_DIRS.get(str(employee))
    return (TEAM / d / "learned_rules.md") if d else None


def load_rulebook(employee: str) -> RuleBook:
    """無ければ空。読めなくても本線は止めない"""
    p = rulebook_path(employee)
    if not p or not p.exists():
        return RuleBook(path=str(p or ""), rules=[], warnings=[])
    try:
        return parse_rulebook(p.read_text(encoding="utf-8"), str(p))
    except Exception as e:  # noqa: BLE001 — soft-fail
        return RuleBook(path=str(p), rules=[], warnings=[f"読めません: {e}"])


@dataclass
class Applied:
    hidden: bool
    delta: int
    rule_ids: list[str]


def apply_to_row(book: RuleBook, row: dict[str, Any]) -> Applied:
    """1件に効かせる。keep（例外）が当たれば hide・demote は打ち消す"""
    kept = [r for r in book.exceptions if r.matches(row)]
    hidden = False
    delta = 0
    ids: list[str] = [r.id for r in kept]
    for r in book.confirmed:
        if r.effect == "rewrite" or not r.matches(row):
            continue
        if kept and r.effect in ("hide", "demote"):
            continue
        if r.effect == "hide":
            hidden = True
        elif r.effect == "boost":
            delta += r.step
        elif r.effect == "demote":
            delta -= r.step
        ids.append(r.id)
    return Applied(hidden=hidden, delta=delta, rule_ids=ids)


def rewrite_lines(book: RuleBook, row: dict[str, Any] | None = None) -> list[tuple[str, str]]:
    """下書きプロンプトに足す言い回しルール（番号, 文）。row を渡せば当たるものだけ"""
    out = []
    for r in book.confirmed:
        if r.effect != "rewrite" or not r.text:
            continue
        if row is not None and r.conds and not r.matches(row):
            continue
        out.append((r.id, r.text))
    return out


def _main(argv: Iterable[str]) -> int:
    args = list(argv)
    if not args:
        print(__doc__)
        return 0
    rc = 0
    for a in args:
        book = parse_rulebook(Path(a).read_text(encoding="utf-8"), a)
        print(f"# {a}")
        for r in book.rules:
            conds = " & ".join(f"{k}:{v}" if k != "*" else "*" for k, v in r.conds) or "-"
            print(f"  {r.status:<10} {r.id:<10} {r.effect:<7} {conds}  {r.note}")
        for w in book.warnings:
            print(f"  ⚠ {w}")
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
