#!/usr/bin/env python3
"""Build an offline server-only Raimo definition; never upload it."""
from __future__ import annotations
import argparse
import copy
from pathlib import Path
import yaml

def guard_definition(source: dict) -> dict:
    result = copy.deepcopy(source)
    for route in result['api']:
        # Keep every existing security-maintenance check. Reopening is a separate decision.
        route.setdefault('steps', []).insert(0, {'check': {
            'condition': "input.__gateway_secret == '__RAIMO_AUTH_GATEWAY_SECRET__'",
            'errorCode': 'unauthorized', 'errorMessage': "'認証できません'"}})
    return result

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    data = guard_definition(yaml.safe_load(args.source.read_text()))
    args.output.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    print(f'offline guarded routes: {len(data["api"])}; not published')

if __name__ == '__main__':
    main()
