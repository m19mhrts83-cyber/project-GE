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

## 入場（鍵）

- Vercel の jarvis-loopware に `LOOPWARE_ACCESS_KEY` を設定する（判断デスクには件名・相手名が出るため）
- 端末ごとに1回 `/login` で鍵を入れる → 180日有効の Cookie
- Slack からのリンクは `?t=<期限>.<署名>`（7日有効。`lib/access.ts` の `linkToken`）でそのまま入れる
- 鍵が未設定の本番では、従来の `/` `/312` `/313` だけ開き、新しい画面と `/api/log` は止める

## 判断ログの書き込み（契約 v1）

- 契約: `lib/decisionContract.ts`（正本。`apps/jarvis-dashboard/lib/decisionContract.ts` は写し）
- 書き込み: `POST /api/log` に `{ decision }` または `{ decisions: [...] }`（最大50件。端末で溜めた分の再送用）
- 今週の粒: `GET /api/log?surface=triage` → 採った／見送った／迷った／未判断…の件数
- 同じ判断の再送は `payload.idem_key` で1行にまとまる（索引: `20261108_owner_decisions_idem_key.sql`）
- テスト: `npm test`（契約・鍵）、`python3 -m unittest scripts/tests/test_decision_contract.py`（写しの一致・Python 経路）

## データ

- 端末: localStorage `loopware_v1`
- サーバ: 312 → `task_loop_*`／313 → `owner_decisions`

### Supabase（jarvis-dashboard PJ）へ適用する順

SQL Editor または CLI で:

1. `apps/jarvis-dashboard/supabase/migrations/20261107_owner_decisions.sql`（未適用なら）
2. `apps/jarvis-dashboard/supabase/migrations/20261107_task_loop.sql`
3. `apps/jarvis-dashboard/supabase/migrations/20261107_owner_decisions_loopware_payload.sql`
4. `apps/jarvis-dashboard/supabase/migrations/20261108_owner_decisions_idem_key.sql`（二重記録防止。未適用でも先に重複を確かめてから入れるので動く）

（MCP 権限が無い環境では Dashboard SQL で手動適用。）

## 関連

- 312: `docs/AIエージェントチーム/…/312_…/docs/ループウェア_入口設計_20261107.md`
- 313: `docs/AIエージェントチーム/…/313_…/docs/ループウェア_出口設計_20261107.md`
