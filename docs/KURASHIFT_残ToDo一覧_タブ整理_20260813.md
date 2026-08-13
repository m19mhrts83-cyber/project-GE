# KURASHIFT 残 ToDo 一覧（タブ整理用・2026-08-13）

**意図**: Cursor の plan タブを減らす。作業の正はここ。詳細・経緯は「元プラン」列から辿る。

入口（再開時）: [`KURASHIFT_実務者引き継ぎ.md`](./KURASHIFT_実務者引き継ぎ.md)  
棚卸し経緯: [`KURASHIFT_plan棚卸し_20260813.md`](./KURASHIFT_plan棚卸し_20260813.md)

plan 実体の場所: `~/.cursor/plans/<ファイル名>`

---

## いま開いてよいタブ（残作業があるものだけ）

この表以外の KURASHIFT 系 plan タブは **閉じてよい**（下の「閉じ用」参照）。

| # | 残 ToDo ID | 内容（要約） | いつ | 元プラン（辿り） |
|---|---|---|---|---|
| 1 | `verification-with-user`（目視残り） | 通し検証の**ログイン目視**（KPI・キャラメル2.55%・案件1件・Zaim live）。煙＋DBは済 | **次（軽）** | [`ライフプランhq再整理_c37d6392.plan.md`](~/.cursor/plans/ライフプランhq再整理_c37d6392.plan.md) · ログ [`KURASHIFT_通し検証ログ_20260813.md`](./KURASHIFT_通し検証ログ_20260813.md) |
| 2 | `wave2-re1` | V-2-UI（`/lifeplan` `/roi` `/tax` 通し）・案件 draft→内見。RE-1b は済 | **次（軽・①と重なる）** | [`qa実行プラン整理_b3b4e68d.plan.md`](~/.cursor/plans/qa実行プラン整理_b3b4e68d.plan.md) |
| 3 | `buy-plan-revise-modes` | 年1実績反映／Excel改訂→運営相談モード（現状は読取・評価のみ） | **検証後** | [`買い進め長期レーン_77a6bd3e.plan.md`](~/.cursor/plans/買い進め長期レーン_77a6bd3e.plan.md) |
| 4 | `re-a-plan-revise` | ③-A 計画補正ジョブ（dry-run→承認→Numbers/DB） | **検証後** | [`ライフプランhq再整理_c37d6392.plan.md`](~/.cursor/plans/ライフプランhq再整理_c37d6392.plan.md) |
| 5 | `phase-c-diff` | Next Action 深化・健美家等・スマホ承認 | **本線検証後・後回し可** | [`kurashift改善プラン_86acd2ee.plan.md`](~/.cursor/plans/kurashift改善プラン_86acd2ee.plan.md) |
| 6 | `lab-tachibana-gated` | 立花 API・少額実弾 | **Lab・本線外** | [`ライフプランhq再整理_c37d6392.plan.md`](~/.cursor/plans/ライフプランhq再整理_c37d6392.plan.md) |

**推奨順**: 1＋2（同じ目視セッションで可）→ 優先付け → 3 or 4 → 5 → 6は別枠。

---

## 閉じ用チェック（完了・吸収済み plan）

「全部終わったのを確認して消す」用。**タブを閉じても、必要ならパスで開き直せる。**

| plan ファイル | 状態 | メモ |
|---|---|---|
| [`不動産cf年次プロット_f7dfb2a6.plan.md`](~/.cursor/plans/不動産cf年次プロット_f7dfb2a6.plan.md) | **todo 全完了** | 本番反映済・`9f1f368` |
| [`融資提出パック設計_74653333.plan.md`](~/.cursor/plans/融資提出パック設計_74653333.plan.md) | **全完了** | ③-D |
| [`kurashift実務検証_fbf4058e.plan.md`](~/.cursor/plans/kurashift実務検証_fbf4058e.plan.md) | **全完了** | Sprint 突合 |
| [`kurashift_hq_overview_e49b0cea.plan.md`](~/.cursor/plans/kurashift_hq_overview_e49b0cea.plan.md) | **全完了** | 俯瞰確認のみ |
| [`trade_desk_方向再編_9c87a14e.plan.md`](~/.cursor/plans/trade_desk_方向再編_9c87a14e.plan.md) | **全 cancelled** | HQ 本線に吸収。**再開しない** |

---

## 残あり plan の「中身の扱い」

残 ToDo が1〜数個でも、plan 本体は長い。タブ運用のコツ:

| plan | pending 数 | タブの持ち方 |
|---|---|---|
| `ライフプランhq再整理_…` | 3（うち Lab1・検証目視1・補正1） | **残一覧だけ見てよい**。中身は ID 単位で開く |
| `買い進め長期レーン_…` | 1（改訂モード） | 検証後に開く。今は閉じて可 |
| `qa実行プラン整理_…` | 1（Wave2） | 目視と同時なら短時間だけ開く |
| `kurashift改善プラン_…` | 1（Phase C） | 後回し。閉じて可 |

---

## ID → 元プラン 早見（処置の辿り）

| ToDo ID | 元プラン名 | ファイル |
|---|---|---|
| `verification-with-user` | KURASHIFT 本線 | `ライフプランhq再整理_c37d6392.plan.md` |
| `re-a-plan-revise` | 同上 | 同上 |
| `lab-tachibana-gated` | 同上 | 同上 |
| `buy-plan-revise-modes` | 買い進め長期レーン | `買い進め長期レーン_77a6bd3e.plan.md` |
| `wave2-re1` | QA実行プラン整理 | `qa実行プラン整理_b3b4e68d.plan.md` |
| `phase-c-diff` | KURASHIFT改善プラン | `kurashift改善プラン_86acd2ee.plan.md` |

完了済みの大量 ID は各 plan の frontmatter（`status: completed`）を正とする。ここには載せない。

---

## 更新ルール（Jarvis）

- 残 ToDo を1つ閉じたら、**このファイルの表から消し**、元 plan の frontmatter を `completed` に同期する  
- 新しい本線 ToDo を足すときは、**元 plan に ID を付けてから**この表へ写す（ここだけに書かない）  
- タブ整理の入口は常にこのファイル＋実務者引き継ぎ
