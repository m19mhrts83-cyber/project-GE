# Grok-first Step A — 候補1件の手動通し

更新: 2026-08-22  
正本プラン: 物件調査 Grok-first（案2 本線）

## 完了条件

1物件で **候補 → Grok 調査 → `[Grok調査]` 送信 → `property_mail_match --apply` → deals 確認** が一周する。

## 手順

### 1. KURASHIFT で候補を確認

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_property_mail_match.py --dry-run
```

- `/realestate/deals` で `status=info|viewing` の行を開く
- **Grok調査用コピー** ボタンで Bot 入力用テキストをクリップボードへ

### 2. Grok 物件調査 Bot

- Instructions 正本: `config/grok_property_bot_grok_paste.md`
- 路線価（chikamap）+ ハザード（disaportal）を調査
- 完了後 **必ず** `matsuno.estate@gmail.com` 宛、件名 `[Grok調査] …` で送信（承認不要）

### 3. 取込

```bash
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_property_mail_match.py --grok-only --apply
```

朝バンドル `jarvis_morning_mac_refresh.py` にも `--grok-only --apply` 組込済み。

### 4. deals 確認

- `source=mail_grok`
- 一行要約: 方式・土地値・HZ・駐車場・人口・聞く
- `聞く` なら `viewing`、HZ除外+見送りなら `passed`

### 5. 第一問合せ（`聞く` 物件のみ・対外は UI 確認）

- プレビュー: `GET /api/re/deals/[id]/inquiry-preview` または deals「第一問い合わせ」
- **倍率**（`grok.land_method`）→ 固定資産税依頼ブロックが自動挿入
- 送信は KURASHIFT UI 2段確認 → `re_deal_inquiry_send`

## 自動検証（fixture）

内部パイプラインのみ（対外 dry-run）:

```bash
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_grok_e2e_runner.py
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_grok_e2e_runner.py --cleanup
```

2026-08-22: **PASS**（`8be466d3` 以降）

## 本番待ち

2026-08-22 の Bot1 実物件3件はすべて `聞く価値: 見送り`（HZ除外）。  
`聞く` の実物件が届いたら §5 まで手動で実施 → `docs/KURASHIFT_re_inquiry_E2E_checklist.md`
