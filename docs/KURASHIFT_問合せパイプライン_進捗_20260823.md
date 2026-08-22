# KURASHIFT 問合せパイプライン — 進捗正本（2026-08-23）

**用途**: Cursor plan がすべて「完了」に見えても、ここが **実装済 / 作業中 / 未実装** の正本。  
**設計**: [`KURASHIFT_RE_業者開拓_物件候補_実務者設計_20260823.md`](KURASHIFT_RE_業者開拓_物件候補_実務者設計_20260823.md)  
**生きている plan**: `~/.cursor/plans/kurashift_re問合せTier2以降_20260823.plan.md`  
**閾値 YAML**: `config/kurashift_re_inquiry_auto.yaml`

---

## 凡例

| 記号 | 意味 |
|---|---|
| ✅ | 実装済・本番 merge 済（commit `b442ca49` 等） |
| 🚧 | コードあり・未 merge / 未検証 / 一部のみ |
| ⬜ | プラン上あるが **未実装** |
| 📅 | カレンダーに将来予定を登録済 |

---

## フェーズ一覧

### Phase 1 — 業者開拓 & 物件候補 UI ✅

| 項目 | 状態 |
|---|---|
| vendors / deals タブ・ドロワー | ✅ commit `4bc055a5` |
| `kurashift_re_vendors` / `kurashift_re_deal_events` | ✅ |
| `re_vendor_sync` ジョブ | ✅ |

### Phase 2 — 日次サイクル ✅

| 項目 | 状態 |
|---|---|
| 朝バンドル（bucho / vendor / poll / digest） | ✅ commit `9c02bd33` |
| `jarvis_kurashift_re_daily_digest.py` | ✅（Tier2 行は ⬜ 下記） |
| 運営相談フォーム下書き（1906a1a5） | ✅ |
| DealDetailDrawer has_reply 導線 | ✅ |

### Phase 2.5 — 問合せ閾値 & Tier1 UI ✅

| 項目 | 状態 |
|---|---|
| `kurashift_re_inquiry_auto.yaml`（Tier0〜3 定義） | ✅ |
| `reInquiryCandidate.ts` + `jarvis_kurashift_re_inquiry_rules.py` | ✅ |
| `?inquiry=ready` フィルタ | ✅ |
| `DealInquiryQuickButton`（1件ずつ確認送信） | ✅ |
| 築古一棟AP / RC 取込整合 | ✅ |
| E2E checklist Tier 表 | ✅ |

**commit**: `b442ca49`（2026-08-23）

### Phase 2.6 — Tier2 日次一括キュー 🚧

**方針（ユーザー合意）**: Tier2 を早め ON。一括確認画面必須。日次上限 5 件。Tier3 は後回し。

| 項目 | 状態 | 備考 |
|---|---|---|
| YAML `tier2_daily_queue.enabled: true` | 🚧 | ローカル・未 commit |
| `reInquiryTier2Queue.ts` | ✅ | |
| GET `/api/re/inquiry-tier2-queue` | ✅ | |
| POST `/api/re/inquiry-tier2-send` | ✅ | `ui_confirmed` + snapshot |
| `/realestate/deals/tier2` 一括確認 UI | ✅ | build 済 |
| deals 一覧「送信待ち N件」リンク | ✅ | |
| digest に Tier2 送信待ち行 | ✅ | `jarvis_kurashift_re_daily_digest.py` |
| `npm run build`（trade-desk）検証 | ✅ | 2026-08-23 |
| 設計 doc / E2E / 運用コマンド追記 | ✅ | |
| **commit & deploy** | ⬜ | ユーザー確認後 |

### Tier1 初級者手順 ⬜

| 項目 | 状態 |
|---|---|
| `docs/KURASHIFT_Tier1_問合せ_初級者手順.md` | ✅ |
| Mac worker 常駐・5件の流れの図解 | ⬜ |

### Tier3 完全自動送信 ⬜

| 項目 | 状態 |
|---|---|
| YAML `tier3_auto_send.enabled` | ⬜ `false` 固定 |
| Mac worker 即送信（確認なし） | ⬜ 未実装 |
| **有効化トリガー** | 累計10件送信・返信3件・Tier2安定4週・明示同意 📅 |

### 物件調査シート / 返信分析 / Notion 🚧

| 項目 | 状態 |
|---|---|
| migration `20260823_kurashift_re_deal_research_fields.sql` | 🚧 ファイルのみ・未 apply |
| `config/kurashift_re_research_fields.yaml` | 🚧 |
| `jarvis_kurashift_re_reply_extract.py` | ⬜ 未作成 |
| Notion `DB_物件購入検討` スキーマ doc 化 | ⬜ |

### Phase 3（任意・後回し）⬜

設計 doc §Phase 3 のとおり。vendor↔deal 強化、Dashboard deep link、CSV export、週次バッチバー。

---

## Tier 運用の見方（今どこまで）

| Tier | いま | 次のゲート |
|---|---|---|
| **1** | ✅ 今すぐ主線。1件ずつ UI 確認送信 | 手動 **5件** 成功 + poll 安定 📅 8/25 目標 |
| **2** | 🚧 コード完了・未 deploy | merge 後 `/realestate/deals/tier2` 📅 9/6 レビュー |
| **3** | ⬜ OFF | Tier2 安定4週 + 10送/3返 📅 10/4 検討 |

---

## 関連 plan ファイル（Cursor）

| plan | 扱い |
|---|---|
| `re問合せ閾値設計_b0c440fc.plan.md` | Phase 2.5 まで ✅。Tier2 以降は **別 plan** へ |
| `kurashift_re問合せTier2以降_20260823.plan.md` | **生きている1本**（未実装 todo） |
| `kurashift残バックログ_20260813.plan.md` | 2026-08-13 以前の6件。**本件とは別**（履歴） |
| `物件調査_grok-first_*.plan.md` | Grok 本線 ✅。返信分析は上表 ⬜ |
| `grok_kurashift_連携_*.plan.md` | Phase1〜5 ✅ |

---

## カレンダー予定（admin・Jarvis 登録）

| 日付 | 予定 |
|---|---|
| 2026-08-25 | Tier1 手動問合せ 5件チェック | ✅ admin カレンダー登録済 |
| 2026-08-30 | Tier2 実装仕上げ（build・doc・merge） | ✅ 登録済 |
| 2026-09-01 | 物件調査シート / 返信分析 Phase 着手 | ✅ 登録済 |
| 2026-09-06 | Tier2 本番運用レビュー | ✅ 登録済 |
| 2026-09-13 | Tier2 2週レビュー → Tier3 可否判断（前倒し） | ✅ 登録済 |
| 2026-09-27 | Tier3 自動送信 有効化検討（前倒し・旧10/4） | ✅ 登録予定 |
| ~~2026-09-20~~ | ~~Tier2 4週安定~~ → 9/13 に前倒し | |
| ~~2026-10-04~~ | ~~Tier3~~ → 9/27 に前倒し | |

---

## 更新ルール

1. 実装が merge されたら ✅ に変更し、commit hash を1行足す  
2. Cursor plan の todo は **この doc と同じ ID** で同期  
3. 「全部完了」に見える旧 plan は触らず、**生きている plan は1本だけ**開く
