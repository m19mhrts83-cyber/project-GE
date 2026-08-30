# 融資アプローチ先・銀行別検討材料（KURASHIFT / Jarvis）

## 目的

- Excel「★金融機関一覧(アプローチ先まとめ)」の **アプローチ候補** を DB／画面に載せる
- 神大家セミナー（STEP3）の観点で銀行別メモを構造化
- 神大家 Q&A（`kamiooya-qa` 読取）と OneDrive `10_【購入】物件購入,融資` を材料に補完

## 正本

| 役割 | パス |
|---|---|
| アプローチ先シード | `config/kurashift_lenders_approach.yaml` |
| 同期 | `scripts/jarvis_kurashift_lenders_sync.py` |
| DDL | `apps/jarvis-dashboard/supabase/migrations/20260830_kurashift_lenders_glucon_materials.sql` |
| UI | KURASHIFT `/realestate/lenders` |
| 提出パック | `/realestate/finance-pack`（③-D） |

## コマンド

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
# DDL（初回）
~/selenium_env/venv/bin/python scripts/jarvis_supabase_apply_sql.py \
  apps/jarvis-dashboard/supabase/migrations/20260830_kurashift_lenders_glucon_materials.sql
# シード＋セミナー／OneDrive（＋任意で Q&A）
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_lenders_sync.py --apply --with-kamiooya
```

## セミナーから使う観点（STEP3）

- 金融機関の種類（アパートローン／地銀／信金／担保ローン／提携）
- 年収条件・得意物件・金利目安・フルローン可否・提携業者
- **初回しか使えない先を先に**、後から使える先は後ろ

## アプローチ先の読み方（2026-08-30 Excel）

- ○ = アプローチ候補（`approach=yes`）— シード上 **28**
- △ = 検討（`maybe`）— **7**
- 静岡など × = `no`（事例メモは intel に残しうる）— **1**
- **画面の「36行」** = 上記合計（active 全件）。「アプローチ候補だけ」と言うときは **yes=28**
- 全国枠のオリックス／滋賀／西京／auじぶん = 候補として載せる
- DDL の `deferred` / `watch` enum は **当面シード未使用**（Excel「後回し」は `maybe`/`no` に吸収）

## 買い進めとの接続（点検是正 · P2）

| 層 | 現状 | 是正（顧客 Q4 推奨A） |
|---|---|---|
| UI | `/lenders` ↔ `/finance-pack` リンクのみ | 維持 |
| Grok | ローンBot / S7 に lenders 言及なし | 打診前に `/realestate/lenders` の `approach=yes` を見る **1行を paste に追加** |
| 提出パック実体 | OneDrive `240_融資/finance_packs/…` | 変更なし。アプローチ順の判断材料として lenders を先に見る |

**別ファイル**: `240_融資/240_融資傾向調査.xlsx` は **傾向メモ用途**（顧客 Q5 推奨A）。アプローチ先の正本は本 YAML のみ。

## 点検参照

`docs/アプリ点検結果_融資Grok週次_20260830.md`
