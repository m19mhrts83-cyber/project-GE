# ループウェア（apps/loopware）

312（入口・何を拾うか）と 313（出口・片付け）の判断 UI。  
Jarvis ダッシュボードには載せない。ダッシュ／Slack からリンクで開く。

## 本番

- URL: https://jarvis-loopware.vercel.app
- Vercel プロジェクト: `jarvis-loopware`（Root Directory = `apps/loopware`）
- デプロイ: `cd ~/git-repos && ./scripts/vercel_loopware_deploy.sh`

## 起動（ローカル）

```bash
cd ~/git-repos/apps/loopware
npm install
# 任意: JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY
npm run dev   # http://127.0.0.1:3004
```

- `/` ハブ
- `/312?topic=seed-aoba` 扱いを決める（S05）
- `/313?task=<todoist_id>` 片付ける

iPhone は **Chrome** 前提。

## データ

- 端末: localStorage `loopware_v1`（各記録に「共有DB／端末のみ」を付ける）
- サーバ: 312 → `task_loop_*`／313 → `owner_decisions`（`lib/decideStore.ts`）
  - 保存に失敗したら API は `persisted:false` を返し、画面は「この端末にだけ保存（共有DBには未保存: 理由）」と出す
  - 312 は同じ話題（topic_text）の topic を使い回し、同じ判断の送り直しは行を増やさない。判断を変えたら前の判断を `history` に積む
  - 313 は1判断1行。同じタスク・同じ判断を10分以内に送り直したら増やさない
  - 313 画面は**判断の記録だけ**。Todoist の完了・期日変更・コメントは 313 の Slack ボタン／CLI
- 週1回 314 が `scripts/jarvis_owner_decisions_weekly.py` で両方の表を読む

テスト: `npm test`（偽の Supabase で保存成功・失敗・送り直し・判断の変更を確認。ネットワーク不要）

### Supabase（jarvis-dashboard PJ）へ適用する順

SQL Editor または CLI で:

1. `apps/jarvis-dashboard/supabase/migrations/20261107_owner_decisions.sql`（未適用なら）
2. `apps/jarvis-dashboard/supabase/migrations/20261107_task_loop.sql`
3. `apps/jarvis-dashboard/supabase/migrations/20261107_owner_decisions_loopware_payload.sql`

（MCP 権限が無い環境では Dashboard SQL で手動適用。）

## 関連

- 312: `docs/AIエージェントチーム/…/312_…/docs/ループウェア_入口設計_20261107.md`
- 313: `docs/AIエージェントチーム/…/313_…/docs/ループウェア_出口設計_20261107.md`
