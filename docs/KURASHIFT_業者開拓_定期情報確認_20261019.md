# KURASHIFT 業者開拓 — 定期情報確認（nurture · 2026-10-19）

初回コンタクト済みの不動産会社へ、**約2ヶ月ごと**に「物件情報はありますか？」系の確認を送る。  
反響は **最新1件だけ** YAML／投影に残す（履歴フルは不要）。

## 方針（4点）

| 柱 | 内容 |
|---|---|
| **入口** | `kurashift_re_vendor_list.yaml`（S2。将来 S9 も同型）。`contacted_at` がある社＝対象候補 |
| **確認** | 承認済み**定型**文面は開拓定型と同じく都度許可不要。非定型・個別事情は松野一度確認 |
| **履歴** | `nurture_last_sent_at`／`nurture_last_reply_*`（最新のみ）。due 一覧は `.jarvis_state/vendor_nurture_due.json` |
| **停止** | `config/kurashift_vendor_nurture.yaml` の `disabled` または `JARVIS_VENDOR_NURTURE_DISABLE=1`。`status: skip\|invalid` は除外 |

## 期限ロジック（確定）

次を満たす社が due:

1. 初回コンタクト済み（`contacted_at` あり、または `status` が `contacted` / `replied`）
2. **最終アウトバウンドから `interval_days`（既定60）以上経過**

最終アウトバウンド日 =

```
max(contacted_at, nurture_last_sent_at)
```

（「初回から2ヶ月」と「メールが2ヶ月空いたら」は、この max で同じ式になる）

## 反響（最新のみ）

| フィールド | 意味 |
|---|---|
| `nurture_last_reply` | `none` \| `replied` \| `ignored`（任意） |
| `nurture_last_reply_at` | 返信／反応を記録した日 |
| `nurture_last_reply_note` | 短いメモ（1行） |

新しい反応が来たら上書き（履歴配列は持たない）。

## レーン・実行

| 誰 | 役割 |
|---|---|
| Jarvis | due 抽出・state・（後続）outbox キュー／YAML mark |
| Grok S2 | 定型送信・`--mark`（初回開拓と同型） |
| 516 | 見守り相乗り（将来: stall に nurture due 件数） |

## コマンド

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
# due 一覧
~/selenium_env/venv/bin/python scripts/jarvis_vendor_nurture_due.py --dry-run
~/selenium_env/venv/bin/python scripts/jarvis_vendor_nurture_due.py --apply
# 定型プレビュー
~/selenium_env/venv/bin/python scripts/jarvis_vendor_nurture_due.py \
  --preview --vendor-name '〇〇不動産' --list-region chubu
# 次に送る候補（due 優先。0なら soon）
~/selenium_env/venv/bin/python scripts/jarvis_vendor_nurture_due.py --next 3
# 送信後 mark
~/selenium_env/venv/bin/python scripts/jarvis_vendor_nurture_due.py --mark chubu-001
# Grok キュー（template.approved: true のときのみ）
~/selenium_env/venv/bin/python scripts/jarvis_vendor_nurture_due.py --queue-outbox
```

`--apply` は due 一覧を state に書くだけ（**送信しない**）。  
`--queue-outbox` は Drive `outbox_to_teams/re/` へ Grok S2 用キューを書く（実送信は Grok）。

## フェーズ

| Phase | 内容 | 状態 |
|---|---|---|
| **1** | 設計・設定・due 抽出・state | **済** |
| **2** | 定型文面＋ preview／next／mark／queue-outbox | **本ドキュメント（文面は松野確認後 `approved: true`）** |
| **3** | 返信 triage → `nurture_last_reply_*` 自動更新・UI 列 | 未 |
| **4** | S9（管理会社）同型 | 未 |

## 関連

- 閉ループ: `docs/KURASHIFT_業者開拓_閉ループ_20261015.md`
- 設定: `config/kurashift_vendor_nurture.yaml`
- リスト例: `config/kurashift_re_vendor_list.example.yaml`
- Todoist: 【不動産業者開拓】定期情報確認メール自動化
