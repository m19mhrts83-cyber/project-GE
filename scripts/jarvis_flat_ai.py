#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定額 AI だけで文章を作る共通部品（従量課金の AI API は呼ばない）。

松野さんの方針（2026-11-13）: 神大家AIナビ以外は従量課金の AI を使わない。定額の枠で回す。
回す順（松野さん指定）:
  定期処理（batch）       : GenCode → Codex → Cursor → Claude
  ボタンで待つもの（interactive）: Codex → Cursor → Claude
    （GenCode は 1 回 5〜30 分かかるため、待つ用途では飛ばす）
上限に当たった係は一定時間休ませて次へ回す。どの係も追加購入・従量には進まない。
Genspark（GenCode）はクレジット残が 500 未満なら使わない（松野さん 2026-11-13）。

Mac 専用（各 CLI は Mac にだけある）。秘密は .env.jarvis_private（GSK_API_KEY）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_flat_ai.py --status
  ~/selenium_env/venv/bin/python scripts/jarvis_flat_ai.py "1行で自己紹介して"
  ~/selenium_env/venv/bin/python scripts/jarvis_flat_ai.py --interactive "1行で自己紹介して"

環境変数（任意）:
  JARVIS_FLAT_AI_ORDER_BATCH / JARVIS_FLAT_AI_ORDER_INTERACTIVE  例 "codex,cursor,claude"
  JARVIS_FLAT_AI_GENSPARK_MIN_CREDITS（既定 500）
  JARVIS_FLAT_AI_DISABLE=<係名,...>  その係を使わない
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

REPO = Path(__file__).resolve().parents[1]
STATE_PATH = REPO / ".jarvis_state" / "flat_ai" / "state.json"

ORDER_BATCH = ["gencode", "codex", "cursor", "claude"]
ORDER_INTERACTIVE = ["codex", "cursor", "claude"]
LABELS = {"gencode": "GenCode", "codex": "Codex", "cursor": "Cursor", "claude": "Claude"}

# 上限・クレジット切れらしい文言（各 CLI の表現の違いを広めに拾う）
LIMIT_RE = re.compile(
    r"rate.?limit|usage.?limit|limit (?:reached|exceeded)|quota|insufficient|out of credits|"
    r"credit|exceeded|too many requests|\b429\b|upgrade your plan|resets? (?:at|in)|上限|使用量",
    re.I,
)
LIMIT_COOLDOWN = timedelta(hours=1)
GENSPARK_MIN_CREDITS_DEFAULT = 500
# GenCode は 1 回 5〜30 分かかるので、1 回の実行（プロセス）で使うのは既定 1 回まで。2 回目以降は次の係へ。
GENCODE_PER_PROCESS_DEFAULT = 1
_gencode_used = 0


class FlatAIError(RuntimeError):
    """どの定額 AI でも作れなかった。"""


class LimitReached(RuntimeError):
    """その係が上限・残高不足。"""


@dataclass
class FlatResult:
    text: str
    provider: str
    notes: list[str]

    @property
    def label(self) -> str:
        return LABELS.get(self.provider, self.provider)


# ---------------------------------------------------------------- state
def _now() -> datetime:
    return datetime.now(timezone.utc)


def load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict[str, Any]) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(STATE_PATH)
    except Exception as e:  # 状態が書けなくても生成は止めない
        print(f"# flat_ai state save skip: {e}", file=sys.stderr)


def cooling_until(state: dict[str, Any], provider: str) -> datetime | None:
    raw = ((state.get("cooldown") or {}).get(provider) or {}).get("until")
    if not raw:
        return None
    try:
        until = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return until if until > _now() else None


def set_cooldown(state: dict[str, Any], provider: str, reason: str) -> None:
    state.setdefault("cooldown", {})[provider] = {
        "until": (_now() + LIMIT_COOLDOWN).isoformat(),
        "reason": reason[:200],
    }


