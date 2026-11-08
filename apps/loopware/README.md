# Nody（apps/loopware）

ループウェア型の判断アプリ。名前は Nody（うなずく＝ワンタップで決める）。

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
- `/312?tab=misses` 提案を仕分ける（いろんなソースの候補を 採る／見送る／保留 → コメント → 最後に選ばなかった理由）

## 声でフィードバック

312・313 の下部バーのマイクで、字幕を見ながら声でコメントを残せる（T05「見ながら言う」）。
対象は既定で**いま見ているカード**（スクロールに追従）。**話し始めた時点**のカードに結び付ける。カードをタップすると固定。
話し終えたときに見ている場所が違えば、コメントに「こちらへ移す」が出る（付け替えは `voice_comment_reassigned` として追記）。
確定した文は `/api/feedback` 経由で Supabase `owner_decisions`（surface=`loopware_voice` / action=`voice_comment`）へ追記（削除は `voice_comment_deleted` を足すだけで元の行は残す）。
音声認識はブラウザの Web Speech API（Chrome）。マイク許可が必要。

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
