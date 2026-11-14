#!/usr/bin/env python3
"""Read-only evidence inventory; optional, explicitly enabled temporary Slack report.

No collectors, financial login, image download or AI API calls. Default: draft only.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import urllib.request

from jarvis_asset_618_report import JST, build_report, db_client, paged, read_database, safe_ref, valid_day

LABELS = {
    'axa_life': 'アクサ', 'akatsuki_bond': 'あかつき', 'bloomo': 'Bloomo',
    'sbi_index': 'SBI証券', 'mhi_stock': '持株', 'tachibana_trade': '立花',
    'sony_life': 'ソニー契約A', 'sony_life_chikage': 'ソニー契約B',
    'sony_life_sovani': 'ソニーSOVANI', 'sony_life_sovani_kids': 'ソニー子ども契約',
    'sony_life_policy_loan': 'ソニー貸付A', 'sony_life_chikage_policy_loan': 'ソニー貸付B',
    'prudential_life': 'プルデンシャルA', 'prudential_life_chikage': 'プルデンシャルB',
    'prudential_life_policy_loan': 'プル貸付A', 'prudential_life_chikage_policy_loan': 'プル貸付B',
    'kyoto_kariya': '京都銀行', 'meigin': '名古屋銀行', 'mufg_apart': '三菱UFJ-A',
    'mufg_toyoake': '三菱UFJ-B', 'ogaki': '大垣共立', 'paypay_bank': 'PayPay銀行',
    'sbinet_alt': '住信SBI-A', 'sbinet_main': '住信SBI-B', 'shiga_kusatsu': '滋賀銀行',
    'smbc_kariya': '三井住友銀行', 'suica': 'Suica', 'tokai_roukin': '東海ろうきん', 'wallet': '現金',
}
END = valid_day('2026-12-12')  # Four weeks; no silent extension.


def read_images(client):
    try:
        # No owner names, paths, image bytes, signed URLs or raw error messages.
        return {'ok': True, 'rows': paged(client.table('asset_evidence_latest').select(
            'id,account_scope,account_id,active_slot,captured_at,source_as_of,last_attempt_status'
        ).order('id'))}
    except Exception:
        return {'ok': False, 'rows': []}


def inventory(database, images, *, now=None):
    now = (now or datetime.now(JST)).astimezone(JST)
    base = build_report({}, database, now=now)
    image_rows = images.get('rows', []) if images.get('ok') else []
    items = []
    for scope, data in database.items():
        if scope not in ('portfolio', 'liquidity'):
            continue
        for account in data.get('accounts', []):
            ident = account['id']
            ref = safe_ref(scope, ident)
            numeric = next((x for x in base['items'] if x['scope'] == scope and x['ref'] == ref), None)
            if numeric is None:
                continue
            rows = [r for r in image_rows if r.get('account_scope') == scope and r.get('account_id') == ident]
            good = [r for r in rows if r.get('active_slot') in ('a', 'b') and r.get('captured_at') and valid_day(r.get('source_as_of'))]
            statuses = {r.get('last_attempt_status') for r in rows}
            image = ('unavailable' if not images.get('ok') else
                     'previous_good_held' if good and statuses.intersection({'failed', 'pending'}) else
                     'registered' if good else 'pending' if 'pending' in statuses else
                     'failed' if 'failed' in statuses else 'not_registered')
            items.append({**numeric, 'label': LABELS.get(ident, ref), 'image': image})
    counts = dict(Counter(x['database'] for x in items))
    image_counts = dict(Counter(x['image'] for x in items))
    result = {'checked_at': now.isoformat(timespec='seconds'), 'target_count': len(items),
              'database_read_failures': base['database_read_failures'],
              'scope_verified': base['scope_verified'], 'database_counts': counts,
              'image_read_ok': bool(images.get('ok')), 'image_counts': image_counts,
              'manual_reference_count': sum(x['source_kind'] == 'manual_reference' for x in items),
              'excluded_cards': sum(len(database.get(s, {}).get('excluded_non_balance', [])) for s in ('portfolio', 'liquidity')),
              'current_write': 'not_verified', 'kurashift_display': 'not_verified', 'items': items}
    result['slack_text'] = make_text(result)
    return result


def make_text(r):
    c, ic = r['database_counts'], r['image_counts']
    saved = c.get('current_week', 0) + c.get('older', 0)
    gaps = [x['label'] for x in r['items'] if x['database'] == 'missing']
    old = [x['label'] for x in r['items'] if x['database'] == 'older']
    if old and all(x.startswith('ソニー') for x in old):
        old = [f'ソニー{len(old)}件（詳細は対象別一覧）']
    portfolio_saved = sum(x['scope'] == 'portfolio' and x['database'] in ('current_week', 'older') for x in r['items'])
    cash_saved = sum(x['scope'] == 'liquidity' and x['database'] in ('current_week', 'older') for x in r['items'])
    normal = r['scope_verified'] and not r['database_read_failures'] and r['image_read_ok']
    return '\n\n'.join([
        '【報告】618 資産証拠・日次確認',
        r['checked_at'][:10] + (' 確認処理は正常' if normal else ' 確認処理に読取障害'),
        f"数値DB：記録あり{saved}/{r['target_count']}件\n今週{c.get('current_week', 0)}／古い{c.get('older', 0)}／未取得{c.get('missing', 0)}",
        f"DB読取障害：{r['database_read_failures']}件\n未来日付：{c.get('invalid_date', 0)}対象",
        f"保存先：Supabase\n資産・保険等{portfolio_saved}／銀行・現金等{cash_saved}件",
        '未取得：' + ('、'.join(gaps) if gaps else 'なし（読取不可の範囲は除く）'),
        '古い記録：' + ('、'.join(old) if old else 'なし（読取不可の範囲は除く）'),
        f"手入力参考値：{r['manual_reference_count']}件\n今週の記録日も取得元の日付保証ではありません",
        (f"正常画像登録：{ic.get('registered', 0) + ic.get('previous_good_held', 0)}対象\n未登録{ic.get('not_registered', 0)}／失敗{ic.get('failed', 0)}／確認待ち{ic.get('pending', 0)}"
         if r['image_read_ok'] else '画像登録状況：読取不可'),
        f"前回正常画像を維持：{ic.get('previous_good_held', 0)}対象\n未登録は撮影失敗を意味しません",
        '今回の数値書込・画面照合：未検証\n登録メタデータ確認のみ。画像本体の再検証なし',
        '数値：https://jarvis-trade-desk.vercel.app/portfolio\n画像：https://jarvis-trade-desk.vercel.app/portfolio/evidence',
        '取り直しの依頼は音声・チャットへ',
    ])


def posting_allowed(now, approved, until):
    day = valid_day(until)
    return approved == 'true' and day is not None and now.date() <= day <= END


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--env-file', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--post', action='store_true')
    args = p.parse_args(argv)
    now = datetime.now(JST)
    try:
        client = db_client(args.env_file)
        database, images = read_database(client), read_images(client)
    except Exception:
        database, images = {}, {'ok': False, 'rows': []}
    result = inventory(database, images, now=now)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'inventory.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    (args.out / 'slack_draft.txt').write_text(result['slack_text'] + '\n')
    if args.post:
        if not posting_allowed(now, os.getenv('ASSET618_REPORT_APPROVED'), os.getenv('ASSET618_REPORT_UNTIL')):
            print('Report saved; posting disabled or expired.')
            return 0 if result['scope_verified'] and not result['database_read_failures'] and result['image_read_ok'] else 2
        webhook = os.getenv('SLACK_WEBHOOK_AI_TEAM_REPORT')
        if not webhook:
            print('Report saved; report webhook unavailable.')
            return 2
        try:
            req = urllib.request.Request(webhook, data=json.dumps({'text': result['slack_text']}).encode(),
                                         headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status != 200 or response.read().strip() != b'ok':
                    raise ValueError('post_failed')
        except Exception:
            print('Report saved; Slack posting failed (not retried).')
            return 2
        print('Report posted.')
    return 0 if result['scope_verified'] and not result['database_read_failures'] and result['image_read_ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