def record_use(state: dict[str, Any], provider: str, ok: bool) -> None:
    day = datetime.now().strftime("%Y-%m-%d")
    uses = state.setdefault("uses", {}).setdefault(day, {})
    key = f"{provider}:{'ok' if ok else 'fail'}"
    uses[key] = int(uses.get(key, 0)) + 1
    # 直近 14 日分だけ残す
    for old in sorted(state["uses"])[:-14]:
        state["uses"].pop(old, None)


# ---------------------------------------------------------------- helpers
def _find(names: Sequence[str], extra: Sequence[Path] = ()) -> str | None:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    local = Path.home() / ".local" / "bin"
    for n in names:
        p = local / n
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    for p in extra:
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


def _env() -> dict[str, str]:
    """launchd は PATH が短いので、CLI（node 製を含む）が動くよう足す。従量の鍵は渡さない。"""
    env = dict(os.environ)
    extra = [str(Path.home() / ".local" / "bin"), "/opt/homebrew/bin", "/usr/local/bin"]
    env["PATH"] = ":".join(extra + [env.get("PATH") or "/usr/bin:/bin"])
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        env.pop(k, None)
    return env


def _run(cmd: list[str], *, stdin: str | None, timeout: int, cwd: str) -> str:
    try:
        r = subprocess.run(
            cmd, input=stdin, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=_env(),
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"timeout {timeout}s") from e
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    if r.returncode != 0:
        msg = (err or out)[-600:]
        if LIMIT_RE.search(msg):
            raise LimitReached(msg)
        raise RuntimeError(f"exit {r.returncode}: {msg}")
    return out


def strip_fence(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"^```[a-zA-Z]*\s*\n?", "", t)
    t = re.sub(r"\n?```\s*$", "", t)
    return t.strip()


READ_ONLY_NOTE = (
    "【実行ルール】あなたは文章を作るだけです。ファイルの作成・編集・削除、コマンド実行、"
    "外部への送信はしないでください。出力は求められた本文（または JSON）だけ。前置き不要。\n\n"
)


# ---------------------------------------------------------------- providers
def codex_exe() -> str | None:
    return _find(
        ["codex"],
        [Path("/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex")],
    )


def gen_codex(prompt: str, *, timeout: int, images: Sequence[Path] = ()) -> str:
    exe = codex_exe()
    if not exe:
        raise RuntimeError("codex が見つかりません")
    with tempfile.TemporaryDirectory(prefix="flat_ai_codex_") as td:
        out_file = Path(td) / "last.txt"
        cmd = [
            exe, "exec", "--skip-git-repo-check", "--ephemeral",
            "-s", "read-only", "-C", td, "-o", str(out_file),
        ]
        for img in images:
            cmd += ["-i", str(img)]
        cmd.append("-")
        _run(cmd, stdin=READ_ONLY_NOTE + prompt, timeout=timeout, cwd=td)
        text = out_file.read_text(encoding="utf-8").strip() if out_file.exists() else ""
    if not text:
        raise RuntimeError("codex: 空の出力")
    return text


def gen_cursor(prompt: str, *, timeout: int, images: Sequence[Path] = ()) -> str:
    exe = _find(["agent", "cursor-agent"])
    if not exe:
        raise RuntimeError("cursor agent が見つかりません")
    if images:
        prompt += "\n\n【画像ファイル】\n" + "\n".join(str(p) for p in images)
    with tempfile.TemporaryDirectory(prefix="flat_ai_cursor_") as td:
        for img in images:  # ask モードで読めるよう作業場所に写す
            shutil.copy(img, Path(td) / img.name)
        cmd = [exe, "-p", "--trust", "--workspace", td, "--mode", "ask",
               "--output-format", "text", READ_ONLY_NOTE + prompt]
        text = _run(cmd, stdin=None, timeout=timeout, cwd=td)
    if not text:
        raise RuntimeError("cursor: 空の出力")
    return text


