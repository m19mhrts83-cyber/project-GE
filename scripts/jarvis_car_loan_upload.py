#!/usr/bin/env python3
"""マイカーローン本審査 — 書類Webアップロード（銀行共通CLI）。

使い方:
  # MUFG: 提出フォルダから4点を自動アップロード
  ~/git-repos/scripts/jarvis_car_loan_upload.py --bank mufg_jaccs --upload

  # フォルダ指定・ドライラン
  ~/git-repos/scripts/jarvis_car_loan_upload.py --bank mufg_jaccs --upload \\
    --folder ~/Library/CloudStorage/GoogleDrive-admin@livingsupport-matsu.co.jp/マイドライブ/800_車両購入検討/MINI_CountrymanD_三菱UFJ本審査提出_202606 --dry-run

  # りそな（設定未完了時は手順を表示）
  ~/git-repos/scripts/jarvis_car_loan_upload.py --bank resona --upload --folder ...

  # 登録銀行一覧
  ~/git-repos/scripts/jarvis_car_loan_upload.py --list-banks

正本: scripts/car_loan/configs/*.yaml、.jarvis_state/car_loan.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from car_loan.banks import ADAPTERS  # noqa: E402
from car_loan.banks.registry import expand_path, load_bank_config, list_banks  # noqa: E402


def default_folder(cfg: dict) -> Path | None:
    raw = cfg.get("default_submit_folder", "")
    if not raw:
        return None
    return expand_path(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description="マイカーローン書類Webアップロード")
    parser.add_argument("--bank", help="銀行ID（mufg_jaccs / resona 等）")
    parser.add_argument("--upload", action="store_true", help="書類を自動アップロードして提出完了まで")
    parser.add_argument("--folder", type=Path, help="提出書類フォルダ（未指定時は YAML の default_submit_folder）")
    parser.add_argument("--port", type=int, help="CDP Chrome ポート（YAML 既定を上書き）")
    parser.add_argument("--portal-url", help="りそな等: メール記載の提出URLを直接指定")
    parser.add_argument("--dry-run", action="store_true", help="URL・ファイル一覧のみ表示")
    parser.add_argument("--list-banks", action="store_true", help="設定済み銀行一覧")
    parser.add_argument("--no-state-update", action="store_true", help="car_loan.json を更新しない")
    args = parser.parse_args()

    if args.list_banks:
        for bid in list_banks():
            cfg = load_bank_config(bid)
            status = cfg.get("implementation_status", "ready")
            print(f"  {bid}: {cfg.get('lender')} ({status})")
        return 0

    if not args.bank:
        parser.print_help()
        return 1

    bank_id = args.bank.lower().replace("-", "_")
    adapter = ADAPTERS.get(bank_id)
    if not adapter:
        print(f"未対応の銀行ID: {args.bank}", file=sys.stderr)
        print(f"登録済み: {', '.join(sorted(ADAPTERS))}", file=sys.stderr)
        return 1

    cfg = load_bank_config(bank_id)
    folder = args.folder or default_folder(cfg)
    if not folder and args.upload:
        print("--folder または YAML の default_submit_folder が必要です。", file=sys.stderr)
        return 1

    if not args.upload:
        parser.print_help()
        return 1

    kwargs = {
        "port": args.port,
        "dry_run": args.dry_run,
    }
    if bank_id.startswith("mufg"):
        kwargs["update_state"] = not args.no_state_update
        final = adapter.run_upload(folder, **kwargs)
    else:
        if args.portal_url:
            kwargs["portal_url"] = args.portal_url
        final = adapter.run_upload(folder, **kwargs)

    print(f"📎 完了 URL: {final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
