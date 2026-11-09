# 715 家族会議週次係

ID: **715**。コーチング支援室（700）。2026-10-19 新設。

## 1. 役割

- やること: 日曜の家族会議後（21:30）に、Genspark AI Meeting Notes（Speakly 同一ストア）の議事録を
  Drive へ MD 保存 → NotebookLM「家族会議」1ノートへソース追加 → Studio で週次インフォ生成 →
  **Notion 当日ページの旧週ブロックを削除 → 末尾へ「インフォ → 議事録要約」の順**で挿入 → Slack 報告。
- 議事録要約の本文は全エージェント共通の型 [`52_議事録のまとめ方`](../../52_議事録のまとめ方_20261029.md)（「家族会議の場合」も）で仕上げてから載せる。自動では Gemini が仕上げ、失敗時は元の要約
- **複製前提**: 松野さんの前週複製では旧週のインフォ／議事録が残る。当該週以外の
  `週次インフォグラフィック（旧日付）` / `Genspark 議事録要約（旧日付）` を自動削除してから入れる
  （当該週の見出しは残す＝再実行しても二重挿入しない）。
- やらないこと:
  - Notion 日付ページの複製・アジェンダ編集（**松野さん担当**）
  - 週ごとに NotebookLM ノートを増やす（**1ノート固定**）
  - 過去週・他ソースをインフォに混ぜる（当該週議事録＋マスタースタイルのみ）
  - 議事録 MD を Notion の添付だけで済ませる（**ページ内本文が正**）

## 2. 動き出す合図

- [x] 時間: **日曜 21:30**（launchd `com.matsunoma.friday.family-meeting-weekly`）
- [x] 見回り: **月曜 07:00** `--retry`（未完了時のみ）
- [x] 人依頼: 「家族会議の議事録とインフォ付けて」（`--date` / `--meeting-id`）
- [x] 変化: 枠切れ・Studio 失敗・ページ未作成 → `#ops`

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| CLI | ○ | `gsk meeting`／Notion REST／Playwright（Studio） |
| 秘密 | ○ | `GSK_API_KEY`・`NOTION_API_TOKEN`（`.env.jarvis_private`） |
| 対外送信 | × | しない（Slack 内部報告のみ） |

**人が確かめる**: Notion ページの複製・アジェンダ。話者名の最終確認（自動補正は要確認フラグ付き）。

## 4. 報告先

| 種別 | 行き先 |
|---|---|
| 完了 | Slack `#report`（**松野への情報共有のみ**。判断・依頼は書かない） |
| 失敗・枠切れ | Slack `#ops`（原因・進み・「次:」を短く） |
| 要手当て | Slack **`#ai-hub`【要手当て】**（下の「失敗の拾い方」。同じ原因は1回だけ） |
| Jarvisへの依頼・確認 | Slack **`#ai-hub`**（`#consult` は松野の要判断専用） |
| 正本 | Notion 家族会議 `(YYYY/MM/DD)` ページ／Drive `13_家族会議_週次/` |

### 失敗の拾い方（2026-11-09 松野さん要望）

10/25・11/1・11/8 と3週続けて `#ops` だけに出て、誰も拾わないまま議事録が入らなかった。
そこで、人かAIの手当てが要る失敗は、番頭さん・ホークが見ている `#ai-hub` に【要手当て】で出す。

| 原因（自動判定） | `#ai-hub` に出す時点 | 次の一手 |
|---|---|---|
| Notion 当日ページ未作成 | 日曜の初回失敗ですぐ | 松野さん: 前週複製→再実行 |
| Genspark 認証切れ（401） | 日曜の初回失敗ですぐ | 松野さん: Mac で `gsk login`→再実行 |
| 当日の録音が見つからない | 日曜の初回失敗ですぐ | 松野さん: 録音確認、あれば `--meeting-id` |
| NotebookLM／Studio／Notion API／不明 | 月曜07:00 `--retry` でも失敗したとき | Jarvis / Miss Lemon: Mac で手当て |

