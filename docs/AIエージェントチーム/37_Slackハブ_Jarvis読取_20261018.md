# Slack ハブ — Jarvis 読取・FRIDAY／Grok 共有（2026-10-18）

## 結論（意見→方針）

| 層 | 正 | 理由 |
|---|---|---|
| **見える共有・残す報告** | Slack `#report` / `#consult` / `#ops` | 人・Jarvis・FRIDAY・Grok が同じタイムラインを見られる |
| **Mac 実行の手渡し** | Drive `【with Grok bot】` inbox／outbox | 秘密・長文・スクリプトキックは Drive のまま（フォーク維持） |
| **Cursor 本題** | Jarvis がセッションで Slack を読んで気づく | 都度「Slack見て」と言わなくてよい |

**Grok のフォルダを捨てて Slack だけ、にはしない。**  
壁打ちは Grok チャンネル可。**残す判断・成果・要次手は Slack に載せる**方向へ寄せる（既に `action: slack_report`）。

**FRIDAY（GenCode）× Jarvis** も同じ。ツール横断で必要な共有は Slack に残し、Cursor がその差分を拾う。

## Cursor（Jarvis）の動き

ルール: `.cursor/rules/jarvis-slack-hub-watch.mdc`

1. トリガー時に Slack MCP で `#consult` → `#ops` → `#report` を読む  
2. 前回以降の新規があれば、本題の前後に **1ブロック**で「こういった更新もあります」  
3. `jarvis_slack_hub_watch.py --mark-prompted` で再掲抑制

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_slack_hub_watch.py --hints
# MCP読取後
~/selenium_env/venv/bin/python scripts/jarvis_slack_hub_watch.py --mark-prompted \
  --summary 'consult: … / ops: …'
```

設定: `config/slack_ai_team_hub.yaml`  
state: `.jarvis_state/slack_hub_watch.json`  
無効化: `JARVIS_SLACK_HUB_WATCH_DISABLE=1` または state `"disabled": true`

## FRIDAY／Grok への期待（人の橋渡し期）

| 誰 | Slack に載せるもの |
|---|---|
| **FRIDAY** | 実装完了・要判断・Jarvis に渡す要点（`#report`／迷い `#consult`） |
| **Grok** | 定型・要ボス（既存 `slack_report`）。末尾「次の担当」は [`36_`](36_Slack_consult手渡し_次の担当_20261018.md) |
| **Jarvis** | 同上＋セッションで差分をチャットに相乗り |

**どの ch・末尾型の書き方1節（正本）**: [`38_Slack書き出し_FRIDAY_Jarvis_20261018.md`](./38_Slack書き出し_FRIDAY_Jarvis_20261018.md)

## Drive との役割分担（移行の実態）

```
Grok 壁打ち・長考     → Grok チャンネル（今までどおり可）
残す報告・要判断      → Slack（本線）
Mac 実行依頼・秘密なし長文 → Drive inbox（Jarvis poll）
Cursor で作業中       → Slack を読んで「変化に気づく」
```

## 入口・確認・履歴・停止

- 入口: Slack 3ch ＋ MCP／任意 API token  
- 確認: 松野は `#consult` を見る。Jarvis はチャットに差分を出す  
- 履歴: Slack 本体 ＋ state `last_summaries`  
- 停止: disable env／state

## 関連

- consult 手渡し: [`36_`](36_Slack_consult手渡し_次の担当_20261018.md)
- Grok 定型: [`17_`](17_Grok定型報告_Slack_20261010.md)
- 日次集約: [`33_`](33_Slack日次集約_第1段階_20261017.md)
- フォーク: `config/grok_jarvisbox_fork_policy.md`
