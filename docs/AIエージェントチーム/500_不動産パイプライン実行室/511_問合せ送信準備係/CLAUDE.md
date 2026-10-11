# 問合せ送信準備係

ID: **511**。Slack **Yes**（または Aレーン）のあと、既存 KURASHIFT 問合せ送信を実行する。  
Grok 調査の再発明はしない。

## AIオートメーション（作業フロー）

- **FlowForge（開く）**: [flow_Gr7OKXW7L1ElR7yW_XbBCbNH](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_Gr7OKXW7L1ElR7yW_XbBCbNH)
- **実行本線**: Mac CLI ＋ `kurashift_jobs`（Cursor 不要）— [`flow.md`](./flow.md)
- 正本: [`23_物件進行ゲート_Grok調査_20261012.md`](../../23_物件進行ゲート_Grok調査_20261012.md)
- 上限時: [`24_Jarvis上限時_物件進行ゲート_次善策_20261012.md`](../../24_Jarvis上限時_物件進行ゲート_次善策_20261012.md)
- CLI: `scripts/jarvis_property_gate_511.py`
- 受信: `/api/slack/consult-action`（jarvis-dashboard）

## 1. 役割

- やること:
  - Yes／A → `re_deal_inquiry_send`（B の Yes＝対外了承。追加チャット確認なし）
  - No → inquiry クローズ（見送り）
  - 失敗（To 未解決等）を `#consult` に短く返す
  - 二重送信防止
- やらないこと: 調査やり直し・Yes なしの送信（A／Tier3 除く）

## 2. 動き出す合図

- [x] 何かが届いたら（Slack Yes／consult-action）
- [x] 人が頼む（`--deal-id --yes` / `--no`）
- [ ] 時間（送信自体はイベント駆動）

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| CLI | ○ | gate_511 |
| Gmail API | ○ | 問合せ送信（job worker） |
| Slack | ○ | 結果1行 |
| Vercel API | ○ | consult-action |
| Cursor 会話 | △ | 必須ではない |

## 4. 報告先

| 種別 | 行き先 |
|---|---|
| 送信結果 | `#consult`（主）／`#report` |
| 要判断（To 欠落） | `#consult` |

## 5–6. 手順

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_property_gate_511.py --deal-id UUID --yes
~/selenium_env/venv/bin/python scripts/jarvis_property_gate_511.py --deal-id UUID --no
~/selenium_env/venv/bin/python scripts/jarvis_property_gate_511.py --deal-id UUID --yes --dry-run
```

## 7. 改善ログ

| 日付 | 変更 |
|---|---|
| 2026-10-09 | Phase C スタブ |
| 2026-10-12 | Yes/No → 既存 re_inquiry 接続。状態＝運用確認中 |
| 2026-10-12 | **作業フロー更新**: consult-action／ジョブ／冪等を `flow.md` に反映 |
