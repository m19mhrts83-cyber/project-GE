"""グルコン材料取込: 冪等（処理済みは inbox から消える）と state 記録。外部送信なし。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_glucon_materials_from_drive as m  # noqa: E402


def _setup(tmp_path, monkeypatch):
    inbox, processed = tmp_path / "inbox", tmp_path / "processed"
    inbox.mkdir()
    (inbox / "a.md").write_text("---\ntitle: t\n---\nbody", encoding="utf-8")
    monkeypatch.setattr(m, "_materials_dirs", lambda: (inbox, processed))
    monkeypatch.setattr(m, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(sys, "argv", ["x", "--apply"])
    return inbox


def test_apply_is_idempotent(tmp_path, monkeypatch):
    inbox = _setup(tmp_path, monkeypatch)
    posted: list = []
    monkeypatch.setattr(m, "_post", lambda rows: posted.extend(rows))
    assert m.main() == 0
    assert m.main() == 0  # 2回目は inbox が空
    assert len(posted) == 1
    assert not list(inbox.iterdir())
    st = json.loads((tmp_path / "state.json").read_text())
    assert st["ok"] is True and st["last_ok_at"]


def test_failure_keeps_file_and_records_error(tmp_path, monkeypatch):
    inbox = _setup(tmp_path, monkeypatch)

    def boom(rows):
        raise SystemExit("HTTP 500")

    monkeypatch.setattr(m, "_post", boom)
    try:
        m.main()
    except SystemExit:
        pass
    assert (inbox / "a.md").exists()
    st = json.loads((tmp_path / "state.json").read_text())
    assert st["ok"] is False and "last_ok_at" not in st
