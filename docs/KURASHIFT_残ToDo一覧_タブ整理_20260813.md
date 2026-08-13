# KURASHIFT 残 ToDo 一覧（タブ整理用・2026-08-13）

**意図**: Cursor の plan タブを1本に閉じる。作業の正はここ。詳細・経緯はアーカイブから辿る。

| 役割 | 場所 |
|---|---|
| **日常の正（このファイル）** | `docs/KURASHIFT_残ToDo一覧_タブ整理_20260813.md` |
| **生きている Cursor plan（1本）** | [`~/.cursor/plans/kurashift残バックログ_20260813.plan.md`](/Users/matsunomasaharu2/.cursor/plans/kurashift残バックログ_20260813.plan.md) |
| **閉じた経緯（読取専用）** | `~/.cursor/plans/_archive/kurashift/` |

入口（再開時）: [`KURASHIFT_実務者引き継ぎ.md`](./KURASHIFT_実務者引き継ぎ.md)  
棚卸し経緯: [`KURASHIFT_plan棚卸し_20260813.md`](./KURASHIFT_plan棚卸し_20260813.md)  
通し検証: [`KURASHIFT_通し検証ログ_20260813.md`](./KURASHIFT_通し検証ログ_20260813.md)

---

## 残 ToDo（生きている）

**2026-08-13 時点: 本線6 ID はすべて完了。** 生きている plan の frontmatter は手元で `completed` に揃えてよい（Jarvis は plan ファイル自体はユーザー指示で未編集の場合あり）。

| # | 残 ToDo ID | 状態 | メモ |
|---|---|---|---|
| 1 | `verification-with-user` | ✅ 完了 | ログイン目視ログ追記 |
| 2 | `wave2-re1` | ✅ 完了 | `/lifeplan` `/roi` `/tax`＋info→viewing |
| 3 | `buy-plan-revise-modes` | ✅ 完了 | buy-plan に評価／年次／運営相談バンド |
| 4 | `re-a-plan-revise` | ✅ 完了 | `re_revise_plan` ジョブ＋UI dry-run／承認 |
| 5 | `phase-c-diff` | ✅ 完了（MVP） | Next Action 深化・スマホ承認。健美家は対象外明記 |
| 6 | `lab-tachibana-gated` | ✅ ゲート維持 | Lab 掲示のみ。実弾なし |

新規本線 ToDo が出たら、生きている plan に ID を付けてからこの表へ写す。

---

## タブ運用

| 開いてよい | 閉じてよい |
|---|---|
| `kurashift残バックログ_20260813.plan.md` | 旧本線 plan すべて（実体は `_archive/kurashift/`） |
| この docs（残 ToDo 一覧） | 完了済み・cancelled のアーカイブ（参照時だけ開く） |

---

## アーカイブ索引（閉じた plan）

パス先頭: `~/.cursor/plans/_archive/kurashift/`

| ファイル | 役割 | メモ |
|---|---|---|
| `ライフプランhq再整理_c37d6392.plan.md` | 本線 HQ（①②③） | 残 ID の一部は上表へ移管 |
| `買い進め長期レーン_77a6bd3e.plan.md` | ③-B 長期→実行 | `buy-plan-revise-modes` |
| `qa実行プラン整理_b3b4e68d.plan.md` | QA Waves | `wave2-re1` |
| `kurashift改善プラン_86acd2ee.plan.md` | QAゲート／Phase | `phase-c-diff` |
| `不動産cf年次プロット_f7dfb2a6.plan.md` | 想定vs実績プロット | **完了**（`9f1f368`） |
| `融資提出パック設計_74653333.plan.md` | ③-D | **完了** |
| `kurashift実務検証_fbf4058e.plan.md` | Sprint 突合 | **完了** |
| `kurashift_hq_overview_e49b0cea.plan.md` | HQ俯瞰 | **完了** |
| `trade_desk_方向再編_9c87a14e.plan.md` | 旧議論 | **cancelled・再開しない** |

各アーカイブ先頭に `ARCHIVED 2026-08-13` 注記あり。

---

## 更新ルール（Jarvis）

- 残 ToDo を1つ閉じたら、**このファイル**を更新。生きている Cursor plan はユーザーが「plan も更新して」と言ったときだけ触る
- 新しい本線 ToDo を足すときは、**生きている plan に ID を付けてから**この表へ写す（アーカイブだけに書かない）
- 旧 plan は `_archive/kurashift/` の参照専用。pending 履歴は壊さない
- タブ整理の入口は常にこのファイル＋実務者引き継ぎ＋生きている plan 1本
