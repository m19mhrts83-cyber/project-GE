#!/usr/bin/env python3
"""AIナビ東京移設: Mac 側の接続先を東京へ切り替える（本人が Mac で実行・2026-11-20）。

値は画面に出さない。やること（--apply）:
1. 東京の service_role 鍵を Supabase の管理 API から取る（.env の SUPABASE_ACCESS_TOKEN_KAMIOOYA を使う）
2. .env.jarvis_private と Q&A チャットボットの scripts/.env を書き換える
   - KAMIOOYA_PROJECT_REF を東京に
   - SUPABASE_URL が旧（ムンバイ）を指しているファイルだけ、SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY を東京に
   - 書き換える前の写しを <ファイル>.before-tokyo-20261120 に残す（初回だけ）
3. gh が使えれば、GitHub の Secret SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY と変数 KAMIOOYA_PROJECT_REF を東京に
   （WeStudy 取込・心拍・講座テーマ案・本番反映ワークフローが読む）
4. --publish を付けると、続けて Raimo を公開し直す（publish_raimo_1346.py。画面と API 定義の URL が東京になる）

戻すとき（--rollback）: 残しておいた写しで .env を元に戻し、GitHub の値も旧へ戻す。そのあと Raimo を公開し直す。

    ~/selenium_env/venv/bin/python scripts/kamiooya_tokyo_switch.py --target sufbsyddqgekvcgadhpv            # 確認だけ
    ~/selenium_env/venv/bin/python scripts/kamiooya_tokyo_switch.py --target sufbsyddqgekvcgadhpv --apply --publish
    ~/selenium_env/venv/bin/python scripts/kamiooya_tokyo_switch.py --target sufbsyddqgekvcgadhpv --rollback --publish
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kamiooya_target  # noqa: E402
from kamiooya_tokyo_secrets import CHATBOT, read_env  # noqa: E402

REPO_SLUG = "m19mhrts83-cyber/project-GE"
SUFFIX = ".before-tokyo-20261120"
OLD_BASE = kamiooya_target.base_url(kamiooya_target.DEFAULT_REF)
ENV_FILES = [Path.home() / "git-repos" / ".env.jarvis_private", CHATBOT / "scripts" / ".env"]
PUBLISH = CHATBOT / "scripts" / "publish_raimo_1346.py"


def service_key(ref: str, token: str) -> str:
    req = urllib.request.Request(f"https://api.supabase.com/v1/projects/{ref}/api-keys?reveal=true",
                                 headers={"Authorization": f"Bearer {token}", "User-Agent": "kamiooya-tokyo-switch/1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        keys = json.loads(r.read().decode())
    for k in keys:
        if k.get("name") == "service_role" and k.get("api_key"):
            return k["api_key"]
    raise SystemExit("東京の service_role 鍵が取れませんでした")


def parse(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            out[k.strip().removeprefix("export ").strip()] = v.strip().strip('"').strip("'")
    return out


def set_keys(text: str, values: dict[str, str]) -> str:
    lines = text.splitlines()
    done = set()
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("#") or "=" not in s:
            continue
        k = s.split("=", 1)[0].strip().removeprefix("export ").strip()
        if k in values:
            lines[i] = f"{k}={values[k]}"
            done.add(k)
    for k, v in values.items():
        if k not in done:
            lines.append(f"{k}={v}")
    return "\n".join(lines) + "\n"


def gh(args: list[str], body: str | None = None) -> bool:
    r = subprocess.run(["gh", *args, "-R", REPO_SLUG], input=body, text=True, capture_output=True)
    return r.returncode == 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--rollback", action="store_true")
    ap.add_argument("--publish", action="store_true")
    a = ap.parse_args(argv)
    if a.target == kamiooya_target.DEFAULT_REF:
        print("旧ではなく東京の ref を指定してください", file=sys.stderr)
        return 2
    new_base = kamiooya_target.base_url(a.target)
    files = [f for f in ENV_FILES if f.exists()]
    has_gh = shutil.which("gh") is not None and subprocess.run(["gh", "auth", "status"], capture_output=True).returncode == 0

    if a.rollback:
        for f in files:
            b = f.with_name(f.name + SUFFIX)
            if b.exists():
                shutil.copy2(b, f)
                print(f"- {f.name}: 切替前に戻しました")
        old = parse(next((f.with_name(f.name + SUFFIX) for f in files if f.with_name(f.name + SUFFIX).exists()), files[0]).read_text(encoding="utf-8"))
        if has_gh and old.get("SUPABASE_URL") == OLD_BASE and old.get("SUPABASE_SERVICE_ROLE_KEY"):
            ok = gh(["secret", "set", "SUPABASE_URL"], OLD_BASE) and gh(["secret", "set", "SUPABASE_SERVICE_ROLE_KEY"], old["SUPABASE_SERVICE_ROLE_KEY"]) \
                and gh(["variable", "delete", "KAMIOOYA_PROJECT_REF"])
            print(f"- GitHub: {'旧へ戻しました' if ok else '戻せませんでした（画面で戻してください）'}")
        os.environ["KAMIOOYA_PROJECT_REF"] = kamiooya_target.DEFAULT_REF
    else:
        env = read_env()
        token = os.environ.get("SUPABASE_ACCESS_TOKEN_KAMIOOYA") or env.get("SUPABASE_ACCESS_TOKEN_KAMIOOYA") \
            or os.environ.get("SUPABASE_ACCESS_TOKEN") or env.get("SUPABASE_ACCESS_TOKEN") or ""
        if not token:
            print("SUPABASE_ACCESS_TOKEN(_KAMIOOYA) が見つかりません（値は表示しません）", file=sys.stderr)
            return 1
        key = service_key(a.target, token)
        print(f"- 東京の鍵: 取得しました（{len(key)}文字・表示しません）")
        for f in files:
            text = f.read_text(encoding="utf-8")
            cur = parse(text)
            values = {"KAMIOOYA_PROJECT_REF": a.target}
            if cur.get("SUPABASE_URL", "").rstrip("/") in (OLD_BASE, new_base):
                values.update({"SUPABASE_URL": new_base, "SUPABASE_SERVICE_ROLE_KEY": key})
            what = "接続先と鍵" if "SUPABASE_URL" in values else "接続先のみ（SUPABASE_URL は神大家以外を指しているので触らない）"
            if not a.apply:
                print(f"- {f.name}: {what} を東京へ書き換えます（確認だけ）")
                continue
            b = f.with_name(f.name + SUFFIX)
            if not b.exists():
                shutil.copy2(f, b)
            f.write_text(set_keys(text, values), encoding="utf-8")
            print(f"- {f.name}: {what} を東京へ書き換えました（元は {b.name}）")
        if not has_gh:
            print("- GitHub: gh が使えないので未変更です（Secret SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY と変数 KAMIOOYA_PROJECT_REF）")
        elif a.apply:
            ok = gh(["secret", "set", "SUPABASE_URL"], new_base) and gh(["secret", "set", "SUPABASE_SERVICE_ROLE_KEY"], key) \
                and gh(["variable", "set", "KAMIOOYA_PROJECT_REF", "--body", a.target])
            print(f"- GitHub: {'東京へ書き換えました' if ok else '書き換えに失敗しました'}")
        else:
            print("- GitHub: Secret 2件と変数1件を東京へ書き換えます（確認だけ）")
        if not a.apply:
            print("確認だけです。--apply で書き換えます")
            return 0
        os.environ["KAMIOOYA_PROJECT_REF"] = a.target

    if a.publish:
        print("- Raimo を公開し直します…")
        r = subprocess.run([sys.executable, str(PUBLISH)], env=os.environ.copy())
        print(f"- Raimo: {'公開しました' if r.returncode == 0 else f'公開に失敗しました（終了コード {r.returncode}）'}")
        return r.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
