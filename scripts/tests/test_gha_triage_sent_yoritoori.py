"""Slack/Web から送った返信を 5.やり取り.md に残す（クラウド補完, 2026-11-13）."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"))

import jarvis_gha_triage_sent_yoritoori as m  # noqa: E402
from jarvis_gha_partner_gmail_yoritoori import already_in_md  # noqa: E402

MD = """# 317 やり取り

## やり取り（時系列）

### 2026/11/12 13:17｜日本総険｜相手から返信｜いつも…

**件名**: 【御礼】火災保険
本文

---

### 2026/11/06 06:46｜日本総険｜自分から送信｜清水様 いつも…

**件名**: Re: 【再追加資料ご提出の御礼】火災保険
清水様

---
"""


def _row(**kw):
    base = {
        "id": "abc123",
        "folder": "P317_日本総険",
        "partner": "日本総険",
        "subject": "【御礼】火災保険",
        "draft_text": "清水様\n\nありがとうございます。",
        "payload": {"sent_at": "2026-11-12T21:39:25.804Z"},
    }
    base.update(kw)
    return base


class SentYoritooriTest(unittest.TestCase):
    def test_dup_matches_partner_name_not_direction(self):
        # 以前は「｜相手から返信｜」側を相手名として拾い、名前つきの重複判定が効かなかった
        self.assertTrue(already_in_md(MD, "日本総険", "Re: 【再追加資料ご提出の御礼】火災保険", "2026-11-06"))
        self.assertTrue(already_in_md(MD, "日本総険", "【御礼】火災保険", "2026-11-12"))
        self.assertFalse(already_in_md(MD, "日本総険", "Re: 【御礼】火災保険", "2026-11-13"))

    def test_pick_rows(self):
        since = datetime(2026, 11, 6, tzinfo=timezone.utc)
        rows = [
            _row(),
            _row(id="done1", payload={"sent_at": "2026-11-12T00:00:00Z", "yoritoori_appended": True}),
            _row(id="nobody", draft_text=""),
            _row(id="nofolder", folder=""),
            _row(id="old", payload={"sent_at": "2026-10-01T00:00:00Z"}),
        ]
        self.assertEqual([r["id"] for r in m.pick_rows(rows, since=since)], ["abc123"])

    def test_block_inserted_at_top_of_timeline(self):
        block = m.build_sent_block(
            partner_name="日本総険",
            date_str="2026/11/13 06:39",
            subject=m.reply_subject("【御礼】火災保険"),
            body="清水様\n\nありがとうございます。",
        )
        out = m.append_sent(MD, block)
        first = out.split("## やり取り（時系列）", 1)[1].strip().splitlines()[0]
        self.assertTrue(first.startswith("### 2026/11/13 06:39｜日本総険｜自分から送信｜"))
        self.assertTrue(already_in_md(out, "日本総険", "Re: 【御礼】火災保険", "2026-11-13"))


if __name__ == "__main__":
    unittest.main()
