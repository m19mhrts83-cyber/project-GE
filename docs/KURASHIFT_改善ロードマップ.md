# KURASHIFT 改善ロードマップ（実行トラッキング）

正本プラン: `~/.cursor/plans/kurashift改善プラン_86acd2ee.plan.md`  
検証: `docs/KURASHIFT_検証プラン.md`

## Phase A / QAゲート（2026-08-13 実装）

| ID | 内容 | 状態 |
|---|---|---|
| QA-1/2 | `portfolio_weekly` → `sync_meta` にソース別 status | **実装** |
| QA-3 | Zaim本番 `requireConfirm`＋API `ui_confirmed` | **実装** |
| QA-4/5 | ホーム鮮度・滞留・一部未取得 | **実装** |
| A1 | いまやること＋鮮度カード | **実装** |
| A2 | ソニー no-table フォールバック強化 | **実装（要再実行検証）** |
| A3 | 証憑手動 inbox ジョブ | **実装** |
| A4 | αβγ注記・Step3「記録のみ」 | **実装** |
| A5 | Vercel 自動デプロイ手順 | 下記 |

### デプロイ（A5）

- 本番 URL: https://jarvis-trade-desk.vercel.app
- プロジェクト: `jarvis-trade-desk`（Root: `apps/trade-desk`）
- Git 連携が効かないときは:

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
cd apps/trade-desk && npx vercel deploy --prod --yes --token "$VERCEL_TOKEN"
```

- ダッシュボードは `main` push で自動。trade-desk は Git 連携を Vercel コンソールで確認すること。

### 受け入れ（本番）

- [ ] ホームにソニー失敗がソース名で出る
- [ ] Zaim本番ボタンで confirm が出る／API 直叩きは 400
- [ ] `/tax` で手動取込ボタンがある
- [ ] 週次 `--force` 後に last_full_ok 改善（ソニー）

## Phase B / C

未着手（プランどおり A 完了後に切る）。
