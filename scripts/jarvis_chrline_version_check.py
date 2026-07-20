#!/usr/bin/env python3
"""
CHRLINE-Patch のインストール版と GitHub 最新版を比較し、state に記録・報告ブロックを stdout に出す。

使い方:
  cd ~/git-repos && python3 scripts/jarvis_chrline_version_check.py
  cd ~/git-repos && python3 scripts/jarvis_chrline_version_check.py --force-upstream
  cd ~/git-repos && python3 scripts/jarvis_chrline_version_check.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LINE_POC = REPO / "line_unofficial_poc"
VENV_PATCH_PY = LINE_POC / ".venv-patch" / "bin" / "python"
STATE_PATH = REPO / ".jarvis_state" / "chrline_version.json"
EXAMPLE_PATH = REPO / ".jarvis_state" / "chrline_version.example.json"
UPSTREAM_INIT_URL = (
    "https://raw.githubusercontent.com/WEDeach/CHRLINE-Patch/master/CHRLINE/__init__.py"
)
UPSTREAM_COMMITS_URL = (
    "https://api.github.com/repos/WEDeach/CHRLINE-Patch/commits?per_page=1"
)
CACHE_HOURS = 24


def _parse_version(raw: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in re.split(r"[.\-+]", (raw or "").strip()):
        if not piece:
            continue
        m = re.match(r"(\d+)", piece)
        if m:
            parts.append(int(m.group(1)))
    return tuple(parts) if parts else (0,)


def _version_lt(a: str, b: str) -> bool:
    return _parse_version(a) < _parse_version(b)


def _http_get(url: str, *, timeout: float = 15.0) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "jarvis-chrline-version-check/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _installed_info() -> dict:
    app_version = "9.0.0.3360"
    device = "DESKTOPWIN"
    package_version = ""
    runner = "line_unofficial_poc/run_patch.sh"
    venv_ok = VENV_PATCH_PY.is_file()

    if venv_ok:
        import subprocess

        code = """
