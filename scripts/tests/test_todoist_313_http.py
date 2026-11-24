#!/usr/bin/env python3
"""313 の Todoist 呼び出し再試行のテスト（ネットワーク不要・待ちはダミー）。"""
from __future__ import annotations

import io
import sys
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_todoist_313_http as h  # noqa: E402


def _err(code, retry_after=None):
    hdr = Message()
    if retry_after:
        hdr["Retry-After"] = retry_after
    return urllib.error.HTTPError("u", code, "x", hdr, io.BytesIO(b""))


class _Resp:
    def __init__(self, body=b'{"ok":1}'):
        self._b = body

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _run(side, method="GET"):
    sleeps = []
    with mock.patch.object(h.urllib.request, "urlopen", side_effect=side) as m:
        try:
            r = h.request(method, "/tasks", "t", sleep=sleeps.append)
        except Exception as e:  # noqa: BLE001
            r = e
    return r, m.call_count, sleeps


class T(unittest.TestCase):
    def test_502_502_then_200(self):
        r, n, s = _run([_err(502), _err(502), _Resp()])
        self.assertEqual(r, {"ok": 1})
        self.assertEqual((n, s), (3, [5, 15]))

    def test_four_502_fails(self):
        r, n, s = _run([_err(502)] * 4)
        self.assertIsInstance(r, urllib.error.HTTPError)
        self.assertEqual((n, s), (4, [5, 15, 45]))

    def test_404_immediate(self):
        r, n, s = _run([_err(404)])
        self.assertIsInstance(r, urllib.error.HTTPError)
        self.assertEqual((n, s), (1, []))

    def test_429_retry_after(self):
        r, n, s = _run([_err(429, "7"), _Resp()])
        self.assertEqual((r, n, s), ({"ok": 1}, 2, [7.0]))

    def test_urlerror_and_timeout_retry(self):
        r, n, s = _run([urllib.error.URLError("x"), TimeoutError(), _Resp()])
        self.assertEqual((r, n), ({"ok": 1}, 3))

    def test_post_never_retried(self):
        r, n, s = _run([_err(502), _Resp()], method="POST")
        self.assertIsInstance(r, urllib.error.HTTPError)
        self.assertEqual((n, s), (1, []))


if __name__ == "__main__":
    unittest.main()
