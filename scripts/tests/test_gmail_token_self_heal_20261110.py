import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_gmail_token_health as H

FULL = list(H.GMAIL_SCOPES_215)


def fake_google(granted, fail=False):
    class Creds:
        def __init__(self, info, scopes):
            self.info, self.granted_scopes = info, None

        @classmethod
        def from_authorized_user_info(cls, info, scopes):
            return cls(info, scopes)

        def refresh(self, req):
            if fail:
                raise RuntimeError("invalid_grant")
            self.granted_scopes = granted

        def to_json(self):
            return json.dumps({**self.info, "token": "new"})

    g = types.ModuleType("google")
    sys.modules["google"] = g
    sys.modules["google.auth"] = types.ModuleType("google.auth")
    sys.modules["google.auth.transport"] = types.ModuleType("google.auth.transport")
    req = types.ModuleType("google.auth.transport.requests")
    req.Request = lambda: None
    sys.modules["google.auth.transport.requests"] = req
    sys.modules["google.oauth2"] = types.ModuleType("google.oauth2")
    cm = types.ModuleType("google.oauth2.credentials")
    cm.Credentials = Creds
    sys.modules["google.oauth2.credentials"] = cm


class SelfHealTests(unittest.TestCase):
    def setUp(self):
        self._saved = {k: v for k, v in sys.modules.items() if k == "google" or k.startswith("google.")}

    def tearDown(self):
        for k in [k for k in sys.modules if k == "google" or k.startswith("google.")]:
            del sys.modules[k]
        sys.modules.update(self._saved)

    def _rec(self, t):
        p = Path(t) / "token_estate.json"
        rec = {"refresh_token": "r", "scopes": [FULL[0]]}
        p.write_text(json.dumps(rec))
        return p, rec

    def test_heals_when_google_still_grants_all(self):
        fake_google(FULL)
        with tempfile.TemporaryDirectory() as t:
            p, rec = self._rec(t)
            self.assertTrue(H.try_self_heal(p, rec))
            self.assertEqual(json.loads(p.read_text())["scopes"], FULL)

    def test_no_heal_when_revoked_or_partial(self):
        with tempfile.TemporaryDirectory() as t:
            fake_google(FULL, fail=True)
            p, rec = self._rec(t)
            self.assertFalse(H.try_self_heal(p, rec))
            fake_google(FULL[:1])
            self.assertFalse(H.try_self_heal(p, rec))
            self.assertEqual(json.loads(p.read_text())["scopes"], [FULL[0]])


if __name__ == "__main__":
    unittest.main()
