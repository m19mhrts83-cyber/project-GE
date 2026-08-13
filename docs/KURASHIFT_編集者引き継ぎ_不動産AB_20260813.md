# 編集者向け引き継ぎ — 不動産 ③-A / ③-B（2026-08-13）

本番: https://jarvis-trade-desk.vercel.app/  
対象アプリ: `apps/trade-desk`（KURASHIFT）

## 意図（顧客＝松野）

- 不動産を **4レーン** で分ける（混ぜない）
- **A**: 今持っている資産の運用・進捗（CF・返済余裕）
- **B**: 買い進めを **長期プラン（トップダウン）→ 今狙う条件 → 千三つ実行** の順で見る
- ライフプランと同じく「長期で見える」ことが買い進めの要

## 参照した正本・知見

| ソース | 取り込み |
|---|---|
| Notion「物件買い進め条件」 | 戸建・利回20%・300万以下・土地値60%・愛知中心エリア → Focus 補助表示 |
| Notion「物件買い進めプランニング」＋STEP3 運営FB | 個人／法人使い分け、戸建売却で資金回復、カードローン禁じ手、運転資金は使途明確 |
| 神大家 STEP3-3 文字起こし | トップダウン、部品化（購入／売却／フリー・運転）、PDCA |
| Tavily（業界定番） | **DSCR**（簡易: 月家賃÷月返済）を KPI に採用。目安 1.2× |

## 実装した画面

| レーン | URL | 内容 |
|---|---|---|
| A | `/realestate?scope=combined\|personal\|corporate` | Portfolio KPI（RR・返済・DSCR・YTD CF）、名義切替、B-RATE＋DSCR、CF50万ギャップ |
| B プラン | `/realestate/buy-plan` | Excel canonical 年表、KPI、今狙う条件、銀行枠、ingest/export |
| B 実行 | `/realestate/deals` | 千三つファネルに寄せ。条件は要約のみ。プランへ誘導 |
| 共通 | 全 `/realestate/*` | `RealEstateLaneNav` |

## 主要ファイル

- `components/RealEstateLaneNav.tsx`
- `lib/reDscr.ts`
- `app/realestate/page.tsx`（A）
- `app/realestate/buy-plan/page.tsx`（B 新規）
- `app/realestate/deals/page.tsx`（B 実行）
- 既存 C/D はナビ追加＋C に DSCR

## QA 回付（2026-08-13）

- 実行プラン: [`KURASHIFT_品質保証点検_実行プラン_20260813.md`](./KURASHIFT_品質保証点検_実行プラン_20260813.md)
- **点検ログ（実務者へ）**: [`KURASHIFT_品質保証点検ログ_20260813.md`](./KURASHIFT_品質保証点検ログ_20260813.md)
- Wave0: P0 なし。③骨格は条件付き合格。本線全満足は未宣言

## 編集者へのお願い（次の一手）

1. **文言・トーン**: レーンラベル・Focus の「今狙う」文言を顧客口調に整える
2. **年表の読みやすさ**: `action` 列の日本語正規化（購入／売却／調達の色分けやアイコン）← QA P1
3. **A の計画 vs 実績**: YTD は Zaim 投影のみ。年計画バーは未実装 → コピー案があれば（Wave2）
4. **Notion 条件と Excel criteria の同期**: Focus の Notion 要約は静的。鮮度が落ちたら Excel 正本に寄せる or Notion fetch 化
5. **スクリーンショット**: A の KPI 帯・B の年表・千三つの導線を撮って docs に1枚

## やらない／未着手（意図的）

- 厳密 NOI ベースの DSCR（経費控除なし簡易）
- ③-A の計画補正ジョブ
- 自動問い合わせ送信

## 確認コマンド

```bash
cd ~/git-repos/apps/trade-desk && npx tsc --noEmit
npx vercel deploy --prod --yes
```
