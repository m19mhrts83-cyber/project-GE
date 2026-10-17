# 2026-10-17 — Cursor×別Agent 比較実験（Cursor／Jarvis 実行分）

- 実験: `6hmrRCwjPjGQ43Mv`
- 実行ツール: **Cursor（Jarvis）**（executor=cursor）
- Agent: 114 物件一次判定係
- 結果: **成功**（`--dry-run` のみ）

## 所要時間

| 区間 | 時間 |
|---|---|
| acquire → dry-run → release | 約 2 秒（壁時計） |
| 本線コマンド | exit 0（GenCode と同結果） |

## 結果（dry-run）

```
KURASHIFT_RESULT:{"ok": true, "count": 153, "lanes": {"A": 1, "B": 33, "C": 119}, "b_posted": 0, "b_deferred": 0}
```

- ログ: `logs/20261017_231042_gate114.md`

## 通ったチェック

- [x] 入力 153件
- [x] 本線コマンド動いた
- [x] A/B/C がログに残った（GenCode と同じ内訳）
- [x] To未解決で全停止なし
- [x] 秘密を書いていない
- [ ] B の `#consult` 投稿 — dry-run のため未実施

## 修正回数

- **0回**

## 所見

- 同一入力・同一コマンドなら Cursor と GenCode で振分結果は一致した。
- 差は「会話UIでの手順追従・記録の丁寧さ」側（GenCode は比較ログを自前で残した）。CLI 品質差は今回ほぼ無し。
