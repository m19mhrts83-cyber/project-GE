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
- `/week` 今週の9件（土曜の午前。振り返り→カレンダーに置く→確定）
- `/drafts` 下書きを直す（箇所を選んで声でダメ出し → ダメ出しは箇所ごとに即記録 → 「まとめて直す」で Mac の Cursor（定額）が新しい版 → 差分。判断ログ surface=draft_review。従量課金の API キーは不要）
- `/312?tab=misses` 提案を仕分ける（いろんなソースの候補を 採る／見送る／保留 → コメント → 最後に選ばなかった理由）

## まとめて判断（`/all`）

ジャンルをまたいで1画面で判断する（2026-11-25 松野さん要望・Todoist 6j4hH9FW4rFF7J97）。部品は `lib/allCore.ts`、一覧は `/api/all`。

| ジャンル | 材料 | その場の選択 | 記録・反映（既存の道のまま） |
|---|---|---|---|
| メール | 判断デスク（`loadDeskCards`） | ToDo／済み／見送る／あとで | `/api/desk/decide` |
| 318 要判断 | `sync_meta.todoist_cleanup_snapshot`（origin=318） | 完了／残す | `/api/cleanup` → owner_decisions(todoist_313) → cleanup reflect |
| 313 週の整理 | 同上（origin=313） | 済み／やめる／残す（やめるも完了扱い） | 同上 |
| 313 閉じ漏れ（`/313?tab=misses`） | `sync_meta.todoist_313_close_leak`（Mac 毎日 19:30 `done_elsewhere.py --publish`）→ `/api/closeleak` | 済み／残す | `/api/cleanup`（origin=close_leak）→ cleanup reflect が根拠コメント付きで完了 |
| スター片付け | 同上（origin なし） | 完了／残す | 同上 |
| お題 | `task_loop_topics`（312） | 案n／保留 | `/api/decide` |
| 今週の9件 | `sync_meta.weekly_pick_snapshot`（未確定の週だけ1行） | なし（「開いて決める」→ `/week`） | `/api/week` |
| Zaim | `watch_status(zaim_quality)` | 正しい／違う | `/api/zaim` |
| ルール候補 | `sync_meta.loopware_rule_candidates`（未判断だけ） | 採用／今回だけ／違う | `/api/rules/decide` |

- 並べ替え: 重要度順／期日超過順／すぐ決まる順。絞り込み: ジャンル（件数バッジ）・重要度・すぐ決まる／じっくり・提案ありだけ
- 判断の重さ（すぐ／じっくり）は今週の9件の材料（`config/todoist_weekly_weight.yaml` で判定済み）から同じタスク id に付ける。分からない件は印なし（推測で付けない）
- 提案どおり: 行の ★、チェックした分、表示中ぜんぶ。どれも「選ぶ」だけで、「まとめて確定」を押すまで何も記録しない
- Todoist の削除はここでは選べない（318・スターの「削除」は 「313 出口」の「まとめて」（`/313`。旧 `/313/bulk` は `/313` へ転送）だけ）。Zaim・ルール候補には提案を置かない（基準は本人が選ぶ）

## 312 の本物のお題（collect／reflect）

- `scripts/jarvis_todoist_312_collect.py`（`.github/workflows/todoist-312-collect.yml`）
  - collect（月・水・金 20:30 JST）: Slack の松野さんの発言から『起こり』を拾い、`task_loop_topics`（source_kind=slack, status=open）と3案を入れて #consult に「Nody で開く」
  - reflect（30分ごと）: 「既存タスクへ追記」「別タスクを作る」を選んだものだけ Todoist へ反映し `reflected_todoist_id` に記録
- 画面: `/312` は `/api/topics`（鍵が要る）の本物のお題だけを並べる（見本＝例題は出さない・2026-11-21）。お題が空、または全部決めたら「判断するタスクなし」の祝い表示（輪とチェックが描かれ粒がはじける）。決めると status=decided
- 試す: `python3 scripts/jarvis_todoist_312_collect.py --dry-run --hours 240`

## 今週の9件（`/week`・土曜の午前）

