# ルール帳 — 116 メール要対応係

Slack #consult に出すメールの選び方（出さない・上げる・下げる）。松野さんの判断ログ（owner_decisions）から 314 業務品質監査係が土曜に候補を作り、
loopware で「採用」したものだけを ## 確定ルール に足す（1ルール=1コミット。取り消しは revert）。
読む側: `scripts/jarvis_learned_rules.py`（点検: `python3 scripts/jarvis_learned_rules.py <このファイル>`）。
効かせたルール番号は判断ログの payload.applied_rules に残り、効いたかを週次で数える。

書き方（1行1ルール、| 区切り）:
`- R<社員>-<連番> | hide / boost+N / demote-N / rewrite / keep | 条件 | scope=once/partner/always | v1 YYYY-MM-DD | 根拠 <判断ログid,...> | メモ`
条件は from:addr / from:@domain / domain: / subject: / partner: / lane: / kind:、「&」で複数、「*」で全部。例: `from:news@example.com`

## 確定ルール

- R116-001 | hide | from:info@chat-work.com | scope=partner | v1 2026-11-09 | 根拠 34,35,36 | info@chat-work.com からのメールは、次から判断デスクにも Slack にも出しません

## 仮説

（効かせない候補。週次で確かめる）

## 例外

（keep。確定ルールの hide・demote を打ち消す）

## 参照例

（下書きの手本。相手ごとに2件まで）
