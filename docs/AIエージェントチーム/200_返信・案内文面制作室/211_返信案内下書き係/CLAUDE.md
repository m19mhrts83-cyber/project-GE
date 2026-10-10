# 返信案内下書き係（管理会社向け朝便）

作業を始めたら、まず `PROGRESS.md` を読む。

## 0. 置き場（二層）

| 層 | パス | 役割 |
|---|---|---|
| **運用ハブ（このフォルダ）** | admin Drive `★AIエージェントチーム/200_返信・案内文面制作室/211_返信案内下書き係/` | 設計・進捗・手順・ログ。伴走の作業フォルダ |
| **版管理ミラー** | `~/git-repos/docs/AIエージェントチーム/200_返信・案内文面制作室/211_返信案内下書き係/` | Git に載せる写し（節目で同期） |
| **下書き正本** | OneDrive `26_パートナー社への相談/{三桁}/4.送信下書き.txt` | 各パートナーへの文面。形式は `docs/draft-format.md` |
| **文脈正本** | 同フォルダ `5.やり取り.md` | 受信・送信履歴 |
| **実行コード** | `~/git-repos/scripts/` | Jarvis 既存スクリプト（秘密は `.env.jarvis_private`） |

## 1. 役割

- **やること**: 管理会社の新着・受信要約から返信文を起案し、OneDrive `4.送信下書き.txt` に正本保存。**完了・承認待ちの知らせは Slack `#report` が本線**（Todoist／Dashboard は補助）
- **やらないこと**: 了承前の対外送信／815オプチャへの返信／原価見積Aの相手提示／秘密の再掲／勝手な Todoist complete／Slack に下書き全文を載せる

## 2. 決定事項（2026-10-11）

| 項目 | 決定 |
|---|---|
| 実行環境 | **本線: GHA＋Graph**。FlowForge 定義は参照のみ（`flow_gvDWblu8H38otZzGm66S4Znv`）。Mac は保険 |
| 取込 | 既存 Gmail API（`gmail_to_yoritoori`）＋ `5.やり取り.md` |
| 下書き正本 | 経路別: Gmail=`4.送信下書き.txt`（1行目=`件名：`）／LINE=`4.LINE送信下書き.txt`。Gmailトレイは正本にしない |
| From | estate。既存スレが m19m のときだけ例外 |
| 見積 | 退去・修繕・見積・請求時は提示用B確認。Aは相手に出さない |
| 終了報告（本線） | Slack `#report`（起案あり時のみ）。迷い=`#consult`／失敗=`#ops` |
| 作業トラッキング（補助） | Todoist（オーナー確認／進行中）＋ Jarvis Dashboard |
| 送信ゲート | 人が「これで送ってOK」と言うまで送信しない。本フローに送信ステップを置かない |
| 定期実行 | **Phase3 本線: GHA** `jarvis-reply-draft-211.yml`（07:30 JST・Graph）。Mac launchd は保険 |
| 再利用 | `jarvis_reply_draft_211.py`（入口）／`jarvis_night_triage.py`／`jarvis_slack_webhook_post.py`／`jarvis_todoist_pm_status_footer.py` |
| LINE送信 | 人間が iPhoneミラーリングで貼付。記録は `line_clip_send.py --record-only`。OA Bot は受信のみ（pushしない） |

連携詳細: `docs/setup-connectors.md`  
下書き形式: `docs/draft-format.md`

## 3. 動き出す合図

- [x] 人が頼む（伴走・手動パイロット）
- [x] 手動朝便（Phase2: `--morning`）
- [x] 時間（毎朝 7:30 — Phase3 GHA／Mac 保険）
- [ ] 何かが届いたら（将来）

## 4. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| チャット・検索 | ○ | 方針・承認 |
| Gmail / Todoist API | ○ | 取込・起票・通知（既存スクリプト） |
| OneDrive ファイル | ○ | `5.やり取り.md` 読／`4.送信下書き.txt` 書 |
| ブラウザ送信 | × | 送信は人 |
| Mac版LINE | × | CHRLINE 競合のため起動しない |

## 5. 報告先

| 種別 | 行き先 |
|---|---|
| 完了・承認待ち（本線） | Slack `#report`（文面: `report_consult.md`） |
| 方針の迷い・見積B待ち判断 | Slack `#consult` |
| 起動・投稿失敗 | Slack `#ops` |
| 補助 | Todoist／Dashboard／伴走中のみ Cursor チャット |

## 6. 成果物の置き場

- このフォルダ: `logs/` / `docs/` / `outbox/` / `PROGRESS.md`
- 外部正本: OneDrive `26_パートナー社への相談/{三桁}/4.送信下書き.txt` と `5.やり取り.md`

## 7. 段階ロードマップ

| Phase | 内容 | 状態 |
|---|---|---|
| 1 | 手動で正本起案＋Slack `#report`＋送信クローズ | **完了**（ミニテック Gmail／Tcell LINE・2026-10-11） |
| 2 | 管理会社複数の朝便定常＋見積B分岐 | **完了**（dry-run 検証・2026-10-11） |
| 3 | 毎朝7:30 GHA（Graph） | **実装済**（push 後に dispatch 確認→Mac 保険解除） |

## 8. 作業手順（Phase 3 朝便・GHA）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
# Graph 経路（クラウド相当）
PYTHONPATH=scripts ~/selenium_env/venv/bin/python scripts/jarvis_gha_reply_draft_211.py --dry-run
# GHA
gh workflow run jarvis-reply-draft-211.yml -f dry_run=true
# Mac 保険（ローカル path）
~/selenium_env/venv/bin/python scripts/jarvis_reply_draft_211.py --morning --dry-run
```

挙動:

1. Graph で 101〜104 の `5.やり取り.md` を materialize
2. `night_triage --lane partner`（heuristic・LLM off）→ 空下書きは 211 テンプレで補完
3. 社ごと最新1件。21日超スキップ。見積B無し → `#consult`
4. 起案あり → Graph PUT で正本 → Slack `#report`
5. 送信は人が別フロー（LINEは貼付＋`record-only`）

停止: `JARVIS_REPLY_DRAFT_211_GHA_DISABLE=1`  
Phase1 人向け: `docs/phase1-pilot.md`

## 9. 改善ログ

| 日付 | 変更 |
|---|---|
| 2026-10-09 | ビルダー候補フォルダ作成 |
| 2026-10-11 | 朝便伴走開始。既存 Jarvis スタック採用・Phase1=手動1社に決定 |
| 2026-10-11 | 終了報告を Slack `#report` 本線に変更。`report_consult.md` 追加 |
| 2026-10-11 | FlowForge クリーン版 `flow_gvDWblu8H38otZzGm66S4Znv` |
| 2026-10-11 | 運用ハブを Drive `211_…` に同期。下書き形式 `docs/draft-format.md` 追加 |
| 2026-10-11 | Phase1送信クローズ。Phase2（複数社・見積B・lookback21）＋launchd雛形 |
| 2026-10-11 | Phase3: Graph PUT＋GHA `jarvis-reply-draft-211`。Mac launchd は保険 |
