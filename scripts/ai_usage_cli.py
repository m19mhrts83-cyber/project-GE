#!/usr/bin/env python3
"""Claude / Codex / Cursor / Antigravity の使用率を表示する（正本。`~/.local/bin/ai-usage` へコピーして使う）。

インストール: cp scripts/ai_usage_cli.py ~/.local/bin/ai-usage && chmod +x ~/.local/bin/ai-usage
--json で機械向け出力。秘密（トークン）は出力しない。

読めない・古い・制限中を「None%」にしない:
  - 古い値（STALE_MIN 分超）は「古い（N時間前）・割り振りに使えない」と出す。
  - 使用率100%以上は「制限中（回復 ○時）」。回復時刻を過ぎた値は「回復済みのはず（値は古い）」。
"""
import datetime
import glob
import json
import os
import re
import subprocess
import sys
import time

STALE_MIN = 180  # これより古い値は割り振りに使わない


def fmt_reset(ts):
    if not ts:
        return None
    return time.strftime("%m/%d %H:%M", time.localtime(float(ts)))


def fmt_age(age_min):
    if age_min is None:
        return "時刻不明"
    if age_min < 120:
        return f"{age_min}分前"
    if age_min < 48 * 60:
        return f"{age_min // 60}時間前"
    return f"{age_min // 1440}日前"


def window_text(label, w, now, age_min):
    """1つの枠を人が読める文字列にする。w = {used_percent, resets_at_ts}。"""
    pct, rts = w.get("used_percent"), w.get("resets_at_ts")
    if pct is None:
        return f"{label} 読めない（値なし）"
    reset = fmt_reset(rts)
    if rts and float(rts) <= now:
        return f"{label} 回復済みのはず（記録時 {pct:g}%・値は古い）"
    if pct >= 100:
        return f"{label} 制限中（回復 {reset}）"
    return f"{label} {pct:g}%（{reset} 回復）" if reset else f"{label} {pct:g}%"


def line_text(name, windows, now, age_min):
    """windows = [(label, w), ...]。古ければ判断不可と明示する。"""
    body = " / ".join(window_text(l, w, now, age_min) for l, w in windows)
    if age_min is not None and age_min > STALE_MIN:
        return f"{name:7} 【古い（{fmt_age(age_min)}）・割り振りに使えない】 最後の値: {body}"
    return f"{name:7} {body} ※{fmt_age(age_min)}の値"


# ---- Claude: statusLine（~/.local/bin/claude-statusline-usage-tee.sh）が保存した値 ----
def read_claude(now, path=None):
    p = path or os.path.expanduser("~/.local/state/ai-usage/claude.json")
    try:
        d = json.load(open(p))
    except FileNotFoundError:
        return {"error": "まだ記録なし（対話型の Claude を一度動かすと記録される）"}
    rl = d.get("rate_limits") or {}

    def g(k):
        w = rl.get(k) or {}
        return {"used_percent": w.get("used_percentage", w.get("used_percent")), "resets_at_ts": w.get("resets_at")}

    return {"five_hour": g("five_hour"), "weekly": g("seven_day"),
            "age_min": round((now - d.get("saved_at", now)) / 60)}


# ---- Codex: ~/.codex/sessions の token_count イベント ----
def _find_rl(o):
    if isinstance(o, dict):
        if isinstance(o.get("rate_limits"), dict):
            return o["rate_limits"]
        for v in o.values():
            r = _find_rl(v)
            if r:
                return r
    return None


