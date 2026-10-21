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

### Slack 書き出し（FRIDAY／Jarvis 共通）

| ch | いつ |
|---|---|
| `#report` | 完了・定型・生存確認 |
| `#consult` | 要判断。末尾「次の担当」3行必須 |
| `#ops` | 障害・失敗・枠切れ |

`#consult` 末尾: `次: Grokで続行 | Jarvisに依頼 | 人判断のみ` ＋ `担当メモ` ＋ `橋渡し`  
正本: [`38_Slack書き出し_FRIDAY_Jarvis_20261018.md`](../../38_Slack書き出し_FRIDAY_Jarvis_20261018.md) · [`36_`](../../36_Slack_consult手渡し_次の担当_20261018.md)

## 5–6. 成果物・手順

- 依頼・完了条件: [`TASK.md`](./TASK.md)
- 検証: [`tests/checklist.md`](./tests/checklist.md)
- 規格: [`30_共通Agentフォルダ規格_BCP`](../../30_共通Agentフォルダ規格_BCP_20261017.md)

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
| 2026-10-21 | Slack件名: `AIチーム` を外し、`114・物件一次判定`＋A/B/Cレーンの意味（自動進行／要人判断／報告のみ）を明記 |
| 2026-10-13 | Slack Bカード: コードブロック表廃止→箇条書き＋詳細HTML。カード先頭に位置づけ（Grok S1／114／511）を明記。表示名「114 物件一次判定」 |
| 2026-10-13 | Bカードに **土地値の評価**／**利回りの評価** を独立節として詳述（基準・クリア/惜しい/未達）。先頭に判断軸1行。詳細HTMLも同軸カード |
| 2026-10-17 | 共通フォルダ規格パイロット: TASK.md / config / input / output / tests / scripts |
