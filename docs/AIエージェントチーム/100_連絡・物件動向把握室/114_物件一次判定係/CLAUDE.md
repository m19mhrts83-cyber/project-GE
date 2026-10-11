# 物件一次判定係

ID: **114**。Grok S1 調査後の **進行ゲート（3レーン振分）**。  
調査本文の再発明はしない。問合せ送信は **511**。

## AIオートメーション

- FlowForge: [flow_O1OMOoN2vkVf9SKLD9T_mvBy](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_O1OMOoN2vkVf9SKLD9T_mvBy)
- 正本: [`23_物件進行ゲート_Grok調査_20261012.md`](../../23_物件進行ゲート_Grok調査_20261012.md)
- CLI: `scripts/jarvis_property_gate_114.py`

## 1. 役割

- やること:
  - deals／`[Grok調査]` 要約からレーン **A / B / C** を振る
  - B → Slack `#consult` カード（deal_id・見てほしい3点・Yes/No）
  - C → `#report` ダイジェスト（1日まとめて可）
  - A → `#report` 1行＋511／Tier へ渡す合図
- やらないこと: Web 再調査・対外送信・了承なしの close

## 2. 動き出す合図

- [x] 何かが届いたら（Grok 取込後・deals 更新）
- [x] 人が頼む（`--deal-id` / `--scan`）
- [ ] 時間（将来 GHA）

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| CLI | ○ | `jarvis_property_gate_114.py` |
| Slack Webhook | ○ | `#consult` / `#report` |
| ブラウザ | × | |

## 4. 報告先

| 種別 | 行き先 |
|---|---|
| B 要判断 | Slack `#consult` |
| A/C | Slack `#report` |

## 5–6. 成果物・手順

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_property_gate_114.py --scan --post
# 1件
~/selenium_env/venv/bin/python scripts/jarvis_property_gate_114.py --deal-id UUID --post
```

ログ: このフォルダ `logs/`

## 7. 改善ログ

| 日付 | 変更 |
|---|---|
| 2026-10-09 | 候補フォルダ作成 |
| 2026-10-12 | 進行ゲート具体化（3レーン・Slack）。状態＝運用確認中 |