import importlib.metadata as m
import os
print(m.version("CHRLINE"))
print(os.environ.get("LINE_CHRLINE_APP_VERSION", "9.0.0.3360"))
print(os.environ.get("LINE_CHRLINE_DEVICE", "DESKTOPWIN"))
"""
        try:
            out = subprocess.run(
                [str(VENV_PATCH_PY), "-c", code],
                cwd=str(LINE_POC),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            lines = [ln.strip() for ln in (out.stdout or "").splitlines() if ln.strip()]
            if lines:
                package_version = lines[0]
            if len(lines) > 1:
                app_version = lines[1]
            if len(lines) > 2:
                device = lines[2]
        except Exception as exc:
            return {
                "venv_ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "package_version": "",
                "app_version": app_version,
                "device": device,
                "runner": runner,
            }

    return {
        "venv_ok": venv_ok,
        "package_version": package_version,
        "app_version": app_version,
        "device": device,
        "runner": runner,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _fetch_upstream(*, force: bool = False) -> dict:
    now = datetime.now(timezone.utc)
    try:
        init_py = _http_get(UPSTREAM_INIT_URL)
        m = re.search(r'__version__\s*=\s*"([^"]+)"', init_py)
        version = m.group(1) if m else ""
        commits_raw = _http_get(UPSTREAM_COMMITS_URL)
        commits = json.loads(commits_raw)
        commit = commits[0] if commits else {}
        sha = (commit.get("sha") or "")[:12]
        commit_date = (commit.get("commit") or {}).get("committer", {}).get("date", "")
        return {
            "version": version,
            "commit_sha": sha,
            "commit_date": commit_date,
            "fetched_at": now.isoformat(),
            "error": "",
        }
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {
            "version": "",
            "commit_sha": "",
            "commit_date": "",
            "fetched_at": now.isoformat(),
            "error": f"{type(exc).__name__}: {exc}",
        }


def _load_state() -> dict:
    if STATE_PATH.is_file():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    if EXAMPLE_PATH.is_file():
        try:
            return json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _should_fetch_upstream(state: dict, *, force: bool) -> bool:
    if force:
        return True
    upstream = state.get("upstream") or {}
    fetched_at = upstream.get("fetched_at")
    if not fetched_at:
        return True
    try:
        ts = datetime.fromisoformat(str(fetched_at).replace("Z", "+00:00"))
        age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
        return age_h >= CACHE_HOURS
    except (TypeError, ValueError):
        return True


def run_version_check(*, force_upstream: bool = False, save: bool = True) -> dict:
    state = _load_state()
    installed = _installed_info()
    if _should_fetch_upstream(state, force=force_upstream):
        upstream = _fetch_upstream(force=force_upstream)
    else:
        upstream = dict(state.get("upstream") or {})

    inst_ver = str(installed.get("package_version") or "")
    up_ver = str(upstream.get("version") or "")
    update_available = bool(inst_ver and up_ver and _version_lt(inst_ver, up_ver))
    last_commit = str((state.get("installed") or {}).get("upstream_commit_sha") or "")
    current_commit = str(upstream.get("commit_sha") or "")
    source_refresh_suggested = bool(
        inst_ver
        and up_ver
        and inst_ver == up_ver
        and current_commit
        and last_commit
        and current_commit != last_commit
    )

    result = {
        "installed": {
            **installed,
            "upstream_commit_sha": current_commit if not update_available else last_commit,
        },
        "upstream": upstream,
        "update_available": update_available,
        "source_refresh_suggested": source_refresh_suggested,
        "last_check_at": datetime.now(timezone.utc).isoformat(),
        "update_command": "cd ~/git-repos && ./scripts/jarvis_chrline_update.sh",
    }
    if save:
        if not update_available and current_commit:
            result["installed"]["upstream_commit_sha"] = current_commit
        _save_state(result)
    return result


def format_version_report(result: dict) -> str:
    installed = result.get("installed") or {}
    upstream = result.get("upstream") or {}
    inst_ver = installed.get("package_version") or "—"
    up_ver = upstream.get("version") or "—"
    lines = [
        "---",
        "📎 CHRLINE バージョン確認",
        f"- インストール: CHRLINE-Patch {inst_ver}（app={installed.get('app_version', '—')} device={installed.get('device', '—')}）",
        f"- GitHub 最新: {up_ver}（commit {upstream.get('commit_sha') or '—'}）",
    ]
    if not installed.get("venv_ok", True):
        lines.append("- venv: .venv-patch 未構築 → docs/運用コマンド一覧.md の CHRLINE-Patch 節を参照")
    if upstream.get("error"):
        lines.append(f"- upstream 取得: 失敗（{str(upstream['error'])[:80]}）")
    if result.get("update_available"):
        lines.append(f"- 判定: 新版あり → 更新推奨（`{result.get('update_command')}`）")
    elif result.get("source_refresh_suggested"):
        lines.append("- 判定: 版番号同一だが GitHub コミット更新あり → ソース上書き更新を検討")
    else:
        lines.append("- 判定: インストール版は最新相当")
    lines.append("---")
    return "\n".join(lines)


def version_update_hint_for_probe_failure() -> str:
    """Square probe NG 時に追記する1行（state 参照のみ・ネットワーク不要）。"""
    state = _load_state()
    if state.get("update_available"):
        up = (state.get("upstream") or {}).get("version") or "?"
        return f"- CHRLINE 更新: 新版 {up} あり → `./scripts/jarvis_chrline_update.sh` で更新後に probe 再実行"
    if state.get("source_refresh_suggested"):
        return "- CHRLINE 更新: 版番号は同一だが GitHub 更新あり → `./scripts/jarvis_chrline_update.sh` を検討"
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CHRLINE-Patch バージョン確認")
    parser.add_argument("--force-upstream", action="store_true", help="upstream をキャッシュ無視で再取得")
    parser.add_argument("--json", action="store_true", help="JSON のみ stdout")
    args = parser.parse_args(argv)

    result = run_version_check(force_upstream=bool(args.force_upstream))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_version_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
