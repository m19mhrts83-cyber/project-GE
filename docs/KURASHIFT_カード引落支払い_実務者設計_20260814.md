# KURASHIFT カード引落支払い — 実務者設計（2026-08-14）

**役割**: 品質点検 → 実務実装の正本  
**顧客意図**: 支払いは重要行為。気づきは Jarvis ダッシュボード、処置は KURASHIFT。寄せ無料優先。借りは返済カレンダー必須。

**本番**
- Dashboard: https://jarvis-dashboard-amber.vercel.app/
- KURASHIFT: https://jarvis-trade-desk.vercel.app/money-ops

## 役割分担

| 層 | 担当 |
|---|---|
| 気づき | Jarvis ダッシュボード（ホームピン・状況ウォッチ） |
| 処置 | KURASHIFT `/money-ops` |
| 年会費 | `card_annual_fee`（本機能と分離） |

## Deep link（固定）

- ホームピン / KURASHIFT Next Action → `/money-ops`（処置）
- 状況ウォッチ・今日のキュー → `/situation?watch=card_debit_watch`（気づき＋ CTA）

## ライフサイクル

| キー | 意味 | 効果 |
|---|---|---|
| `plan_ready_due` | money_ops が consulting/approved/executing | warn → attention（計画作成済み） |
| `settled_due` | money_ops **done** または `--dismiss-due` | 当該 due のアラート解除 |
| `dashboard_ack_due` | ダッシュボード「確認（ピン解除）」 | ホームピンだけ消す（状況ウォッチは残る） |

正本: `.jarvis_state/card_debit_watch.json` ＋ `sync_meta.card_debit_lifecycle`（Vercel 書込 → Mac runner 合流）

## 金額把握ライン（確実に押さえる・2026-08-14）

| 優先 | 手段 | 備考 |
|---|---|---|
| 1 | Gmail「お支払い金額のお知らせ」 | **メールに金額表示ON**のときだけ yen が入る。OFFが既定 |
| 2 | **Vpass Web**（`--fetch-vpass`） | **金額把握の本線**。Myページの「〇月〇日お支払い金額（確定）」を読む。日次は `--fetch-vpass-if-pending` |
| 3 | 手動 `--set` | Vpass/メールで見た額を Jarvis に渡す |

補助: 「お支払い日のご案内」→ 引落日の補強（金額は通常なし）。

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_vpass_payment_fetch.py --json
~/selenium_env/venv/bin/python scripts/jarvis_card_debit_watch.py --fetch-vpass
```

任意（再発防止）: Vpass で「お支払い金額の確定メール表示」をONにすると、優先1が自動で効く。

## 調達・返済の判断（財務プロ・2026-08-14）

- **定額返済の契約者貸付は可**（株再建と同型の強制貯蓄）。必須: 月額・期間・原資を書く。
- 返済は **防衛 → 次物件キープ → NISA9万** のあとの余りから。削るなら不可 → Bloomo。
- 今回（Infinite 約160万・不足約92万）: まず無料寄せ最大化。残りは「定額カレンダー付き貸付」か「Bloomo一部」かハイブリッド。

詳細: `docs/Jarvis_金融相談の出し方_20260814.md` / `jarvis-finance-philosophy.mdc`

## P0 実装

1. **日次収集**: `launchd/dashboard_push_runner.sh` 先頭で `jarvis_card_debit_watch.py` → `situation_watch` → `dashboard_push`
2. **サイクル完了**: settled / plan_ready。money_ops done で sync_meta writeback
3. **due 単位 ack**: `dashboard_ack_due`（汎用7日 ack は SPECIALIZED で除外）
4. **方針**: `jarvis-finance-philosophy.mdc` ＋ UI 貸付注記

## 手動コマンド

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_card_debit_watch.py
~/selenium_env/venv/bin/python scripts/jarvis_card_debit_watch.py \
  --set olive_infinite --amount N --due YYYY-MM-DD
~/selenium_env/venv/bin/python scripts/jarvis_card_debit_watch.py --dismiss-due YYYY-MM-DD
~/selenium_env/venv/bin/python scripts/jarvis_situation_watch.py
~/selenium_env/venv/bin/python scripts/jarvis_dashboard_push.py --watch-only
```

## 禁止

- 自動振込
- あかつき元本・SBIコアの安易な推奨
- 返済カレンダーなしの契約者貸付推奨
- `card_annual_fee` との混同
