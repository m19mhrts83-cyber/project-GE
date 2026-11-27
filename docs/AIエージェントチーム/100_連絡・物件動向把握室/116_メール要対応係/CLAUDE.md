# メール要対応係（116）

管理者／パートナーの **要返信・要処置メール** を Slack `#consult` で捌く係。  
ボタン: **返信する／見送り／Todoist追加**。業者返信（VR）は **516**。

## AIオートメーション（作業フロー）

- **FlowForge（開く）**: 未作成。当面の正は [`flow.md`](./flow.md)（v2・618 形式の20工程、2026-11-15 松野さん了承）
- 一覧・進捗: [`15_FlowForge全体系_進捗_20261010.md`](../../15_FlowForge全体系_進捗_20261010.md)
- 設計正本: [`Jarvis_メール要対応_Slack操作_20261019.md`](../../../Jarvis_メール要対応_Slack操作_20261019.md)

## 1. 役割

- やること:
  - `triage_items` pending → **スコア上位5**を `#consult` へ。**本線は短索引**、**カード（要旨＋ボタン）はスレ**（Bot時。Webhookは本線に短カード）
  - 見送り連続学習の監視／unmute 案内
  - 障害・枠切れは `#ops`
  - **スター付きメールの起票（入口の一つ・工程03、2026-11-15 松野さん決定）**: 松野さんが自分でスターを付けたメール（人が選んだもの）を Todoist に起票する。道具は Claude 予定タスク「スター付きメール→Todoist起票」（平日 8:38 JST・`trig_01Da1EyELbZPFbYJheDT2BtU`）。Gmail ラベル `Todoist済`／Todoist ラベル `スター起票`。報告は #report に1通（11/22 まで毎回、以後は🟡🔴のみ）
  - スター付き・`Todoist済` のメールはカードに出さず、「後回し」でも二重に起票しない（突き合わせの鍵は Gmail スレッドID。116 の Todoist 説明欄 `gmail_thread=<id>`）
- やらないこと:
  - 了承なしの Gmail 送信（ボタン＝了承）
  - 業者返信 VR（`re-vendor-*`）の処理（**516**）
  - 111 のパートナー `#report` 差分報告
  - 211 の管理会社定型下書き本線
  - GenMail MD 入口の代替（レーン推定のみ同系）

## 2. 動き出す合図（確定 2026-10-19・T1〜T5 すべて）

- [x] **T1 時間＋朝バンドル**: `jarvis_morning_mac_refresh` soft-fail で `--from-triage --limit 5`
- [x] **T2 時間（昼）**: 平日 12:30 JST GHA `jarvis-mail-action-noon.yml`
- [x] **T3 イベント**: `jarvis_night_triage` 成功後に相乗り投稿
- [x] **T4 人が頼む**: 「メール要対応出して」→ `jarvis_mail_action_slack_post.py --from-triage`
- [x] **T5 変化・失敗を見回る**: 朝バンドルで `--health --notify-ops`（異常時のみ `#ops`）

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| CLI | ○ | `jarvis_mail_action_slack_post.py` / `jarvis_mail_action_mute.py` |
| launchd／朝バンドル | ○ | morning soft-fail（T1・T5） |
| GHA | ○ | noon（T2） |
| Slack Bot／Webhook | ○ | `#consult` 投稿・Interactivity は Dashboard |
| ブラウザ | × | |
| Cursor 会話 | △ | 手動依頼・unmute |

**秘密**: `.env.jarvis_private` のみ。値は MD に書かない。  
**人が確かめる（必須）**: Slack ボタン（返信本文・見送り・Todoist）。お金・外に出す・消す。

## 4. 報告先

| 種別 | 行き先 |
|---|---|
| 要判断カード | Slack `#consult`（本線） |
| 障害・健全性異常 | Slack `#ops` |
| 完了・生存 | 朝の回（mac_morning_refresh）でカード0件の日だけ `#report` に🟢1行（例: 要対応0件（流し読み・業者返信の数））、1日1回まで（松野さん 2026-11-27）。カードがある日は従来どおり1行は足さない。昼・夕の回は出さない。止まったのか0件なのかを見分けるため。`--morning` / `--dry-run` で文を確認 |
| スター起票（工程03） | `#report` に1通（11/22 まで毎回、以後🟡🔴のみ） |
| 判断ログ（工程16） | 平日21:00 の unseen 記録のあと `#report` に1通（今日出したカード数・今日たまった判断の内訳・7日合計。カードを出したのに0件なら🟡）。11/22 まで、立ち上がり確認・松野さん 11/15 |