- 挿入後に見出し2つを読み直し、無ければ失敗扱いにする（入ったつもりで入っていない、を拾う）。
- 成功時の `#report`【報告】715 に「解決: #ai-hub【要手当て】（原因）」の行が付く。これが解決確認の根拠。
- 役割分担（`55_` の範囲内。新しい定期処理は増やさない）:
  - **番頭さん**: 既存巡回で【要手当て】スレを拾い、`#report`【報告】715 が出たかを見てスレで解決確認。
    月曜11:50の巡回で、前日分の【報告】715 も【要手当て】715 も無いとき（Mac 停止などで何も出ていない）は、松野さんへの報告に1件入れる。
  - **ホーク**: 朝6:15の確認で【要手当て】715 を Todoist「AIエージェントチーム」へ起票（担当・次回確認日）。完了は `#report` の成功報告リンク付きで。
  - **Jarvis / Miss Lemon**: AI側の原因のとき Mac で手当てし、同じスレで報告。

### Slack 書き出し（FRIDAY／Jarvis 共通）

正本: [`38_Slack書き出し_FRIDAY_Jarvis_20261018.md`](../../38_Slack書き出し_FRIDAY_Jarvis_20261018.md)

## 5. 実行ファイル

| 用途 | パス |
|---|---|
| オーケストレータ | `scripts/friday_family_meeting_weekly.py` |
| Notion 操作 | `scripts/friday_notion_ops.py` |
| 議事録 MD | `scripts/jarvis_family_meeting_weekly.py`（既存を再利用） |
| NLM ソース追加 | `scripts/jarvis_notebooklm_add_source.py` |
| Studio | `scripts/jarvis_notebooklm_studio_run.py` |
| launchd | `launchd/friday_family_meeting_weekly_runner.sh` / `install_friday_family_meeting_weekly_launchd.sh` |
| 状態 | `.jarvis_state/friday_family_meeting_weekly.json` |
| ログ | `~/Library/Logs/friday_family_meeting_weekly/` |

## 6. 設計4点

| 柱 | 内容 |
|---|---|
| 入口 | Genspark `search`（前後1日）→ JST 日付＋家族語彙＋時間帯で採点。曖昧なら `--meeting-id` |
| 確認 | ページ未作成なら停止して `#ops`（複製は人）。旧週ブロックは自動削除。二重挿入は見出しで防止 |
| 履歴 | 日付ごとに `source_added` / `infographic_png` / `notion_inserted` を保存 |
| 停止 | `config/notion_family_coaching.yaml` の `automation.enabled: false` または `FRIDAY_FAMILY_MEETING_WEEKLY_DISABLE=1` |

## 7. 改善ログ

| 日付 | 内容 |
|---|---|
| 2026-10-19 | 新設。日曜21:30＋月曜07:00リトライ。Notion複製は人担当として分離 |
| 2026-10-19 | Builder 組織図・索引・ダッシュ反映（共有 `uksxiDIzE1AEckKH`・40体） |
| 2026-11-09 | 失敗を原因で分類し、要手当ては `#ai-hub`【要手当て】へ（番頭さん解決確認・ホーク起票）。挿入後の見出し確認、`#ops` のエラー文短縮 |
| 2026-10-29 | 議事録要約を `52_議事録のまとめ方` の型で仕上げて掲載（自動は Gemini、失敗時は元の要約。松野さん了承） |

## 8. Jarvis回答（2026-10-19 #ai-hub）

| # | 論点 | 確定 |
|---|---|---|
| 1 | 前週ページ複製 | **松野さん手動**。自動化しない |
| 2 | インフォ画像 | **PNG優先**（PDFならPNG化）。Notion画像ブロックをページ末尾へ。file upload でOK |
| 3 | 話者補正 | 辞書（さあ/さー→さわ、まーくん→たまき 等）＋**要確認フラグ**。Speaker N は自動で決めない |
| 4 | 会議特定 | タイトルは自動生成。**JST日付＋家族語彙＋時間帯の採点**でよい（追加の命名規則なし） |
| 5 | NotebookLM | **1ノート固定**。2026-09-20以降も週次ソース追加の運用 |

初回ライブ解除OK（日曜21:30本線／月曜07:00 `--retry` のまま）。