def _parse_ts(s):
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def pick_codex(lines_by_file, now):
    """lines_by_file: 新しい順のファイルごとの行リスト。
    枠（primary/secondary）が入った最新イベントと、それより新しい「使用量制限」エラーを返す。
    limit_id が codex 以外（premium 等）や枠が null のイベントは無視する。"""
    best, limit_err = None, None
    for lines, mtime in lines_by_file:
        for line in reversed(lines):
            if limit_err is None and "hit your usage limit" in line:
                m = re.search(r"try again at ([0-9:]+ ?[AP]M)", line)
                try:
                    ts = _parse_ts(json.loads(line).get("timestamp", "")) or mtime
                except Exception:
                    ts = mtime
                limit_err = {"at": ts, "retry": m.group(1) if m else None}
            if best is None and '"rate_limits"' in line:
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                rl = _find_rl(ev)
                if rl and isinstance(rl.get("primary"), dict):
                    best = (rl, _parse_ts(ev.get("timestamp", "")) or mtime)
            if best and limit_err:
                break
        if best and limit_err:
            break
    return best, limit_err


def read_codex(now, files=None):
    files = files if files is not None else sorted(
        glob.glob(os.path.expanduser("~/.codex/sessions/**/*.jsonl"), recursive=True),
        key=os.path.getmtime, reverse=True)[:30]
    data = []
    for f in files:
        try:
            data.append((open(f, encoding="utf-8", errors="ignore").readlines(), os.path.getmtime(f)))
        except OSError:
            pass
    best, err = pick_codex(data, now)
    out = {}
    if best:
        rl, ts = best

        def g(k):
            w = rl.get(k) or {}
            return {"used_percent": w.get("used_percent"), "resets_at_ts": w.get("resets_at")}

        out = {"five_hour": g("primary"), "weekly": g("secondary"), "age_min": round((now - ts) / 60)}
    if err and (not best or err["at"] > _best_ts(best)):
        out["limit_error"] = err
        out["limited"] = True
        out.setdefault("age_min", round((now - err["at"]) / 60))
    if not out:
        return {"error": "記録なし（Codex の枠情報つきセッションが見つからない）"}
    return out


def _best_ts(best):
    return best[1]


# ---- Cursor: キーチェーンの cursor-agent ログイン → api2.cursor.sh（Connect RPC・Bearer）----
# cookie 方式（cursor.com/api/usage-summary）は、トークンが api_key_token 型になって 401 になるため使わない。
def parse_cursor(d):
    plan = d.get("planUsage") or {}
    end = d.get("billingCycleEnd")
    return {"used_percent": plan.get("totalPercentUsed"),
            "resets_at_ts": int(end) / 1000 if end else None,
            "message": d.get("displayMessage")}


def _cursor_token():
    return subprocess.run(["security", "find-generic-password", "-s", "cursor-access-token", "-a", "cursor-user", "-w"],
                          capture_output=True, text=True, timeout=20).stdout.strip()


def _cursor_token_expiring(tok, now=None, margin_sec=300):
    """JWT の exp が近い（または読めない）なら True。トークン本体は出力しない。"""
    import base64
    try:
        pl = tok.split(".")[1]
        pl += "=" * (-len(pl) % 4)
        exp = json.loads(base64.urlsafe_b64decode(pl)).get("exp")
    except Exception:
        return True
    if not isinstance(exp, (int, float)):
        return True
    return exp - (now if now is not None else time.time()) <= margin_sec


def _cursor_refresh():
    """cursor-agent がキーチェーンの refresh token でアクセストークンを更新する（2026-11 時点で約1時間で失効）。"""
    try:
        subprocess.run(["cursor-agent", "status"], capture_output=True, text=True, timeout=45)
    except Exception:
        pass


def read_cursor():
    import urllib.error
    import urllib.request
    tok = _cursor_token()
    if not tok:
        raise RuntimeError("キーチェーンに Cursor ログインなし（cursor-agent login が必要）")
    if _cursor_token_expiring(tok):
        _cursor_refresh()
        tok = _cursor_token() or tok

    def call(t):
        req = urllib.request.Request(
            "https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage", data=b"{}", method="POST",
            headers={"Authorization": f"Bearer {t}", "Content-Type": "application/json",
                     "Connect-Protocol-Version": "1"})
        return parse_cursor(json.load(urllib.request.urlopen(req, timeout=10)))

    try:
        return call(tok)
    except urllib.error.HTTPError as e:
        if e.code != 401:
            raise
        _cursor_refresh()
        tok2 = _cursor_token()
        if not tok2 or tok2 == tok:
            raise RuntimeError("Cursor のログインが切れた（cursor-agent login で再ログイン）")
        return call(tok2)


