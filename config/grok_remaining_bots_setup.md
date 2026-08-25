# Grok 残り社員 — UI 作成チェックリスト（S6 / S7 / S8）

**更新**: 2026-08-25  
**方針**: Instructions 正本は repo 済み。このファイルは **Grok UI での作成手順**。単体を Instructions に貼らない。

チーム: 既存の **不動産Dailyチーム** にメンバー追加（専用チャンネルは作らない）。  
コネクタ: 既存不動産方針に合わせる。**estate Gmail を S6/S7/S8 に接続しない**（読取は参謀のみ）。

---

## 共通手順（各 Bot）

1. Grok で Bot を新規作成  
2. 名前・Description を下表どおり  
3. Instructions に正本 MD の **フェンス内全文**を貼る  
4. 不動産Dailyチームに追加  
5. 部長から `@名前` で1回テスト  

| チェック | S6 | S7 | S8 |
|---|---|---|---|
| Bot 作成 | ☐ | ☐ | ☐ |
| Instructions 貼付 | ☐ | ☐ | ☐ |
| チーム追加 | ☐ | ☐ | ☐ |
| 部長から @ テスト | ☐ | ☐ | ☐ |

部長 Instructions もロスター更新後に **再貼り**（☐）。

---

## S6 買付交渉

| 項目 | 値 |
|---|---|
| 名前 | `買付交渉` |
| 短名 | 買付 |
| Description | 内見〜買付〜価格交渉。推奨 go/hold/pass |
| Instructions 正本 | `config/grok_deal_negotiation_bot_grok_paste.md` |
| 件名（任意メール） | `[Grok買付]` |

**初回テスト文（部長 or 松野→部長経由）**:

```
@買付交渉 テスト: 架空物件でよい。内見チェック3項目と推奨 go|hold|pass を短く。
```

---

## S7 融資相談

| 項目 | 値 |
|---|---|
| 名前 | `融資相談` |
| 短名 | 融資 |
| Description | 融資打診準備・提出パックの抜け確認。承認保証はしない |
| Instructions 正本 | `config/grok_loan_bot_grok_paste.md` |
| 件名（任意メール） | `[Grok融資]` |

**初回テスト文**:

```
@融資相談 テスト: 架空の木造AP想定。提出物チェック5個と銀行への質問3つだけ。
```

---

## S8 物件ライフライン（今回追加）

| 項目 | 値 |
|---|---|
| 名前 | `物件ライフライン` |
| 短名 | ライフライン |
| Description | 賃貸物件の電気・水道・ネット・ガスの新規加入と見直し |
| Instructions 正本 | `config/grok_property_util_bot_grok_paste.md` |
| 件名（任意メール） | `[Grokライフライン]` |

**初回テスト文**:

```
@物件ライフライン テスト: 架空の名古屋市北区・購入直後想定。
電気・ガス・ネットの新規加入で必要な手続き観点を表で。実申込はしない。
```

---

## 振り分けの覚え方

| 言い方 | 社員 |
|---|---|
| 買付・内見・価格交渉 | S6 |
| 融資・打診・finance-pack | S7 |
| 電気／水道／ネット／ガス／開通／プロパン／ライフライン | S8 |
| 修繕・一人親方 | S4（開通相談ではない） |

---

## 関連

- 設計: `docs/KURASHIFT_Grok_不動産フェーズBot_設計_20260824.md`
- 索引: `config/grok_kurashift_inquiry_handoff_paste.md`
- 部長: `config/grok_sanbo_bot_grok_paste.md`