def gen_claude(prompt: str, *, timeout: int, images: Sequence[Path] = ()) -> str:
    exe = _find(["claude"])
    if not exe:
        raise RuntimeError("claude が見つかりません")
    with tempfile.TemporaryDirectory(prefix="flat_ai_claude_") as td:
        names = []
        for img in images:
            dst = Path(td) / img.name
            shutil.copy(img, dst)
            names.append(dst.name)
        if names:
            prompt += "\n\n【画像ファイル（この作業場所にあります。Read で読んでください）】\n" + "\n".join(names)
        cmd = [exe, "-p", "--output-format", "text",
               "--disallowedTools", "Bash,Edit,Write,NotebookEdit,WebFetch,WebSearch"]
        if names:
            cmd += ["--allowedTools", "Read"]
        # 従量課金にならないよう API キーは渡さない（_env で外す。サブスクのログインで動かす）
        text = _run(cmd, stdin=READ_ONLY_NOTE + prompt, timeout=timeout, cwd=td)
    if not text:
        raise RuntimeError("claude: 空の出力")
    return text


def genspark_exe() -> str | None:
    return _find(["genspark", "gsk"])


def genspark_credits() -> int | None:
    """Genspark の残クレジット。読めなければ None（読めないときは使わない）。"""
    exe = genspark_exe()
    if not exe or not (os.environ.get("GSK_API_KEY") or "").strip():
        return None
    try:
        r = subprocess.run([exe, "login-info", "--output", "json"], capture_output=True,
                           text=True, timeout=60, env=_env())
        raw = (r.stdout or "") + "\n" + (r.stderr or "")
    except Exception:
        return None
    try:
        obj = json.loads(r.stdout)
        found = _find_number(obj, ("credit", "balance", "remaining"))
        if found is not None:
            return found
    except Exception:
        pass
    m = re.search(r"(?:credit|balance|remaining)[^\d\n]{0,40}([\d,]+)", raw, re.I)
    return int(m.group(1).replace(",", "")) if m else None


def _find_number(obj: Any, keys: tuple[str, ...]) -> int | None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if any(x in str(k).lower() for x in keys) and isinstance(v, (int, float)) and not isinstance(v, bool):
                return int(v)
        for v in obj.values():
            n = _find_number(v, keys)
            if n is not None:
                return n
    elif isinstance(obj, list):
        for v in obj:
            n = _find_number(v, keys)
            if n is not None:
                return n
    return None


def _longest_text(obj: Any, keys: tuple[str, ...] = ("answer", "result", "content", "text", "output", "message")) -> str:
    best = ""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and any(x in str(k).lower() for x in keys) and len(v) > len(best):
                best = v
            else:
                sub = _longest_text(v, keys)
                if len(sub) > len(best):
                    best = sub
    elif isinstance(obj, list):
        for v in obj:
            sub = _longest_text(v, keys)
            if len(sub) > len(best):
                best = sub
    return best


def gen_gencode(prompt: str, *, timeout: int, images: Sequence[Path] = ()) -> str:
    global _gencode_used
    if images:
        raise RuntimeError("gencode: 画像は扱わない")
    cap = int(os.environ.get("JARVIS_FLAT_AI_GENCODE_PER_PROCESS") or GENCODE_PER_PROCESS_DEFAULT)
    if _gencode_used >= cap:
        raise RuntimeError(f"gencode: この実行での上限 {cap} 回に達したので次へ")
    exe = genspark_exe()
    if not exe:
        raise RuntimeError("genspark CLI が見つかりません")
    floor = int(os.environ.get("JARVIS_FLAT_AI_GENSPARK_MIN_CREDITS") or GENSPARK_MIN_CREDITS_DEFAULT)
    credits = genspark_credits()
    if credits is None:
        raise RuntimeError("gencode: 残クレジットが読めないため使わない")
    if credits < floor:
        raise LimitReached(f"Genspark 残 {credits} < {floor}（残しておく分）")
    cmd = [exe, "task", "create", "super_agent",
           "--task_name", "jarvis-flat-ai",
           "--query", READ_ONLY_NOTE + prompt,
           "--wait", "true", "--output", "json"]
    _gencode_used += 1
    raw = _run(cmd, stdin=None, timeout=max(timeout, 1800), cwd=tempfile.gettempdir())
    try:
        text = _longest_text(json.loads(raw))
    except json.JSONDecodeError:
        text = raw
    text = (text or "").strip()
    if not text:
        raise RuntimeError("gencode: 空の出力")
    return text