入口（312）→ **今週の9件** → 出口（313）→ 週1のレビュー、の真ん中。2026-11-10 松野さん決定。

- 決まりごと: 確定は目の前の1週間（月・水・金に3件ずつ）。火・木は派生・追加の空け、土日は残りの片付け。
  次の週は候補の順番だけ、2〜3週先は締切・支払い・行事の日付だけ見る。外との約束・行事の期日は外さない
- 手順: ① 先週の結果と「残った理由・次の手」→ ② おすすめ9件と選ぶ理由（AI案）を直して3週間カレンダーの月・水・金に置く
  （候補をタップ→マスをタップ、またはカードの 月/水/金）。入口で残った話題もここで 今週やる／入れる／見送る → ③ 確定
- 材料: `scripts/jarvis_todoist_weekly_pick.py --mode snapshot`（`.github/workflows/todoist-weekly-pick.yml`、土曜 07:00 JST・次の月曜からの週が対象。2026-11-23 に日曜 17:00 から変更）
  → `sync_meta.weekly_pick_snapshot`。カレンダーは Mac の `scripts/jarvis_weekly_pick_calendar.py --publish`
  （`scripts/install_weekly_pick_calendar_launchd.sh`、毎朝 6:30・日曜 16:30。土曜の判断には朝 6:30 の分が使われる）→ `sync_meta.weekly_pick_calendar`
- 判断ログ: `owner_decisions` surface=`weekly_pick`（pick／defer／left／commit）。AI案の理由（ai_proposal）と選んだ理由（final_text・reason_tags）、
  AI案の曜日（payload.ai_day）と置いた曜日（payload.day）が残る
- 反映: 同じスクリプトの `--mode reflect`（30分ごと）が commit の plan を Todoist へ（期日を入れる／外す、入口の話題を 🦾依頼 で作る、
  やめる・AIへはコメントだけ）。反映したら action=done（target_type=weekly_commit）を足す。312 はタスクを閉じない
- 判断の重さ（2026-11-23）: 各件に「すぐ決まる」（判断すれば進む・終わる）／「じっくり」（ラリーして形にする）／「未判別」の印と根拠1行。
  基準は `config/todoist_weekly_weight.yaml`（snapshot 側で判定・AI は呼ばない）。見出しに置いた件の内訳（すぐ決まる n／じっくり n／未判別 n）
- じっくり枠: じっくりは週1件を**火・金**（`deep_frame.weekdays`）に1回目・2回目として置く。9件の上限は枠の2回を含めて数える（月水金は7件まで）。
  すぐ決まるは月→水→金に前倒し。2件目以降のじっくりは「翌週以降の候補へ」の理由つき。枠には社員1名のフロー磨き込み
  （チャッピー相談→図で確認→本人判断→運用で確認）も入れられる。社員は本人が決める（config の `staff_by_week` か画面で書く。自動で決めない）。
  枠のタスクは1回目の日に期日・2回目はコメント、社員の分は Todoist に起票しない（判断ログ target_type=`weekly_deep_frame` だけ）。
  本人が置き直した・空けた枠は下書きのまま（再読込で上書きしない）
- 下書き: 端末の localStorage（`weekpick:v1:<週>`）に自動保存。確定し直すと新しい行が増え、最後の確定だけ反映
- 試す: `python3 scripts/jarvis_todoist_weekly_pick.py --mode snapshot --dry-run`、テスト `npm test`（tests/weekPick.test.ts）と
  `python3 -m unittest scripts/tests/test_todoist_weekly_pick.py`

## 毎日の仕分け → 週1のレビュー → Slack

- **毎日**：ハブの「今日の仕分け」（`/312?tab=misses`）を仕分けて保存すると、その日は完了。判断ログが溜まる（お題は日付ごと。前の日の判断はログとして残る）
- **週1**：溜まったログを `/review` で確認し、基準を更新
- **Slack**（`scripts/loopware_weekly_review_slack.py`／`.github/workflows/loopware-weekly-review.yml`）：
  月曜 09:00 JST に先週のログを集計して #consult へ「確認をお願い」→ 毎朝 09:30 JST に確認待ちなら催促（最大2回）→
  アプリで「この週のレビューを完了」が押されたら #report に「確認済み」を返す。状態は `owner_decisions`（surface=`loopware_review`）に追記
