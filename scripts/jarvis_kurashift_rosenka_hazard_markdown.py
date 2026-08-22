#!/usr/bin/env python3
"""Grok 形式 Markdown のフォールバック出力（案1 最小版・補助線）。

Grok 枠切れ時や Mac 単体確認用。Selenium は --open-chikamap のみ（任意）。
ハザードは自動判定せず 要確認。完成レポートは Grok Bot 本線。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_rosenka_hazard_markdown.py \\
    --address "愛知県岡崎市羽根町" --price-man 1200 --title "岡崎 戸建"
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_rosenka_hazard_markdown.py \\
    --file report.md --send   # estate へ送信（内部・承認不要）
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")
ROSENKA = REPO / "ProgramCode" / "alfred_python" / "rosenka_final.py"


def report_id() -> str:
    return datetime.now().strftime("FALLBACK-%Y%m%d-%H%M%S")


def build_markdown(
    *,
    address: str,
    title: str,
    price_man: str | None,
    url: str | None,
    note: str,
) -> str:
    rid = report_id()
    pm = price_man or ""
    u = url or ""
    return f"""---
source: grok_bot
bot: 物件調査
report_id: {rid}
fallback: jarvis_mac
note: {note}
---

## 物件
- 所在: {address}
- 価格_万: {pm}
- 土地面積: 要確認
- 建物: 要確認
- 駐車場: 不明
- URL: {u}

## 土地評価
- 方式: 要確認
- 路線価_万円_坪: 要確認
- 倍率:
- 土地積算_万円: 要確認
- 土地値100%_比率: 要確認
- 土地値100%判定: 保留
- 根拠URL: https://www.chikamap.jp/chikamap/Map

## ハザード（重ねるハザードマップ）
- 調査URL: https://disaportal.gsi.go.jp/maps/
- 洪水: 要確認
- 土砂: 要確認
- 高潮: 要確認
- 内水: 要確認
- 評価: 要確認
- 根拠URL: https://disaportal.gsi.go.jp/maps/

## 人口（チャプロ軸）
- 評価: 要確認
- 表: （Grok Bot または手動で更新）

## 総合
- 聞く価値: 保留
- 理由1行: Mac フォールバック雛形。路線/HZ は手動または Grok Bot で上書き
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--address", required=True, help="所在（番地まで推奨）")
    ap.add_argument("--title", default="", help="件名短名（未指定なら住所先頭）")
    ap.add_argument("--price-man", default="", help="価格（万）")
    ap.add_argument("--url", default="", help="物件 URL")
    ap.add_argument(
        "--open-chikamap",
        action="store_true",
        help="rosenka_final.py で chikamap を開く（Selenium・ブラウザ残る）",
    )
    ap.add_argument("--out", default="", help="Markdown 保存先（未指定は stdout）")
    ap.add_argument("--send", action="store_true", help="jarvis_grok_report_mail.py --send")
    ap.add_argument("--file", default="", help="--send 時の既存ファイル（--out より優先）")
    args = ap.parse_args()

    title = args.title.strip() or args.address[:30]
    note = "jarvis_kurashift_rosenka_hazard_markdown fallback"
    if args.open_chikamap and ROSENKA.is_file():
        print(f"# open chikamap via {ROSENKA}", file=sys.stderr)
        subprocess.run(
            [str(PY), str(ROSENKA), args.address],
            check=False,
        )
        note += "; chikamap opened — 数値は手動でテンプレ更新"

    body = build_markdown(
        address=args.address,
        title=title,
        price_man=args.price_man or None,
        url=args.url or None,
        note=note,
    )

    out_path = Path(args.file) if args.file else (Path(args.out) if args.out else None)
    if out_path:
        out_path.write_text(body, encoding="utf-8")
        print(f"📎 fallback markdown: {out_path}")
    else:
        print(body)

    if args.send:
        import tempfile

        path = out_path
        if not path:
            tf = tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", delete=False, encoding="utf-8"
            )
            tf.write(body)
            tf.close()
            path = Path(tf.name)
        subject = f"[Grok調査] {title}"
        subprocess.run(
            [
                str(PY),
                "scripts/jarvis_grok_report_mail.py",
                "--file",
                str(path),
                "--subject",
                subject,
                "--send",
            ],
            cwd=str(REPO),
            check=True,
        )
        if not out_path and path.exists():
            path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
