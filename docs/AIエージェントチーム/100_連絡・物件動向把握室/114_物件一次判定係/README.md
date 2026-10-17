# 【運用確認中】物件一次判定係 — 一目でわかる1枚

| 項目 | 内容 |
|---|---|
| 社員ID | **114**（AIエージェントチーム／100室） |
| 役割 | Grok調査後の A/B/C 振分と Slack カード（**調査そのものは Grok S1**） |
| 位置づけ | Grok=[Grok調査]作成 → **114=振分・#consult通知** → 人=Yes/No → **511=送信** |
| きっかけ | Grok取込後／毎日11:15／手動 |
| 報告 | B=`#consult`（要点＋詳細HTML表）、A/C=`#report` |
| Slack体裁 | コードブロック表は使わない（モバイル崩れ防止）。表は `/api/g/d/{deal}` |
| 実行 | `jarvis_property_gate_degraded.py`（本線） |
| 正本 | [23_物件進行ゲート…](../../23_物件進行ゲート_Grok調査_20261012.md) |
| 上限時 | [24_次善策…](../../24_Jarvis上限時_物件進行ゲート_次善策_20261012.md) |
| 作業フロー | [flow.md](./flow.md) · [FlowForge](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_O1OMOoN2vkVf9SKLD9T_mvBy) |
| 指示 | [CLAUDE.md](./CLAUDE.md) |
| 今回の依頼 | [TASK.md](./TASK.md)（共通規格パイロット） |
| 検証 | [tests/checklist.md](./tests/checklist.md) |
