# ルール帳 — 814 Jarvisダッシュボード更新係

ダッシュボードの使い勝手。担当社員がいない画面（投資・資産運用）も当面ここで預かる。松野さんの判断ログ（owner_decisions）から 314 業務品質監査係が土曜に候補を作り、
loopware で「採用」したものだけを ## 確定ルール に足す（1ルール=1コミット。取り消しは revert）。
読む側: `scripts/jarvis_learned_rules.py`（点検: `python3 scripts/jarvis_learned_rules.py <このファイル>`）。
効かせたルール番号は判断ログの payload.applied_rules に残り、効いたかを週次で数える。

書き方（1行1ルール、| 区切り）:
`- R<社員>-<連番> | hide / boost+N / demote-N / rewrite / keep | 条件 | scope=once/partner/always | v1 YYYY-MM-DD | 根拠 <判断ログid,...> | メモ`
条件は from:addr / from:@domain / domain: / subject: / partner: / lane: / kind:、「&」で複数、「*」で全部。例: `*`

## 確定ルール

（最大10行。まだありません）

## 仮説

（効かせない候補。週次で確かめる）

## 例外

（keep。確定ルールの hide・demote を打ち消す）

## 参照例

（下書きの手本。相手ごとに2件まで）
