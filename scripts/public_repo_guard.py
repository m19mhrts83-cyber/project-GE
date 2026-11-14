# -*- coding: utf-8 -*-
"""公開リポに入れてはいけない情報を止める（2026-11-14 松野さん判断）。

project-GE は public。取引先とのやり取り・契約・神大家メンバーの投稿・口座などは
非公開リポ project-GE-private に置く（config/private_paths.txt）。ここでは変更分だけ見る。

止めるもの:
  1. config/private_paths.txt に当たるファイルの追加・変更
  2. 追加した行に出てくる個人情報らしきもの
     - メールアドレス（example.* など見本の宛先、config/public_guard_allow.txt の宛先は除く）
     - 日本の電話番号
     - 「口座」の近くの 7 桁の数字
     - IPv4 アドレス（ローカル・見本用は除く）
     - CSV の見出しに投稿者名・メール・会員番号など
  3. 録音・書き起こし（.srt .vtt .m4a .mp3 .wav）

使い方:
  python3 scripts/public_repo_guard.py --base origin/main            # 手元のブランチの変更
  python3 scripts/public_repo_guard.py --base <sha> --head <sha>      # GHA
  python3 scripts/public_repo_guard.py --staged                       # pre-commit
どうしても公開してよい行は、その行に `public-ok` と書く（理由も添える）。
"""
from __future__ import annotations

import argparse
import fnmatch
import ipaddress
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PRIVATE_LIST = REPO / "config" / "private_paths.txt"
ALLOW_LIST = REPO / "config" / "public_guard_allow.txt"
SELF_FILES = {
    "scripts/public_repo_guard.py",
    "scripts/tests/test_public_repo_guard.py",
    "config/public_guard_allow.txt",
    "config/private_paths.txt",
    ".gitignore",
}

EMAIL_RE = re.compile(r"(?<![\w.%+-])([A-Za-z0-9._%+-]+)@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})\b")
PHONE_RE = re.compile(r"(?<![\d\-])(0\d{1,4}-\d{1,4}-\d{4}|0[789]0\d{8})(?![\d\-])")
ACCOUNT_RE = re.compile(r"口座[^\n]{0,15}?(?<!\d)(\d{7})(?!\d)")
IPV4_RE = re.compile(r"(?<![\d.])((?:\d{1,3}\.){3}\d{1,3})(?![\d.])")
CSV_HEADER_RE = re.compile(r"投稿者名|投稿者メール|member_name|member_no|会員番号|メールアドレス|電話番号|生年月日|マイナンバー|IP ?アドレス")
MEDIA_EXT = {".srt", ".vtt", ".m4a", ".mp3", ".wav"}
# テスト用の見本ドメイン（x.jp・b.jp・*.test など）
SAMPLE_DOMAIN_RE = re.compile(r"^(?:[a-z]{1,2}\.(?:jp|com|net)|.*\.(?:test|invalid|local|localhost|example))$")
SAMPLE_DOMAINS = ("example.com", "example.org", "example.net", "example.jp", "example.co.jp", "example")
# パッケージ名（@types/node 等）やバージョン指定（x@1.2）に当たるものは EMAIL_RE で拾わない形にしてある


def _git(*args: str) -> str:
    return subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=REPO, check=True,
                          capture_output=True, text=True).stdout


def load_patterns(path: Path = PRIVATE_LIST) -> list[str]:
    if not path.exists():
        return []
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            out.append(ln)
    return out


def _match_one(path: str, pat: str) -> bool:
    if pat.endswith("/"):
        return path.startswith(pat) or fnmatch.fnmatch(path, pat + "*")
    if "**" in pat:
        rx = re.escape(pat).replace(r"\*\*/", "(?:.*/)?").replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
        return re.fullmatch(rx, path) is not None
    if "/" in pat:
        return fnmatch.fnmatchcase(path, pat) and path.count("/") == pat.count("/")
    return fnmatch.fnmatchcase(Path(path).name, pat)


def is_private(path: str, patterns: list[str]) -> bool:
    """gitignore と同じく後の行が勝つ。! は除外の取り消し。"""
    hit = False
    for pat in patterns:
        neg = pat.startswith("!")
        p = pat[1:] if neg else pat
        if p.endswith("**/"):
            continue  # ディレクトリの再包含（ファイル判定には使わない）
        if _match_one(path, p):
            hit = not neg
    return hit


