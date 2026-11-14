# -*- coding: utf-8 -*-
"""Pages に出すのは HTML と、その HTML が読み込む・リンクするファイルだけ（リンクの無い .md は出さない）。"""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pcp", REPO / "scripts" / "pages_collect_public.py")
pcp = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(pcp)


class CollectTest(unittest.TestCase):
    def test_only_html_and_referenced_assets(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "docs"
            (root / "a" / "img").mkdir(parents=True)
            (root / "a" / "page.html").write_text(
                '<link href="s.css"><img src="img/x%20y.png"><a href="notes.md">n</a><a href="d.json">j</a>'
                '<a href="https://example.com/z.png">e</a><a href="../../outside.png">o</a>',
                encoding="utf-8",
            )
            (root / "a" / "s.css").write_text("body{background:url('img/bg.svg')}", encoding="utf-8")
            (root / "a" / "img" / "x y.png").write_bytes(b"x")
            (root / "a" / "img" / "bg.svg").write_text("<svg/>", encoding="utf-8")
            (root / "a" / "notes.md").write_text("秘密", encoding="utf-8")
            (root / "a" / "d.json").write_text("{}", encoding="utf-8")
            (root / "secret.md").write_text("秘密", encoding="utf-8")
            (root / "unlinked.png").write_bytes(b"x")
            (Path(d) / "outside.png").write_bytes(b"x")
            got = {p.relative_to(root.resolve()).as_posix() for p in pcp.collect(root)}
        self.assertEqual(got, {"a/page.html", "a/s.css", "a/img/x y.png", "a/img/bg.svg", "a/notes.md"})


if __name__ == "__main__":
    unittest.main()
