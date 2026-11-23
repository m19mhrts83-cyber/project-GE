#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""313 系スクリプト共通の Todoist 呼び出し（一時エラーは GET だけ自動再試行）。

- 再試行するのは GET のみ（読み取り）。POST（close・期日変更・コメント）は二重実行を避けるため1回だけ。
- 再試行する失敗: HTTP 429/500/502/503/504・URLError・timeout。待ち 5s/15s/45s（最大4回試行）。
  429 は Retry-After があれば尊重（上限120s）。その他の 4xx は即失敗。
"""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request

BASE = "https://api.todoist.com/api/v1"
RETRY_STATUS = {429, 500, 502, 503, 504}
BACKOFF = (5, 15, 45)
MAX_RETRY_AFTER = 120


def _wait_for(exc: Exception, attempt: int) -> float:
    wait = float(BACKOFF[attempt])
    if isinstance(exc, urllib.error.HTTPError) and exc.code == 429:
        ra = (exc.headers.get("Retry-After") if exc.headers else None) or ""
        try:
            wait = min(float(ra), MAX_RETRY_AFTER)
        except ValueError:
            pass
    return wait


def request(
    method: str,
    path: str,
    token: str,
    body: dict | None = None,
    *,
    timeout: int = 40,
    sleep=time.sleep,
) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"Bearer {token}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    can_retry = method.upper() == "GET"
    attempt = 0
    while True:
        req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
        except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout, TimeoutError) as e:
            transient = (
                e.code in RETRY_STATUS
                if isinstance(e, urllib.error.HTTPError)
                else True  # URLError / timeout
            )
            if not (can_retry and transient) or attempt >= len(BACKOFF):
                raise
            wait = _wait_for(e, attempt)
            attempt += 1
            print(f"⚠ Todoist 一時エラー（{e}）→ {wait:.0f}s 後に再試行 {attempt}/{len(BACKOFF)}", flush=True)
            sleep(wait)