書き出し例: `【ops】116 メール要対応 — 健全性`

### Slack 書き出し（FRIDAY／Jarvis 共通）

| ch | いつ |
|---|---|
| `#consult` | 要返信カード。末尾「次の担当」はボタンUIのため省略可 |
| `#ops` | 投稿失敗・pending過多・mute過多 |

正本: [`38_`](../../38_Slack書き出し_FRIDAY_Jarvis_20261018.md)

## 5–6. 成果物・手順

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_mail_action_slack_post.py --from-triage --dry-run
~/selenium_env/venv/bin/python scripts/jarvis_mail_action_slack_post.py --from-triage
~/selenium_env/venv/bin/python scripts/jarvis_mail_action_mute.py --list
~/selenium_env/venv/bin/python scripts/jarvis_mail_action_mute.py --unmute 'from:addr@example.com'
~/selenium_env/venv/bin/python scripts/jarvis_mail_action_mute.py --health --notify-ops
```

停止: `JARVIS_MAIL_ACTION_SLACK_DISABLE=1`

## 7. 改善ログ

| 日付 | 変更 |
|---|---|
| 2026-11-27 | 見送り・Todoist・後回しをパートナー別に引けるように（松野さん了承・大佐 件127）。判断ログ（owner_decisions）に送り手の識別子 `payload.partner_key`（送信元アドレス、無ければパートナー名）を足す（migration `20261127_owner_decisions_partner_key.sql`・過去分は埋めない）。Todoist 登録直後のカードにも任意の理由タグ（調べてから返信／期限がある／人に確認してから／今は手が回らない）を出し、押したものだけ `reason_tags` に残す（理由は AI で補作しない）。Dashboard `/mail/partners`（ログイン必須）でパートナー別に絞り込み。`5.やり取り.md` は変えない |
| 2026-11-15 | スター起票を 116 の入口（工程03）として正式に位置づけ（松野さん決定）。変更直後の1週間（〜11/22）は毎回の結果を #report に🟢で出す（`JARVIS_MAIL_ACTION_GREEN_UNTIL`） |
| 2026-11-15 | 作業フロー v2（618 形式・20工程）を松野さん了承。判断 A＝スター起票の報告は #report に1通（予定タスクの指示を書換済）、B＝スター付き・Todoist済は116に出さない、C＝ルール帳を読めない回は続行＋「ルール未適用」の印・#ops・判断ログ。B・C は [TASK.md](./TASK.md) のとおり実装（PR #426・マージ待ち）。116 のボタン入口は残す。停止: `JARVIS_MAIL_ACTION_STAR_CHECK=0` |
| 2026-11-15 | 役割の境界を明記: スター付きメール（人が選んだもの）の起票はスケジュールタスク「スター付きメール→Todoist起票」の担当、116 は AI が選んだものだけ |
| 2026-11-11 | Chatwork カードの先頭に「Chatworkで返信」URL ボタン（連絡先一覧.yaml の folder＋ルーム名で `#!rid` を引く。決まらなければ Chatwork トップ）。送信はアプリで本人、ここでは開くだけ。受け口は `action_id=mail_action_open_app` を 200 で素通し（Slack FB 11/10） |
| 2026-11-07 | 昼 GHA に `SLACK_SIGNING_SECRET` を渡す（従来は未設定で URL ボタンに落ち、リンク先で再度押す二度手間）。以後アプリ内ボタンで即完了・カード置換 |
| 2026-10-23 | 同一内容の多重投稿防止: gmail_id / 件名キー dedupe、digest を sync_meta 共有、健全性 #ops 6h クールダウン |
| 2026-10-20 | 本線ダイジェスト＝短索引、カードはスレ（Bot）。下書き全文をSlackから外す。見るストレス低減 |
| 2026-10-20 | Bot/Signing 無しは URL ボタン自動フォールバック。Dashboard ログイン後に `/mail/{id}` へ復帰 |
| 2026-10-20 | スコア上位5・ダイジェスト＋抽出要約（Plan A）。本文全文は Dashboard。Slack出した件はGmail既読。見送りでカード削除。ダイジェストは残 pending で更新／残0で削除 |
| 2026-10-19 | 新設（設計中）。T1〜T5 確定。硬化（連続見送り・unmute CLI・Todoist GenMail型） |
