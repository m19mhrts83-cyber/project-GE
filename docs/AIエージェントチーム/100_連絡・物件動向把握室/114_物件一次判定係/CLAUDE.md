# 物件一次判定係

ID: **114**。Grok S1 調査後の **進行ゲート（3レーン振分）**。  
調査本文の再発明はしない。問合せ送信は **511**。

## AIオートメーション（作業フロー）

- **FlowForge（開く）**: [flow_O1OMOoN2vkVf9SKLD9T_mvBy](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_O1OMOoN2vkVf9SKLD9T_mvBy)
- **実行本線**: Mac CLI／launchd（Cursor 不要）— [`flow.md`](./flow.md)
- 正本: [`23_物件進行ゲート_Grok調査_20261012.md`](../../23_物件進行ゲート_Grok調査_20261012.md)
- 上限時: [`24_Jarvis上限時_物件進行ゲート_次善策_20261012.md`](../../24_Jarvis上限時_物件進行ゲート_次善策_20261012.md)
- CLI: `scripts/jarvis_property_gate_114.py` · `jarvis_property_gate_degraded.py`

## 1. 役割

- やること:
  - deals／`[Grok調査]` 要約からレーン **A / B / C** を振る
  - B → Slack `#consult` カード（位置づけ明記・要点箇条書き・詳細HTML表・Yes/No URL。コードブロック表は使わない）
  - C → `#report` ダイジェスト（1日まとめて可）
  - A → `#report` 1行＋511／Tier へ渡す合図
  - handoff 誤ラベルを `awaiting_first_inquiry` へ heal
- やらないこと: Web 再調査・対外送信・了承なしの close

## 2. 動き出す合図

- [x] 何かが届いたら（Grok 取込後・朝バンドル／昼 noon）
- [x] 時間（毎日 11:15 launchd）
- [x] 人が頼む（`--deal-id` / `--scan` / `degraded.py`）

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| CLI | ○ | `gate_114` / `degraded` |
| launchd | ○ | `property-gate-114` 11:15 |
| Slack Webhook | ○ | `#consult` / `#report` |
| ブラウザ | × | |
| Cursor 会話 | △ | あってもよいが必須ではない |

## 4. 報告先

| 種別 | 行き先 |
|---|---|
| B 要判断 | Slack `#consult` |
| A/C | Slack `#report` |

## 5–6. 成果物・手順

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_property_gate_degraded.py
~/selenium_env/venv/bin/python scripts/jarvis_property_gate_114.py --scan --post
~/selenium_env/venv/bin/python scripts/jarvis_property_gate_114.py --deal-id UUID --post
```

ログ: このフォルダ `logs/` · Mac `~/Library/Logs/jarvis_property_gate/`

## 7. 改善ログ

| 日付 | 変更 |
|---|---|
| 2026-10-09 | 候補フォルダ作成 |
| 2026-10-12 | 進行ゲート具体化（3レーン・Slack）。状態＝運用確認中 |
| 2026-10-12 | **作業フロー更新**: launchd／degraded 本線・上限時手順を `flow.md` に反映 |
