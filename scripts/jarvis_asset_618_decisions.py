#!/usr/bin/env python3
"""Explicit voice/chat decision adapter. Default: preview; never watches Slack."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from jarvis_asset_618_runtime import Blocked, DecisionStore, prepare_decision, resolve_decisions


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input', type=Path, required=True, help='Confirmed decision JSON, or read context JSON')
    ap.add_argument('--apply', action='store_true', help='Persist explicit confirmed owner decision')
    ap.add_argument('--owner-confirmed', action='store_true')
    ap.add_argument('--read', action='store_true', help='Read effective decisions, without writing')
    args = ap.parse_args()
    try:
        data = json.loads(args.input.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or (args.apply and args.read):
            raise Blocked('invalid_request')
        if args.read:
            from jarvis_portfolio_weekly import load_private_env, sb_client
            load_private_env()
            result = resolve_decisions(DecisionStore(sb_client()).read(), data['targets'], data['run_id'], retry_of=data.get('retry_of'))
        else:
            row = prepare_decision(data)
            result = {'preview': True, 'surface': row['surface'], 'action': row['action'],
                      'target_ids': row['payload']['asset_618']['targets'],
                      'idem_key': row['payload']['idem_key'], 'writes': 0}
            if args.apply:
                if not args.owner_confirmed:
                    raise Blocked('explicit_owner_confirmation_flag_required')
                from jarvis_portfolio_weekly import load_private_env, sb_client
                load_private_env()
                result = {'persisted': True, 'decision_id': DecisionStore(sb_client()).save(row)}
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (Blocked, ValueError, OSError, KeyError, TypeError) as exc:
        print('# asset618: ' + (str(exc) if isinstance(exc, Blocked) else 'invalid_input'), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
