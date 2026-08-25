# KURASHIFT 問合せパイプライン — 進捗正本（2026-08-23）

**用途**: Cursor plan がすべて「完了」に見えても、ここが **実装済 / 未実装** の正本。  
**設計**: [`KURASHIFT_RE_業者開拓_物件候補_実務者設計_20260823.md`](KURASHIFT_RE_業者開拓_物件候補_実務者設計_20260823.md)  
**生きている plan**: `~/.cursor/plans/kurashift_re問合せTier2以降_20260823.plan.md`  
**閾値 YAML**: `config/kurashift_re_inquiry_auto.yaml`  
**自動サイクル仕様**: 2026-08-25（下準備・既存 Tier 延長）

---

## 目標サイクル（自動問合せ → 内見／購入手前）

```
Grok調査 → score/聞く → Tier1手動 | Tier2一括確認 | Tier3自動(OFF)
  → 送信 → poll → reply_extract → [Grok内見判断] → 購入手前ストック → 内見最終判断
```

| Phase | 内容 | 状態 |
|---|---|---|
| **A 運用** | Tier1 手動ボタンは残す。日次の主線は **Tier2 一括確認**（digest → `/realestate/deals/tier2`） | 🚧 コード済・運用ゲート待ち |
| **B データ** | 返信抽出 → Grok 再調査 → Notion/deals ストック | 🚧 着手（migration / extract） |
| **C 自動** | Tier3 無確認送信（明示同意後のみ YAML `enabled`） | ⬜ OFF・worker 用意 |

しきい値は `kurashift_re_inquiry_auto.yaml` 正本（Tier2: score≥5＋聞く／Tier3: score≥7＋聞く＋HZ=OK）。送信量を増やすときは **score より日次 cap を上げる**。

---

## 凡例

| 記号 | 意味 |
|---|---|
| ✅ | 実装済・本番 merge 済 |
| 🚧 | コードあり・未 apply / 一部のみ |
| ⬜ | 未実装・運用待ち |
| 📅 | カレンダー登録済 |

---

## フェーズ一覧

### Phase 1 — 業者開拓 & 物件候補 UI ✅

| 項目 | 状態 |
|---|---|
| vendors / deals タブ・ドロワー | ✅ `4bc055a5` |
| `kurashift_re_vendors` / `kurashift_re_deal_events` | ✅ |
| `re_vendor_sync` ジョブ | ✅ |

### Phase 2 — 日次サイクル ✅

| 項目 | 状態 |
|---|---|
| 朝バンドル（bucho / vendor / poll / digest） | ✅ `9c02bd33` |
| `jarvis_kurashift_re_daily_digest.py`（Tier2 行含む） | ✅ |
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
| Tier1 初級者手順 | ✅ `docs/KURASHIFT_Tier1_問合せ_初級者手順.md` |
| E2E checklist Tier 表 | ✅ |
| **経路仕分け**（agent_email / grok_handoff / not_applicable） | ✅ `reInquiryChannel` + `awaiting_grok` |
| Grok 依頼メール件名 `[KURASHIFT問合せ依頼]` | ✅ paste: `config/grok_kurashift_inquiry_handoff_paste.md` |

**commit**: `b442ca49`（閾値）＋経路仕分けは後続 commit

### Phase 2.6 — Tier2 日次一括キュー ✅

**方針**: 早め ON・一括確認必須・日次上限5件・**本番候補のみ**（E2E fixture 除外）。

| 項目 | 状態 | 備考 |
|---|---|---|
| YAML `tier2_daily_queue.enabled: true` | ✅ | |
| `reInquiryTier2Queue.ts` + 本番フィルタ | ✅ | `E2E-GROK-KURASHIFT` 除外 |
| GET/POST `inquiry-tier2-*` | ✅ | `ui_confirmed` + snapshot |
| `/realestate/deals/tier2` | ✅ | |
| deals「送信待ち Tier2」リンク | ✅ | |
| digest Tier2 行 | ✅ | |
| **commit & deploy** | ✅ | `3ddcaed2` → main |

### Tier3 完全自動送信 ⬜

