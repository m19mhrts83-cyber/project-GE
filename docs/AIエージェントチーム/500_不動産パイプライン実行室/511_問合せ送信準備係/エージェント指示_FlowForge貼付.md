# FlowForge「AIエージェントへの指示」貼付全文 — 511

- 更新: 2026-10-12
- フロー: https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_Gr7OKXW7L1ElR7yW_XbBCbNH
- **実装の正本**: 同フォルダ `CLAUDE.md` / `flow.md` / `scripts/jarvis_property_gate_511.py`
- 受信: jarvis-dashboard `/api/slack/consult-action`
- 送信: 既存 `jarvis_kurashift_re_inquiry.py`（`re_deal_inquiry_send` ジョブ／Mac job worker）
- 横断正本: `docs/AIエージェントチーム/23_物件進行ゲート_Grok調査_20261012.md`
- **ハブ上書き**: Bカードの Yes＝対外了承（追加の「送ってOK？」不要）。二重送信禁止。kintone禁止

---

# 業務自動化プロジェクトの伴走依頼

以下の業務フローを AIエージェント を使って自動化していきたいです。
**いきなり全自動を作るのではなく、私（初心者）と一緒に、簡単なところから段階的に進めてください。**
デスクトップアプリで作業フォルダを開いた状態で、この指示を貼り付けています。

---

## 対象の業務フロー

# Slack Yes/No 後の第一問合せ送信ワークフロー

114 が出した B カードへの Yes／No（または Aレーン）を受け取り、Yes なら KURASHIFT 第一問合せを送信し、No なら見送りにする。Grok 調査の再発明はしない。

---

## 開始トリガー：Slack Yes/No（consult-action）/ CLI / Aレーン
・種類：イベントで起動
・起動する場所：Vercel jarvis-dashboard consult-action／Mac CLI jarvis_property_gate_511.py
・リンクまたはボタンで deal_id＋yes|no。Cursor 会話は必須ではない。

---

## 1. ツール/API：Yes/No 受信と冪等チェック
・利用API：jarvis-dashboard /api/slack/consult-action
・PROPERTY_GATE_ACTION_TOKEN で署名。同一 deal の二重 Yes・送信済は無視。秘密をログに出さない。

---

## 2. ツール/CLI：ジョブ積上げまたは見送り
・利用CLI：project-GE / jarvis_property_gate_511.py
・Yes → kurashift_jobs に re_deal_inquiry_send（または --direct）。No → inquiry 見送り（passed）。To 未解決は #consult に1行で止めない。

---

## 3. ツール/CLI：Mac job worker が問合せ送信
・利用CLI：既存 jarvis_kurashift_re_inquiry（--i-confirm-send 相当はジョブ内）
・From は estate。B の Yes が対外了承。追加チャット確認はしない。

---

## 終了報告：送信／見送り結果を Slack #consult へ1行
・報告先：Slack #consult
・成功・失敗・見送りを短く返す。#report への冗長報告はしない。

---

## このフローについて（重要な備考 ★必ず先に読んでください）

- **このフローはあくまで「一例（たたき台）」です**
- **実装の正本は Mac CLI＋既存 re_inquiry**。FlowForge は設計図
- Yes＝了承・二重送信禁止・kintone不使用は変えない

---

## 進め方の方針（必ず守ってほしいこと）

### ★大原則: チャット出力は徹底的に短く（最優先）
- 1メッセージ5〜10行。結論ファースト。コマンドは内部実行

### 1–3. スタンス／推奨案1つ／ツール選定
- 正は既存 project-GE（gate_511＋re_inquiry＋job worker）

### 4–10.
- Phase は小さく。CLAUDE.md / PROGRESS.md。完成時 HTML 説明図

---

## 最初に出力してほしいもの

⓪ 環境と連携（5〜7行）→ ① ロードマップ表 → ② Phase1 着手＋TODO
