# 運用手順 — Q&A 負荷と障害対応（Phase 14・フェーズ1）

最終更新: 2026-07-22

対象: Raimo Q&A + Supabase `kamiooya-qa`（意味検索 Edge）

## 平常監視

| 頻度 | 何を見るか |
|------|------------|
| 随時 | Raimo 管理メニュー **運営分析**（通常／意味の比率・**失敗・停止**件数） |
| 週1 | [Google AI Studio](https://aistudio.google.com/) の利用量・課金感 |
| 随時 | Supabase Dashboard → Project `kamiooya-qa` の Health / Edge ログ |

Phase 14 フェーズ2（日次上限の数値など）は、意味検索が数週間／数十件溜まってから判断する。

## 緊急: 意味検索だけ止める（キルスイッチ）

コード再デプロイ不要。

1. Supabase Dashboard → Project `kamiooya-qa` → **Edge Functions** → Secrets  
   または CLI: `supabase secrets set SEMANTIC_SEARCH_DISABLED=1 --project-ref mwubzgefkkjjbingrmqu`
2. ユーザーには「意味検索は一時停止中。通常検索（意味検索モードOFF）を」と出る（HTTP 503）
3. **通常検索はそのまま使える**
4. 再開: `SEMANTIC_SEARCH_DISABLED` を削除するか `0` にする

確認: 運営分析の「失敗・停止」と直近イベントの結果列に `停止` が増える。

## 症状 → 対処

| 症状 | まずやること |
|------|--------------|
| 意味検索だけ失敗／503 | キルスイッチが ON になっていないか。ON なら意図確認。OFF なら Edge ログ |
| 全体が遅い | 通常検索に切替を案内。意味検索の同時連打を避ける（二重送信ガードあり） |
| 回答が空／エラー | 運営分析の失敗件数・直近「エラー」。Gemini 枠切れも疑う |
| Edge timeout 感 | 意味検索は最大約150秒。連打せず待つ。頻発ならフェーズ2で上限検討 |
| DB が読めない | RLS 後は **service_role** 必須。anon 直叩きは拒否が正常 |

切り分け順: **通常検索で代替** → **意味検索キル** → Edge ログ → Gemini 利用量 → Supabase Free 使用量

## Free 枠・課金

会員規模の試算・運営向け要約: [`ランニングコスト試算_会員規模.md`](./ランニングコスト試算_会員規模.md)

| サービス | 本番の目安 |
|----------|------------|
| **Gemini** | Free 枠は日次上限で本番不可。**Paid 従量**。段階公開で月数千〜数万円、本格で月数万〜十数万円になりうる |
| **Supabase** | 休止・容量・バックアップのため **Pro（約 $25／月）推奨**。Team は通常不要 |

- 逼迫・公開拡大時は **合意のうえ** Pro 化・キー移管（Phase 5）を実施
- 本手順では「見る」まで。自動アラート連携は未実装
- 週次: AI Studio の利用金額＋運営分析の日次件数を突き合わせる

## 関連

- フェーズ管理: 同フォルダ `フェーズ管理.md`（Phase 14）
- コスト試算: `ランニングコスト試算_会員規模.md`
- 分析 API: Edge `qa-analytics` / テーブル `app_qa_search_events`（`result_status`: ok / error / disabled / rate_limited）
