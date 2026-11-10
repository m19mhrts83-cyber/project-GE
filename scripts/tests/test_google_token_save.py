import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_google_token_save as s

RO = "https://www.googleapis.com/auth/gmail.readonly"
MOD = "https://www.googleapis.com/auth/gmail.modify"
SEND = "https://www.googleapis.com/auth/gmail.send"


class FakeCreds:
    def __init__(self, rt, scopes):
        self.rt, self.scopes = rt, scopes

    def to_json(self):
        return json.dumps({"token": "t", "refresh_token": self.rt, "scopes": self.scopes})


class SaveTests(unittest.TestCase):
    def test_readonly_refresh_keeps_send(self):
        """11/10 の不具合: readonly で読んで refresh → 上書きで send が消えていた。"""
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "token_estate.json"
            p.write_text(json.dumps({"refresh_token": "R", "scopes": [RO, MOD, SEND]}))
            s.save_creds_keep_scopes(p, FakeCreds("R", [RO]))
            self.assertEqual(json.loads(p.read_text())["scopes"], [RO, MOD, SEND])

    def test_new_consent_uses_new_scopes(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "token.json"
            p.write_text(json.dumps({"refresh_token": "OLD", "scopes": [RO, MOD, SEND]}))
            s.save_creds_keep_scopes(p, FakeCreds("NEW", [RO]))
            self.assertEqual(json.loads(p.read_text())["scopes"], [RO])

    def test_new_file_and_string_scopes(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "x.json"
            s.save_creds_keep_scopes(p, FakeCreds("R", [RO]))
            self.assertEqual(json.loads(p.read_text())["scopes"], [RO])
            out = s.merged_token_json(json.dumps({"refresh_token": "R", "scopes": f"{RO}"}),
                                      {"refresh_token": "R", "scopes": f"{RO} {SEND}"})
            self.assertEqual(json.loads(out)["scopes"], [RO, SEND])


if __name__ == "__main__":
    unittest.main()