| 項目 | 状態 |
|---|---|
| YAML `tier3_auto_send.enabled` | ⬜ `false`（明示同意後のみ） |
| Mac worker | 🚧 `scripts/jarvis_kurashift_re_tier3_auto_send.py`（enabled 時のみ実送信） |
| 有効化手順 | `docs/KURASHIFT_Tier3_自動送信_有効化手順.md` |
| 有効化トリガー | 10送/3返・Tier2安定・明示同意 📅 9/13・9/27（前倒し可） |

### 物件調査シート / 返信分析 🚧

| 項目 | 状態 |
|---|---|
| migration `20260823_kurashift_re_deal_research_fields.sql` | ✅ apply（`kurashift_re_deal_field_values`） |
| `config/kurashift_re_research_fields.yaml` | ✅ |
| `jarvis_kurashift_re_reply_extract.py` | ✅ |
| `[Grok内見判断]` handoff | ✅ paste 索引に追記 |
| Notion `DB_物件購入検討` 投影 | ⬜ 抽出後の手動／後続 sync |

### Phase 3（任意）⬜

vendor↔deal 強化、Dashboard deep link、CSV export、週次バッチバー。

---

## Tier 運用の見方

| Tier | いま | 次のゲート |
|---|---|---|
| **1** | ✅ **手動導線**（1件ずつ・残す） | お試し数件 + poll 📅 8/25 |
| **2** | ✅ **日次主線**（一括確認・deploy 済） | 運用レビュー 📅 9/6 |
| **3** | ⬜ OFF | 可否 📅 9/13 → 有効化検討 📅 9/27 |

**日常の押し方**: 朝 digest の Tier2 行 → https://jarvis-trade-desk.vercel.app/realestate/deals/tier2 で一括確認。個別は Tier1 ボタン。

---

## 生きている plan の todo（同期）

| ID | 状態 |
|---|---|
| `tier2-finish-code` | ✅ |
| `tier1-beginner-doc` | ✅ |
| `tier1-five-sends` | ⬜ 運用 |
| `tier2-prod-review` | ⬜ 運用 |
| `research-reply-extract` | 🚧 コード・migration 済／本番抽出運用 |
| `tier3-gate` | ⬜ 同意後 |
| `tier3-worker` | 🚧 スクリプト用意・enabled 待ち |
| `viewing-judgment-handoff` | ✅ paste／進捗 |
| `phase3-optional` | ⬜ |

---

## 関連 plan（Cursor）

| plan | 扱い |
|---|---|
| `kurashift_re問合せTier2以降_20260823.plan.md` | **生きている1本** |
| `re問合せ閾値設計_b0c440fc.plan.md` | Phase 2.5 まで ✅ |
| `kurashift残バックログ_20260813.plan.md` | 履歴（本件と別） |
| `物件調査_grok-first_*.plan.md` | Grok 本線 ✅ |
| `grok_kurashift_連携_*.plan.md` | Phase1〜5 ✅ |

---

## カレンダー予定（admin）

| 日付 | 予定 | |
|---|---|---|
| 2026-08-25 | Tier1 手動問合せ 5件チェック | ✅ |
| 2026-08-30 | Tier2 実装仕上げ確認 | ✅（実装は済） |
| 2026-09-01 | 物件調査シート / 返信分析 着手 | ✅ |
| 2026-09-06 | Tier2 本番運用レビュー | ✅ |
| 2026-09-13 | Tier2 → Tier3 可否判断（前倒し） | ✅ |
| 2026-09-27 | Tier3 有効化検討（前倒し） | ✅ |
| ~~2026-09-20~~ / ~~2026-10-04~~ | → 9/13・9/27 に前倒し（旧予定は削除可） | |

---

## フォローアップ（終わるまで）

ルール: `.cursor/rules/jarvis-kurashift-inquiry-followup.mdc`  
state: `.jarvis_state/kurashift_re_inquiry_followup.json`

目安日の前後・経過後に Jarvis が「こうしてください」を1ブロック促す。残 todo 完了 or 不要明示で disabled → ルール削除。

## 更新ルール

1. merge したら ✅ と commit hash を更新する  
2. Cursor plan の todo と **この doc の todo 表**を同じ ID で同期する  
3. 生きている plan は **1本だけ**開く
