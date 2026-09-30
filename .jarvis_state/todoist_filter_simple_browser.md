# Cursor 中央に Web／Todoist を出す — 調査メモ（2026-09-21）

## 結論（Todoist 公式 UI）

| 手段 | 中央表示 | Todoist 公式が実用か |
|---|---|---|
| Simple Browser | エディタ内 | **不可寄り**（今回エラー） |
| Cursor Browser（Agent 用） | Cursor 内ペイン | **部分可**（ログイン画面は出るが不安定／Chrome セッション非共有） |
| Chrome＋Cursor 左右分割 | 中央ではない | **実用本線** |
| 自前ダッシュボード投影 | Simple Browser／ローカル可 | **通知・一覧なら可**（公式 UI ではない） |

**公式 Todoist を Cursor 中央で日常操作する、は推奨しない／現状はほぼ無理に近い。**

## なぜ Simple Browser で落ちるか

- VS Code／Cursor の Simple Browser はページを **iframe／埋め込み WebView** で開くことが多い
- Todoist はクリックジャッキング対策・スクリプト制限・CDN 読込の都合で、埋め込み環境で  
  「Todoist couldn't load the required files」等になりやすい（実測あり）
- ヘッダに `X-Frame-Options` / `frame-ancestors` が無くても、**埋め込み専用の失敗**は起きる

→ 「あらゆる方法」でも、**相手サイトが埋め込みを想定していない**限り突破は不安定／非推奨（ヘッダ改ざんはセキュリティ上やらない）

## Cursor Browser（docs: cursor.com/docs/agent/tools/browser）

- Agent 用の **本物に近い Chromium**。チャット横のペイン／別窓で表示できる
- 実測: `app.todoist.com` は一度失敗表示のあと **ログイン画面までは表示**できた
- ただし:
  - Chrome のログイン状態は **引き継がない**（workspace 隔離クッキー）
  - Google ログインは埋め込みブラウザで止まりやすい
  - 主用途は **開発・検証・Agent 操作**であり、日常のフィルタ設定 UI 向きではない

## 「中央に通知を出して捗る」への現実解

1. **本線**: Chrome（または Todoist デスクトップ）↔ Cursor チャットを画面分割  
2. **将来の中央表示**: Jarvis ダッシュボード等に **タスク／要連携の投影**を載せ、それを Simple Browser か localhost で中央表示（自前ページなので埋め込み可）  
3. **やらない**: Requestly 等で Todoist の frame 制限を外す・非公式埋め込みハック

## 朝レビュー順（Todoist）

要連携 → SecondBrain → パッと → **GenMail要対応（提案）** → オーナー確認 → その他未着手

GenMail: admin 集約。入口 `.jarvis_state/genmail_action_needed.md` → `scripts/jarvis_todoist_genmail_propose.py`

## 参照

- https://cursor.com/docs/agent/tools/browser
- CSP `frame-ancestors` / X-Frame-Options（埋め込み拒否の一般論）
- `docs/Todoist_タスク正本_設計_20260921.md`
