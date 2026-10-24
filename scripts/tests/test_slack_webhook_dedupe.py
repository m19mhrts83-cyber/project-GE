#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Webhook 投稿側の同一本文 TTL 抑止（3f8c434e）."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load():
    path = SCRIPTS / "jarvis_slack_webhook_post.py"
    spec = importlib.util.spec_from_file_location("jarvis_slack_webhook_post", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


wp = _load()


class TestWebhookDedupe(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        p = mock.patch.object(wp, "DEDUPE_PATH", Path(self._tmp.name) / "dedupe.json")
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self._tmp.cleanup)
        env = mock.patch.dict(os.environ, {"JARVIS_SLACK_DEDUPE_DISABLE": ""})
        env.start()
        self.addCleanup(env.stop)

    def test_same_text_within_ttl_is_duplicate(self):
        key = wp._dedupe_key("report", "本文")
        self.assertIsNone(wp.recent_duplicate_age(key, ttl=1800))
        wp.remember_post(key, ttl=1800)
        self.assertIsNotNone(wp.recent_duplicate_age(key, ttl=1800))

    def test_other_channel_or_text_is_not_duplicate(self):
        wp.remember_post(wp._dedupe_key("report", "本文"), ttl=1800)
        self.assertIsNone(wp.recent_duplicate_age(wp._dedupe_key("ops", "本文"), ttl=1800))
        self.assertIsNone(wp.recent_duplicate_age(wp._dedupe_key("report", "別"), ttl=1800))

    def test_expired_is_not_duplicate(self):
        key = wp._dedupe_key("report", "本文")
        wp.remember_post(key, ttl=60)
        with mock.patch.object(wp.time, "time", return_value=time.time() + 120):
            self.assertIsNone(wp.recent_duplicate_age(key, ttl=60))

    def test_disable_env(self):
        key = wp._dedupe_key("report", "本文")
        wp.remember_post(key, ttl=1800)
        with mock.patch.dict(os.environ, {"JARVIS_SLACK_DEDUPE_DISABLE": "1"}):
            self.assertIsNone(wp.recent_duplicate_age(key, ttl=1800))


if __name__ == "__main__":
    unittest.main()
