"""閉じた triage 行を pending に戻さないための引き方（id で引く）を確かめる。

2026-11-14: status で全件引いていたため 1000 行で切れ、閉じた行が毎朝 pending に戻っていた。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jarvis_gha_gmail_triage as gmail  # noqa: E402
import jarvis_gha_partner_triage as partner  # noqa: E402


class _Q:
    def __init__(self, db, cap):
        self.db, self.cap, self.f = db, cap, []

    def select(self, *_a):
        return self

    def in_(self, col, vals):
        self.f.append((col, set(vals)))
        return self

    def execute(self):
        rows = [r for r in self.db if all(r[c] in v for c, v in self.f)][: self.cap]
        return type("R", (), {"data": rows})()


class _SB:
    def __init__(self, db, cap=1000):
        self.db, self.cap = db, cap

    def table(self, _name):
        return _Q(self.db, self.cap)


def _db():
    # 閉じた行が 1500 件。目当ての行は最後にある（status だけで引くと 1000 件目で切れる）
    db = [{"id": f"x{i}", "status": "skipped"} for i in range(1500)]
    db.append({"id": "gha-p-target", "status": "skipped"})
    db.append({"id": "gha-p-open", "status": "pending"})
    return db


def test_partner_lookup_finds_closed_row_beyond_cap():
    got = partner.protected_status_by_id(_SB(_db()), ["gha-p-target", "gha-p-open", ""], {"skipped", "sent"})
    assert got == {"gha-p-target": "skipped"}


def test_gmail_lookup_same_behavior():
    got = gmail.protected_status_by_id(_SB(_db()), ["gha-p-target"], {"skipped"})
    assert got == {"gha-p-target": "skipped"}


def test_chunks_many_ids():
    ids = [f"x{i}" for i in range(1500)] + ["gha-p-target"]
    got = partner.protected_status_by_id(_SB(_db(), cap=1000), ids, {"skipped"}, chunk=80)
    assert len(got) == 1501