PROVIDERS: dict[str, Callable[..., str]] = {
    "gencode": gen_gencode,
    "codex": gen_codex,
    "cursor": gen_cursor,
    "claude": gen_claude,
}


def provider_order(interactive: bool) -> list[str]:
    env = os.environ.get(
        "JARVIS_FLAT_AI_ORDER_INTERACTIVE" if interactive else "JARVIS_FLAT_AI_ORDER_BATCH", ""
    ).strip()
    order = [x.strip() for x in env.split(",") if x.strip()] if env else list(
        ORDER_INTERACTIVE if interactive else ORDER_BATCH
    )
    disabled = {x.strip() for x in (os.environ.get("JARVIS_FLAT_AI_DISABLE") or "").split(",") if x.strip()}
    return [p for p in order if p in PROVIDERS and p not in disabled]


# ---------------------------------------------------------------- main API
def generate(
    prompt: str,
    *,
    interactive: bool = False,
    timeout: int | None = None,
    images: Sequence[Path] = (),
    order: Sequence[str] | None = None,
) -> FlatResult:
    """定額 AI を順に試して文章を返す。全滅なら FlatAIError。従量課金には進まない。"""
    state = load_state()
    notes: list[str] = []
    tmo = timeout or (150 if interactive else 300)
    for p in list(order) if order else provider_order(interactive):
        if images and p == "gencode":
            continue
        until = cooling_until(state, p)
        if until:
            notes.append(f"{LABELS[p]}: 上限で休止中（{until.astimezone().strftime('%H:%M')}まで）")
            continue
        try:
            text = PROVIDERS[p](prompt, timeout=tmo, images=images)
        except LimitReached as e:
            set_cooldown(state, p, str(e))
            record_use(state, p, False)
            notes.append(f"{LABELS[p]}: 上限 → 次へ")
            continue
        except Exception as e:
            record_use(state, p, False)
            notes.append(f"{LABELS[p]}: 失敗（{str(e)[:120]}）→ 次へ")
            continue
        record_use(state, p, True)
        save_state(state)
        return FlatResult(text=strip_fence(text), provider=p, notes=notes)
    save_state(state)
    raise FlatAIError("定額 AI がすべて使えませんでした: " + " / ".join(notes))


def generate_json(prompt: str, **kw: Any) -> tuple[Any, FlatResult]:
    """JSON を返させる。取り出せなければ FlatAIError。"""
    res = generate(prompt, **kw)
    t = res.text
    try:
        return json.loads(t), res
    except json.JSONDecodeError:
        m = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", t)
        if m:
            try:
                return json.loads(m.group(1)), res
            except json.JSONDecodeError:
                pass
    raise FlatAIError(f"{res.label}: JSON を取り出せませんでした")


def status() -> dict[str, Any]:
    state = load_state()
    out: dict[str, Any] = {"providers": {}}
    for p in PROVIDERS:
        finder = {"gencode": genspark_exe, "codex": codex_exe}.get(p)
        exe = finder() if finder else _find(["agent", "cursor-agent"] if p == "cursor" else [p])
        until = cooling_until(state, p)
        out["providers"][p] = {
            "installed": bool(exe),
            "cooldown_until": until.isoformat() if until else None,
        }
    out["order_batch"] = provider_order(False)
    out["order_interactive"] = provider_order(True)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="定額 AI だけで文章を作る")
    ap.add_argument("prompt", nargs="?")
    ap.add_argument("--interactive", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--credits", action="store_true", help="Genspark 残クレジットだけ表示")
    args = ap.parse_args(argv)
    if args.credits:
        print(genspark_credits())
        return 0
    if args.status or not args.prompt:
        print(json.dumps(status(), ensure_ascii=False, indent=2))
        return 0
    try:
        res = generate(args.prompt, interactive=args.interactive)
    except FlatAIError as e:
        print(str(e), file=sys.stderr)
        return 2
    for n in res.notes:
        print(f"# {n}", file=sys.stderr)
    print(f"# via {res.label}", file=sys.stderr)
    print(res.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