# ---- Antigravity: `agy -p /usage --output-format json` ----
def read_antigravity():
    env = dict(os.environ, AGY_CLI_DISABLE_AUTO_UPDATE="true")
    r = subprocess.run([os.path.expanduser("~/.local/bin/agy"), "-p", "/usage", "--output-format", "json",
                        "--print-timeout", "20s"], capture_output=True, text=True, timeout=40, env=env)
    d = None
    for line in (r.stdout or "").splitlines() or [r.stdout]:
        line = line.strip()
        if line.startswith("{"):
            try:
                d = json.loads(line)
                break
            except Exception:
                pass
    if d is None:
        try:
            d = json.loads(r.stdout)
        except Exception:
            pass
    if not d or d.get("status") != "SUCCESS" or (d.get("command") or {}).get("name") != "usage":
        msg = (d or {}).get("error") or (r.stderr or r.stdout or "").strip()[:120] or f"rc={r.returncode}"
        raise RuntimeError(msg)
    groups = []
    for g in d["command"]["data"].get("groups", []):
        for b in g.get("buckets", []):
            if b.get("disabled"):
                continue
            rf, rt = b.get("remaining_fraction"), b.get("reset_time")
            ts = datetime.datetime.fromisoformat(rt.replace("Z", "+00:00")).timestamp() if rt else None
            groups.append({"group": g.get("name"), "window": b.get("window"),
                           "used_percent": None if rf is None else round((1 - float(rf)) * 100, 1),
                           "resets_at_ts": ts})
    return {"buckets": groups, "age_min": 0}


def render(out, now):
    lines = []
    for name, v in out.items():
        if "error" in v:
            lines.append(f"{name:7} 読めない（{v['error']}）")
        elif "buckets" in v:
            wn = {"weekly": "週枠", "five_hour": "5時間枠", "session": "5時間枠"}
            short = {"Gemini Models": "Gemini", "Claude and GPT models": "Claude/GPT"}
            parts = [window_text(f"{short.get(b['group'], b['group'])} {wn.get(b['window'], b['window'])}", b, now, 0)
                     for b in v["buckets"]]
            lines.append(f"{'antigr':7} " + (" / ".join(parts) if parts else "枠情報なし"))
        elif "monthly" in v:
            m = v["monthly"]
            lines.append(line_text(name, [("月枠", m)], now, v.get("age_min", 0)))
        elif v.get("limited") and "five_hour" not in v:
            lines.append(f"{name:7} 制限中（エラー記録・回復目安 {v['limit_error'].get('retry') or '不明'}）"
                         f" ※{fmt_age(v.get('age_min'))}の記録")
        else:
            line = line_text(name, [("5時間枠", v["five_hour"]), ("週枠", v["weekly"])], now, v.get("age_min"))
            if v.get("limited"):
                line += f" ／ 使用量制限エラーを記録（回復目安 {v['limit_error'].get('retry') or '不明'}）"
            lines.append(line)
    return "\n".join(lines)


def main(argv):
    now = time.time()
    out = {}
    out["claude"] = _safe(lambda: read_claude(now))
    out["codex"] = _safe(lambda: read_codex(now))
    out["cursor"] = _safe(lambda: {"monthly": read_cursor(), "age_min": 0})
    out["antigravity"] = _safe(read_antigravity)
    if "--json" in argv:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(render(out, now))


def _safe(fn):
    try:
        return fn()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"[:200]}


if __name__ == "__main__":
    main(sys.argv[1:])