def load_allow(path: Path = ALLOW_LIST) -> set[str]:
    if not path.exists():
        return set()
    return {ln.strip().lower() for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")}


def _boring_number(s: str) -> bool:
    digits = re.sub(r"\D", "", s)
    return bool(re.search(r"(\d)\1{3,}", digits)) or "1234" in digits or "5678" in digits


def _mask(s: str) -> str:
    return s[:2] + "…" + s[-2:] if len(s) > 6 else "…"


def scan_line(line: str, allow: set[str]) -> list[str]:
    if "public-ok" in line:
        return []
    hits: list[str] = []
    for m in EMAIL_RE.finditer(line):
        local, domain = m.group(1), m.group(2).lower()
        addr = f"{local}@{domain}".lower()
        if domain.endswith(SAMPLE_DOMAINS) or domain.split(".")[0] == "example" or SAMPLE_DOMAIN_RE.match(domain):
            continue
        if addr in allow or domain in allow or local.lower() in {"noreply", "no-reply"}:
            continue
        if domain.endswith("users.noreply.github.com"):
            continue
        hits.append(f"メールアドレス {_mask(local)}@{domain}")
    for m in PHONE_RE.finditer(line):
        if not _boring_number(m.group(1)):
            hits.append(f"電話番号 {_mask(m.group(1))}")
    for m in ACCOUNT_RE.finditer(line):
        if not _boring_number(m.group(1)):
            hits.append("口座番号らしき 7 桁")
    for m in IPV4_RE.finditer(line):
        try:
            ip = ipaddress.ip_address(m.group(1))
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_unspecified or ip.is_reserved or ip.is_link_local \
                or str(ip).startswith(("192.0.2.", "198.51.100.", "203.0.113.")):
            continue
        hits.append(f"IP アドレス {_mask(str(ip))}")
    return hits


def changed(base: str | None, head: str | None, staged: bool) -> tuple[list[str], dict[str, list[tuple[int, str]]]]:
    if staged:
        names = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines()
        diff = _git("diff", "--cached", "-U0", "--diff-filter=ACMR")
    else:
        rng = [f"{base}...{head or 'HEAD'}"]
        names = _git("diff", "--name-only", "--diff-filter=ACMR", *rng).splitlines()
        diff = _git("diff", "-U0", "--diff-filter=ACMR", *rng)
    added: dict[str, list[tuple[int, str]]] = {}
    cur = None
    ln = 0
    for row in diff.splitlines():
        if row.startswith("+++ "):
            p = row[4:]
            cur = p[2:] if p.startswith("b/") else None
            if cur and cur.startswith('"'):
                cur = cur.strip('"')
            continue
        if row.startswith("@@"):
            m = re.search(r"\+(\d+)", row)
            ln = int(m.group(1)) if m else 0
            continue
        if cur and row.startswith("+"):
            added.setdefault(cur, []).append((ln, row[1:]))
            ln += 1
    return names, added


def check(names: list[str], added: dict[str, list[tuple[int, str]]],
          patterns: list[str], allow: set[str]) -> list[str]:
    problems: list[str] = []
    for n in names:
        if n in SELF_FILES:
            continue
        if is_private(n, patterns):
            problems.append(f"{n}: 非公開リポに置くファイル（config/private_paths.txt）")
        elif Path(n).suffix.lower() in MEDIA_EXT:
            problems.append(f"{n}: 録音・書き起こしは公開リポに置かない")
    for n, rows in added.items():
        if n in SELF_FILES or is_private(n, patterns):
            continue
        for i, (no, text) in enumerate(rows):
            for h in scan_line(text, allow):
                problems.append(f"{n}:{no}: {h}")
            if n.lower().endswith(".csv") and no == 1 and CSV_HEADER_RE.search(text):
                problems.append(f"{n}:1: CSV に個人の列（名前・メール・会員番号など）")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base")
    ap.add_argument("--head")
    ap.add_argument("--staged", action="store_true")
    a = ap.parse_args(argv)
    if not a.staged and not a.base:
        ap.error("--base か --staged を指定")
    names, added = changed(a.base, a.head, a.staged)
    probs = check(names, added, load_patterns(), load_allow())
    if not probs:
        print(f"public guard: OK（{len(names)} ファイル）")
        return 0
    print("public guard: 公開リポに入れてはいけない可能性があるもの", file=sys.stderr)
    for p in probs[:200]:
        print(f"  - {p}", file=sys.stderr)
    print("\n→ 取引先・会員・お金の情報は非公開リポ project-GE-private へ（AGENTS.md「公開リポに入れない情報」）。"
          "\n  見本や公開してよいものなら、その行に `public-ok`（理由つき）を書くか config/public_guard_allow.txt に宛先を足す。",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
