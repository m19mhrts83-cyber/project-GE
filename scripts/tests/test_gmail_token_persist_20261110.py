import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_gmail_token_persist as P

RO = "https://www.googleapis.com/auth/gmail.readonly"
MOD = "https://www.googleapis.com/auth/gmail.modify"
SEND = "https://www.googleapis.com/auth/gmail.send"


class FakeCreds:
    def __init__(self, scopes):
        self.scopes = scopes

    def to_json(self):
        return json.dumps({"token": "x", "refresh_token": "r", "scopes": self.scopes})


class PersistTests(unittest.TestCase):
    def test_narrow_refresh_keeps_send(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "token_estate.json"
            p.write_text(json.dumps({"refresh_token": "r", "scopes": [RO, MOD, SEND]}))
            P.save_gmail_token(p, FakeCreds([RO]))  # 朝の readonly 読込 → refresh → 保存
            self.assertEqual(set(json.loads(p.read_text())["scopes"]), {RO, MOD, SEND})

    def test_new_file(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "token_x.json"
            P.save_gmail_token(p, FakeCreds([RO]))
            self.assertEqual(json.loads(p.read_text())["scopes"], [RO])


if __name__ == "__main__":
    unittest.main()