- **仮説づくりと了承はアプリではなくエージェント（Miss Lemon）で行う**。手順は [docs/週次レビュー_Miss_Lemon手順.md](docs/週次レビュー_Miss_Lemon手順.md)
- 動作確認：`python scripts/loopware_weekly_review_slack.py --mode report --dry-run --week YYYY-MM-DD`（Slack へ出さず本文だけ表示）

## 週1のレビュー（`/review`）

判断ログ（312・313・音声コメント）を週ごとに見て、基準を更新する。
- 見送り・保留の理由を分けて集計、直しの前後、「次も同じに」が付いた判断（基準の候補）を並べる
- 基準は**本人が承認したものだけ**。承認・編集・取り消し・レビュー完了は Supabase `owner_decisions`（surface=`loopware_criteria` / `loopware_review`）へ追記のみ（現在の一覧は履歴を順に読んで作る）
- 分析・学習はツールの外：「AIに渡す文章をコピー」で、段階（その場／〜10件／〜30件／〜100件／成果で見直す）に合わせたお願いと生ログをチャットのAIへ渡す

## 資料づくり（`/slides`）

DX互助会などの説明資料を、ループウェアの型で作る。エージェントが構成案を3つ置き → ここで1つ選び観点を選ぶ → 資料を作って直す → エージェントが直しを概念にまとめた次回反映案を置き → ここで 採用／今回だけ／違う。採用したものだけが「資料の基準」として次回の案に効く。
- アプリは AI を呼ばない。手順は [docs/資料作成ループ_Miss_Lemon手順.md](docs/資料作成ループ_Miss_Lemon手順.md)、型は `prompts/slides_proposal.md`
- デッキ：`sync_meta`（key=`loopware_slides`）。`scripts/slides_loop.py put` で置く
- 判断：`owner_decisions`（surface=`slide_plan`／`slide_fix`／`slide_rule`）

## 画面の好み（`/uiux`）

3アプリ（ダッシュボード・KURASHIFT・ループウェア）の画面づくりを、ループウェアの型で松野さんの好みに寄せる。エージェントが好み帳を読んで画面の案（画像つき）を置き → ここで案ごとに 良い／違う／迷う＋理由タグ（任意）、1つ選ぶか「どれも違う」→ 作った後の直しはエージェントが記録 → 土曜に好みルール案を 採用／今回だけ／違う。採用したものだけが好み帳に入り、次の案づくりで必ず読まれる。上部に「1案目OK率・平均往復回数」を出す。
- アプリは AI を呼ばない。道具は `scripts/jarvis_uiux_loop.py`（リポジトリ直下）、手順は AGENTS.md「画面づくりの好み帳」
- ラウンド：`sync_meta`（key=`loopware_uiux`）。画像は Supabase Storage の非公開バケット `uiux-shots`（`storage:<パス>` をサーバが1時間の署名付き URL にする）
- 判断：`owner_decisions`（surface=`uiux_plan`／`uiux_fix`／`uiux_rule`、employee=814）。好み帳：`docs/AIエージェントチーム/800_俯瞰UI・投影更新室/uiux_taste.md`

## 声でフィードバック

312・313 の下部バーのマイクで、字幕を見ながら声でコメントを残せる（T05「見ながら言う」）。
対象は既定で**いま見ているカード**（スクロールに追従）。**話し始めた時点**のカードに結び付ける。カードをタップすると固定。
話し終えたときに見ている場所が違えば、コメントに「こちらへ移す」が出る（付け替えは `voice_comment_reassigned` として追記）。
確定した文は `/api/feedback` 経由で Supabase `owner_decisions`（surface=`loopware_voice` / action=`voice_comment`）へ追記（削除は `voice_comment_deleted` を足すだけで元の行は残す）。
音声認識はブラウザの Web Speech API（Chrome）。マイク許可が必要。

iPhone は **Chrome** 前提。

## 入場（鍵）

