# フロー — 朝便返信下書き作成（211）

更新: 2026-10-11（Phase3: Graph／GHA 本線）

## 本線（毎朝 07:30 JST・クラウド）

1. 前日までの取込（Gmail／Chatwork→MD は既存 GHA 05:00 等）→ OneDrive `5.やり取り.md`
2. GHA `jarvis-reply-draft-211.yml` 起動
3. Graph で管理会社（101〜104）の `5.やり取り.md` を materialize
4. `night_triage --lane partner`（heuristic）→ 211 フィルタ（lookback21・見積B・社ごと最新1件・テンプレ下書き）
5. Graph PUT で正本保存: `4.送信下書き.txt` / `4.LINE送信下書き.txt`
6. 起案1件以上 → Slack `#report`（件数のみ）／見積B待ち → `#consult`／失敗 → `#ops`
7. 人が確認。「これで送ってOK」まで送信しない

## 入口

| 役割 | パス |
|---|---|
| GHA 本線 | `scripts/jarvis_gha_reply_draft_211.py` / `.github/workflows/jarvis-reply-draft-211.yml` |
| Mac 保険 | `scripts/jarvis_reply_draft_211.py --morning` / launchd `reply-draft-211` |
| Graph | `scripts/jarvis_onedrive_graph.py`（読取・PUT・子一覧） |

停止: Secret `JARVIS_REPLY_DRAFT_211_GHA_DISABLE=1`  
詳細: `docs/runbook-211.md` / 図: `docs/flow-overview.html` / Graph: `docs/Jarvis_OneDrive_Graph.md`
