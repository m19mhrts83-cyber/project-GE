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
| A5 | Vercel 自動デプロイ手順 | **実装**（`trade-desk-deploy.yml` + `vercel_trade_desk_deploy.sh`） |

### デプロイ（A5）

- 本番 URL: https://jarvis-trade-desk.vercel.app
- プロジェクト: `jarvis-trade-desk`（Root: `apps/trade-desk`）
- **自動**: `.github/workflows/trade-desk-deploy.yml`（`main` + `apps/trade-desk/**`）
- **手動**（ルートのみ）:

```bash
cd ~/git-repos && ./scripts/vercel_trade_desk_deploy.sh
```

- ダッシュボードは `main` push で自動。trade-desk も同様に Actions 本線（Vercel Git 連携は未使用可）。

### 受け入れ（本番）— Sprint 1 検証中

- [ ] ホームにソニー失敗がソース名で出る
- [ ] Zaim本番ボタンで confirm が出る／API 直叩きは 400
- [ ] `/tax` で手動取込ボタンがある
- [ ] 週次 `--force` 後に last_full_ok 改善（ソニー）または失敗表示の合格

### ローン正本（2026-08-13）

- 旧「本田連携」→ **借入残高トラッカー** https://loan-tracker-plum.vercel.app/（Google: **estate**）

## Phase B / C

未着手（プランどおり A 完了後に切る）。
