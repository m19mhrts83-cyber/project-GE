# FlowForge「AIエージェントへの指示」貼付全文（ハブ正本）

- 取得: 2026-10-11
- **現行フロー（正）**: https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_gvDWblu8H38otZzGm66S4Znv
- 旧フロー（文言残り・非推奨）: `flow_Q-tcpLi56I1Eku1bCz0UyCJN`
- **ハブ正本の上書き**: 終了報告本線は Slack `#report`（起案あり時のみ）。Todoist／Dashboard は補助。正本は OneDrive `4.送信下書き.txt`（**書込は Microsoft Graph PUT**）。Discord置換しない。実装判断は同フォルダ `CLAUDE.md` / `report_consult.md` を優先。
- **実行本線（2026-10-11〜）**: GitHub Actions `jarvis-reply-draft-211.yml`（毎朝 07:30 JST）。エントリ `scripts/jarvis_gha_reply_draft_211.py`。Mac launchd は保険。停止: `JARVIS_REPLY_DRAFT_211_GHA_DISABLE=1`。

実行時は FlowForge「エージェントへの指示」をコピーするか、本ファイルを使う。実装の正は GHA／Graph（上記）。

---

# 業務自動化プロジェクトの伴走依頼

以下の業務フローを AIエージェント を使って自動化していきたいです。
**いきなり全自動を作るのではなく、私（初心者）と一緒に、簡単なところから段階的に進めてください。**
デスクトップアプリで作業フォルダを開いた状態で、この指示を貼り付けています。

---

## 対象の業務フロー

# 管理会社向け朝便返信メール下書き自動作成

管理会社からの新着連絡や受信要約を基に、物件状況に応じた返信文面を自動起案し、OneDrive `4.送信下書き.txt` に正本保存し、Slack `#report` へ終了報告するワークフロー。

---

## 開始トリガー：毎日7:30に起動
・種類：定期実行
・起動する場所：**GitHub Actions**（`jarvis-reply-draft-211.yml`／cron `30 22 * * *` UTC＝07:30 JST）。Mac launchd は保険のみ。
・朝便スケジュール起動。OneDrive 正本は **Microsoft Graph** で読書き（Mac 同期 path 必須ではない）。
・定期実行。起動に失敗した場合の報告先は Slack #ops。

---

## 1. 受信情報の取得と論点整理（フェーズ1）

新着メール本文と受信要約を取得し、返信が必要な案件の抽出と要点を整理する

### 詳細1-1. ツール/MCP：文脈資料とTodoist propertiesの取得
・利用MCP：OneDrive / Todoist
・OneDriveの「5.やり取り.md」とTodoist properties（物件ラベル・管理会社ラベル）を取得する。815オプチャは返信対象外として除外する。

### 詳細1-2. AIエージェント：問い合わせ分析・返信方針策定
・対象判定、論点と返信方針を整理する。Fromはestate（matsuno.estate）を使用し、既存スレッドがm19mの場合のみ例外とする。815オプチャは対象外。送信は行わない。退去・修繕・見積・請求が絡む場合は退去者提示用見積Bの確認を行い、業者原価見積Aを相手向け文面や添付に含めない。

### 詳細1-3. ツール/folder：該当案件の退去者提示用見積Bを確認
・利用FOLDER：OneDrive
・退去・修繕・見積・請求が絡む場合のみ、退去者提示用見積Bの有無を確認する。業者原価見積Aは相手に提示・送付しない。Bが確認できない場合は確認待ち（必要なら Slack #consult）。

---

## 2. 返信起案と下書き作成（フェーズ2）

丁寧かつ過不足のない返信文を生成し、OneDriveの4.送信下書き.txtに正本保存する

### 詳細2-1. AIエージェント：返信メール文面の生成（送信元・内容制約を適用）
・下書き文面のみ生成し、自動送信しない。Fromはestate。LINEが必要な場合は人がクリップボード経由で扱うための文面準備までとし、API直接送信・Mac版LINE起動は禁止。

### 詳細2-2. AIエージェント：任意：進行中タスク要約フッターを付与
・任意ステップ。適切な進行中タスクがある場合のみ、管理会社向け本文末尾に要約を追加。

### 詳細2-3. ツール/folder：正本をOneDriveパートナーフォルダの送信下書きファイルに保存
・利用FOLDER：OneDrive（**Microsoft Graph PUT**／`jarvis_onedrive_graph.upload_file_graph`）
・正本はOneDriveパートナーフォルダ／4.送信下書き.txt（LINEは4.LINE送信下書き.txt）。件名を1行目に記載する。Gmail下書きトレイのみを正本にしない。送信はしない。

---

## 3. ツール/通知：Todoist・Jarvis Dashboardに補助通知
・報告先：Todoist / Jarvis Dashboard（補助のみ）
・Todoist（オーナー確認／進行中）とJarvis Dashboardへの補助通知。終了報告の本線はSlack #reportとし、ここではSlack報告を代替しない。

---

## 4. 人間：チャットで明示承認するまで送信しない（必須送信ゲート）
・人がチャットで「これで送ってOK」と明示するまで送信不可。このフローは下書き作成までとし、自動送信・送信ステップを置かない。承認後の送信は別フローで人が実施する。

---

## 終了報告：条件に応じてSlackへ終了報告
・報告先：Slack #report
・起案が1件以上、または要確認事項がある場合のみSlack #reportへ報告する。対象0件かつ失敗なしの場合は報告しない。方針に迷いがある場合はSlack #consult、起動失敗はSlack #opsへ報告する。Slackに下書き全文は載せず、件数・状態・確認事項などの要約のみを報告する。

---

（以降の伴走テンプレ共通節は FlowForge UI 上の全文を参照。実装の不変条件は上書き節と CLAUDE.md を正とする。）