- Vercel の jarvis-loopware に `LOOPWARE_ACCESS_KEY` を設定する（判断デスクには件名・相手名が出るため）
- 端末ごとに1回 `/login` で鍵を入れる → 180日有効の Cookie
- Slack からのリンクは `?t=<期限>.<署名>`（7日有効。`lib/access.ts` の `linkToken`）でそのまま入れる
- 鍵が未設定の本番では、従来の `/` `/312` `/313` だけ開き、新しい画面と `/api/log` は止める

## 判断ログに残ったときの演出

- 記録できた（ok）ときだけ、各画面が `logged()`（`lib/logPulse.ts`）を呼ぶ。失敗・端末預かりでは出さない
- 演出は `components/LogCelebration.tsx`（layout に1つ）：チェックの輪 → 粒が右上の瓶へ飛ぶ → 瓶がせり上がり、今週の件数（`/api/log`）が繰り上がる
- 案の確定・反映案を全部決め終えた・10件ごとの区切りは `big`（紙吹雪＋ひと言）。判断デスクは連打するので `compact`（瓶だけ）
- 動きを減らす設定の端末では、動かさずに件数だけ出す

## 判断ログの書き込み（契約 v1）

- 契約: `lib/decisionContract.ts`（正本。`apps/jarvis-dashboard/lib/decisionContract.ts` は写し）
- 書き込み: `POST /api/log` に `{ decision }` または `{ decisions: [...] }`（最大50件。端末で溜めた分の再送用）
- 今週の粒: `GET /api/log?surface=triage` → 採った／見送った／迷った／未判断…の件数
- 同じ判断の再送は `payload.idem_key` で1行にまとまる（索引: `20261108_owner_decisions_idem_key.sql`）
- テスト: `npm test`（契約・鍵）、`python3 -m unittest scripts/tests/test_decision_contract.py`（写しの一致・Python 経路）

## データ

- 端末: localStorage `loopware_v1`（保存シートに「共有DB／端末のみ」を出す）
- サーバ: 312 → `task_loop_*`／313 → `owner_decisions`（`lib/decideStore.ts`）
  - 保存に失敗したら API は `persisted:false` を返し、保存シートは「端末のみ」と出す（不明な応答も成功扱いにしない）
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
4. `apps/jarvis-dashboard/supabase/migrations/20261108_owner_decisions_idem_key.sql`（二重記録防止。未適用でも先に重複を確かめてから入れるので動く）
5. `apps/jarvis-dashboard/supabase/migrations/20261111_kurashift_owner_decisions_retro.sql`（KURASHIFT の資金移動・物件の判断と答え合わせを owner_decisions へ写すトリガー。surface=kurashift_money／kurashift_deal。20261110 の上位互換でこれ1本でよい）

（MCP 権限が無い環境では Dashboard SQL で手動適用。）

## 関連

- 312: `docs/AIエージェントチーム/…/312_…/docs/ループウェア_入口設計_20261107.md`
- 313: `docs/AIエージェントチーム/…/313_…/docs/ループウェア_出口設計_20261107.md`


## ボット用の入り方（2026-11-27 大佐の決定・アイテム134）

- 環境変数 `LOOPWARE_BOT_ACCESS_KEY`（松野さんの `LOOPWARE_ACCESS_KEY` とは別の値）。`/login` にこの鍵を入れると、別の Cookie（actor=bot）をもらう。松野さんの鍵は actor=owner。
- 判断ログ（owner_decisions）の `payload.actor` に owner／bot を残す。無い古い行は owner 扱い。
- actor=bot で止めるもの（403 `{code:"bot_forbidden"}`）: 返信の「送る」、見送り・Todoist・回答不要（判断デスク／次の一手）、312/313 の判断、313 まとめ判断、今週の9件の確定。見る・下書き作成・迷った記録は今までどおり。
- Jarvis `/api/g/ma/*` へも `actor` を渡し、`actor=bot` なら Jarvis 側でも 403（二重の守り）。
- 鍵の値は 1Password のエージェント保管庫と Vercel（jarvis-loopware の production/preview）。設定は再デプロイ後に効く。
