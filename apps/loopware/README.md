# ループウェア（apps/loopware）

312（入口・何を拾うか）と 313（出口・片付け）の判断 UI。  
Jarvis ダッシュボードには載せない。ダッシュ／Slack からリンクで開く。

## 起動

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

- 端末: localStorage `loopware_v1`
- サーバ: 312 → `task_loop_*`／313 → `owner_decisions`

### Supabase（jarvis-dashboard PJ）へ適用する順

SQL Editor または CLI で:

1. `apps/jarvis-dashboard/supabase/migrations/20261107_owner_decisions.sql`（未適用なら）
2. `apps/jarvis-dashboard/supabase/migrations/20261107_task_loop.sql`
3. `apps/jarvis-dashboard/supabase/migrations/20261107_owner_decisions_loopware_payload.sql`

（MCP 権限が無い環境では Dashboard SQL で手動適用。）

## 関連

- 312: `docs/AIエージェントチーム/…/312_…/docs/ループウェア_入口設計_20261107.md`
- 313: `docs/AIエージェントチーム/…/313_…/docs/ループウェア_出口設計_20261107.md`
