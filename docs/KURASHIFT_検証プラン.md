# KURASHIFT 検証プラン（実装完了後・最後の To-do）

プラン末尾 To-do: **`verification-with-user`**  
実装は先に全部進め、**検証はこのドキュメントに沿ってユーザー確認しながら**実務レベルまで整える。

## 進め方（合意）

| 誰 | 何をするか |
|---|---|
| **Jarvis** | 実装 To-do を先に完了。検証フェーズでは本プランの手順を案内し、指摘をその場で修正 |
| **ユーザー** | V0→V3 を確認。おかしい点・足りない点を検証実行中に伝える |
| **ゴール** | 実務で使える（残高・貸付・αβγ・年次・設定が説明でき、承認境界が守られている） |

検証中に「ここ違う」「この数字が欲しい」と言われたら、実装に戻って直し、同じチェック項目を再確認する。

## 段階

| 段階 | 内容 | 前提 |
|---|---|---|
| **V0 静的** | 型チェック・dry-run・画面 200 | ログイン不要 |
| **V1 設定後** | `/settings` → 週次・契約者貸付 | ソニー等を登録済み |
| **V2 年次** | 実績・αβγ・19不動産・教育・ROI・比較 | Zaim サマリーあり |
| **V3 承認境界** | Theme 承認／Zaim 本番／税 | **明示承認があるときだけ** |

---

## V0 — コード／骨格（ログイン不要）

- [ ] `cd apps/trade-desk && npx tsc --noEmit`
- [ ] `python -m py_compile scripts/jarvis_kurashift_*.py scripts/jarvis_portfolio_weekly.py`
- [ ] `jarvis_portfolio_weekly.py --dry-run` → 資格情報の有無だけ（ブラウザなし）
- [ ] `jarvis_kurashift_lifeplan.py --step ingest_actuals --year 2025 --dry-run`
- [ ] `jarvis_kurashift_secrets.py --status`（値は出ない）
- [ ] アプリ: `/` `/themes` `/portfolio` `/lifeplan` `/settings` `/tax` `/roi`（あれば）が開く
- [ ] Supabase に loan / bloomo 口座がある

## V1 — 秘密・週次・契約者貸付

- [ ] `/settings` で必要キーを保存 → worker 成功 → ジョブ payload が空
- [ ] 週次 `--force` で `sony_life*` と `*_policy_loan` にスナップ
- [ ] `/portfolio` の保険借入合計が実態と合う（ユーザーが金額を見て判定）
- [ ] skipped 理由が説明できる（未設定の口座）

## V2 — ライフプラン

- [ ] 実績取込で `kind=actuals` スナップが増える
- [ ] `/lifeplan` の αβγ ゲージ・19不動産・教育ブロックが読める
- [ ] 目標 20/60/20 との差が分かる
- [ ] 実績 vs 計画比較表が埋まる
- [ ] ROI（CF／返済）が横並びで見える
- [ ] 年次モードで Step1〜4 がキューに入る

## V3 — 承認境界

- [ ] Theme 承認〜完走アシストで **発注なし**（手順メモのみ）
- [ ] `push_zaim` は CSV のみ（confirm なし）
- [ ] （明示時のみ）Zaim 本番・税登録

## V4 — ブランド／Lab（任意）

- [ ] Vercel 表示名 KURASHIFT
- [ ] Lab／立花は鍵が揃うまでスキップ可

---

## 合格の目安

1. Core と保険借入が `/portfolio` で説明できる  
2. `/lifeplan` で αβγ・19・教育・ROI が目標と並べて見える  
3. 秘密がチャット・Git・ジョブに残っていない  
4. 未承認の実弾／Zaim／弥生が動いていない  

## コマンド（貼り付け用）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a

# V0
~/selenium_env/venv/bin/python scripts/jarvis_portfolio_weekly.py --dry-run --force
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_lifeplan.py --step ingest_actuals --year 2025 --dry-run

# V2
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_lifeplan.py --step ingest_actuals --year 2025
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_lifeplan.py --step revise_budget --year 2025

# V1（ログイン後）
~/selenium_env/venv/bin/python scripts/jarvis_portfolio_weekly.py --force
```

プラン: `~/.cursor/plans/ライフプランhq再整理_c37d6392.plan.md`（末尾 `verification-with-user`）  
運用: `docs/運用コマンド一覧.md` §7.6
