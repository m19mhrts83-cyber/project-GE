# FlowForge「AIエージェントへの指示」貼付全文 — 114

- 更新: 2026-10-12
- フロー: https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_O1OMOoN2vkVf9SKLD9T_mvBy
- **実装の正本**: 同フォルダ `CLAUDE.md` / `flow.md` / `scripts/jarvis_property_gate_114.py` / `jarvis_property_gate_degraded.py`
- 横断正本: `docs/AIエージェントチーム/23_物件進行ゲート_Grok調査_20261012.md`
- 上限時: `docs/AIエージェントチーム/24_Jarvis上限時_物件進行ゲート_次善策_20261012.md`
- **ハブ上書き**: kintone禁止・Cursor必須にしない・送信は511。B=`#consult`、A/C=`#report`

---

# 業務自動化プロジェクトの伴走依頼

以下の業務フローを AIエージェント を使って自動化していきたいです。
**いきなり全自動を作るのではなく、私（初心者）と一緒に、簡単なところから段階的に進めてください。**
デスクトップアプリで作業フォルダを開いた状態で、この指示を貼り付けています。

---

## 対象の業務フロー

# Grok調査後の物件進行ゲート（A/B/C振分）ワークフロー

Grok S1 の `[Grok調査]` 取込後（および毎日11:15の取りこぼし）に deals を読み、レーン A（自動）／B（要人）／C（報告のみ）へ振り分け、Slack にカードまたはダイジェストを出す。対外問合せ送信はしない（Yes 後は 511）。

---

## 開始トリガー：Grok取込後 / 毎日11:15 launchd / 手動
・種類：イベント＋定期実行
・起動する場所：Mac Jarvis（launchd property-gate-114／朝バンドル／昼 noon 末尾）／手動 CLI
・本線は Cursor 会話不要。`jarvis_property_gate_degraded.py` が一発（heal＋scan＋post）。無効化は `JARVIS_PROPERTY_GATE_DISABLE=1`。

---

## 1. ツール/CLI：handoff 誤ラベル修復
・利用CLI：project-GE / jarvis_property_gate_114.py --heal-handoff
・kurashift_handoff 後に誤って awaiting_grok になっている案件を awaiting_first_inquiry へ直す。秘密・トークンは扱わない。

---

## 2. ツール/CLI：deals 取得と A/B/C 振分
・利用CLI：project-GE / jarvis_property_gate_114.py --scan
・score・聞く価値・inquiry_action・inquiry_status・To 要約のみ読む。Web 再調査しない。
・A=自動進行、B=人の Yes/No 要、C=報告のみ。

---

## 3. ツール/通知：B を Slack #consult へカード投稿
・報告先：Slack #consult
・deal_id・見てほしい3点・Yes/No 用 URL（consult-action）を1カードで出す。秘密は含めない。

---

## 4. ツール/通知：A/C を Slack #report へ
・報告先：Slack #report
・A は1行。C は日次ダイジェスト（1日1通）。送信ジョブは積まない（A＋Tier3+To のときは 511／既存パイプラインへ合図のみ可）。

---

## 終了報告：振分結果を Slack へ出し、送信は 511 に渡す
・報告先：Slack #consult / #report
・この係はゲートまで。Yes 後の問合せ送信は 511（問合せ送信準備係）。

---

## このフローについて（重要な備考 ★必ず先に読んでください）

- **このフローはあくまで「一例（たたき台）」です**。ステップの粒度・ツール名が現実とズレている可能性があります
- **実装の正本は Mac CLI／launchd**（FlowForge は設計図）。kintone は使わない
- 細かい内容は最新情報で更新してよいが、報告先（B=#consult、A/C=#report）と「送信しない」は変えない

---

## 進め方の方針（必ず守ってほしいこと）

### ★大原則: チャット出力は徹底的に短く（最優先）
- 1メッセージは原則5〜10行以内。結論ファースト。挨拶・復唱禁止
- コマンドはチャットに書かず内部実行し結果サマリのみ
- 詳細は別 md に切り出す

### 1. スタンス
- フローは一例。実行前に方針を短く示し OK 後に着手

### 2. 提案のスタイル
- 推奨案を1つ＋なぜ良いか。選択肢の羅列はしない
- ユーザーへの依頼は番号付き TODO

### 3. ツール選定
1. 接続済み連携 2. 公式 REST API 3. ブラウザ操作 4. デスクトップ 5. CLI 6. SDK
- 本フローの正は既存 project-GE Python（`jarvis_property_gate_*`）

### 4–10.
- Phase は効果×簡単さ優先。完了時に確認手順。CLAUDE.md / PROGRESS.md をメンテ。仕組み完成時は HTML 説明図

---

## 最初に出力してほしいもの

⓪ 環境と連携（5〜7行）→ ① ロードマップ表 → ② Phase1 着手＋TODO
