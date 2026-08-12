# KURASHIFT 検証プラン（一通り実装後にまとめて実施）

実装を先に進め、**検証はバッチで行う**前提のチェックリスト。  
秘密・実弾・Zaim 本番反映は本番データに触るので、最後のブロックで実施。

## 方針

| 段階 | 内容 | いつ |
|---|---|---|
| **V0 静的** | 型チェック・dry-run・DB 行の有無 | 実装直後でも可（自動） |
| **V1 設定後** | `/settings` 反映 → 週次 skipped 解消 | ログイン情報を入れたあと |
| **V2 年次** | 実績取込〜αβγ表示〜スナップ比較 | 1〜2月ウィンドウ or 手動 |
| **V3 本番境界** | Zaim 反映・Theme 承認完走・貸付実額 | 明示承認があるときだけ |

---

## V0 — コード／骨格（ログイン不要）

- [ ] `cd apps/trade-desk && npx tsc --noEmit`
- [ ] `python -m py_compile scripts/jarvis_kurashift_*.py scripts/jarvis_portfolio_weekly.py`
- [ ] `jarvis_portfolio_weekly.py --dry-run` → 資格情報の有無だけ表示（ブラウザなし）
- [ ] `jarvis_kurashift_theme.py --ensure-index-rb --dry-run`
- [ ] `jarvis_kurashift_lifeplan.py --step ingest_actuals --year 2025 --dry-run` → サマリー検出
- [ ] `jarvis_kurashift_secrets.py --status` → set_count 表示（値は出ない）
- [ ] アプリ起動 `apps/trade-desk` : `/` `/themes` `/portfolio` `/lifeplan` `/settings` `/tax` が 200
- [ ] Supabase: `portfolio_accounts` に `*_policy_loan` / `bloomo` 等がある

## V1 — 秘密・週次・契約者貸付（settings 後）

前提: `/settings` でソニー（必要なら Bloomo／PRU）を保存し、Mac worker が成功していること。

- [ ] ジョブ `secrets_upsert` が succeeded、payload が空
- [ ] `sync_meta.kurashift_secrets_status` が更新されている
- [ ] `jarvis_portfolio_weekly.py --force`（またはアプリからキュー）
  - [ ] `sony_life` / `sony_life_chikage` にスナップ
  - [ ] `sony_life_policy_loan` / `sony_life_chikage_policy_loan` に借入残高
- [ ] `/portfolio` の「保険借入」合計が 0 でない（借入がある場合）
- [ ] Bloomo／PRU は設定どおり ok or skipped が説明可能

## V2 — ライフプラン実績・比較

- [ ] `--step ingest_actuals --year 2025`（dry-run なし）→ `kurashift_plan_snapshots` に `kind=actuals`
- [ ] `/lifeplan` に αβγ ゲージと金額が出る
- [ ] `--step revise_budget --year 2025` → gaps（目標との差分）が JSON／state に出る
- [ ] `--step snapshot` → `kind=plan` 行が増える
- [ ] `/lifeplan` の「実績 vs 直近計画」表が埋まる
- [ ] 年次モード `?mode=annual` で Step1〜4 ボタンがジョブを積む

## V3 — 承認境界（壊すとまずいもの）

**やらないこと**: 未承認の実弾・振替・弥生本登録・Zaim 一括 apply。

- [ ] Theme: draft → consulting → approved（確認ダイアログ）→ 完走アシスト  
  → `review_note` に手順のみ。**発注なし**
- [ ] `lifeplan_push_zaim`（`confirm_apply=false`）→ CSV のみ生成
- [ ] （明示時のみ）`confirm_apply=true` → Zaim 予算 1 ヶ月試験 → 年間
- [ ] 税: `--build-csv --dry-run`／証憑 ingest dry-run。本番登録は別承認

## V4 — ブランド／Lab（後回し可）

- [ ] Vercel 表示名 KURASHIFT
- [ ] Lab／立花: 口座・API 鍵が揃うまでスキップ

---

## 合格の目安（まとめて見るとき）

1. Core 網羅と保険借入が `/portfolio` で説明できる  
2. `/lifeplan` で前年 αβγ が目標 20/60/20 と並べて見える  
3. 秘密がチャット・Git・ジョブ payload に残っていない  
4. 実弾・Zaim 本番が「確認なしで動いた」ログが無い  

## 実行コマンド（検証時の貼り付け用）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a

# V0
~/selenium_env/venv/bin/python scripts/jarvis_portfolio_weekly.py --dry-run --force
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_lifeplan.py --step ingest_actuals --year 2025 --dry-run

# V2（実書き込み）
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_lifeplan.py --step ingest_actuals --year 2025
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_lifeplan.py --step revise_budget --year 2025
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_lifeplan.py --step snapshot --year 2026

# V1（ログイン後）
~/selenium_env/venv/bin/python scripts/jarvis_portfolio_weekly.py --force
```

正本プラン: `~/.cursor/plans/ライフプランhq再整理_c37d6392.plan.md`  
運用コマンド: `docs/運用コマンド一覧.md` §7.6
