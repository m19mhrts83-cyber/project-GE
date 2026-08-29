# Grok 物件調査 Bot — レポート形式（正本）

松野エステイト Gmail 宛 `[Grok調査]` メール。Jarvis `property_mail_match` が `mail_grok` として取込。

**優先エリア・ふるい**: `config/grok_property_search_criteria.yaml`（愛知最優先 → 岐阜・三重。戸建500〜3500万・HZ原則除外）

## 送信方針

- **宛先**: `matsuno.estate@gmail.com`（松野エステイト宛は承認不要・送信してよい）
- **件名**: `[Grok調査] {市区町村} {物件短名}`
- **From**: m19m 等（estate ログインは Grok VM に載せない）
- **Grok Instructions 貼り付け**: `config/grok_property_bot_grok_paste.md`

## 調査手順（Bot 説明文に載せる）

### 0. 耐震区分（最初に · 必須）

| 区分 | 目安 |
|---|---|
| 新耐震 | 建築確認 **1981-06-01** 以降 |
| 旧耐震 | それより前 |

旧耐震戸建は保険コスト増の目安（年約10万円級・要見積）。買付減額交渉は S6。

### 1. 相続税路線価（土地値）

1. [全国地価マップ（chikamap）](https://www.chikamap.jp/chikamap/Map) を開く
2. 物件の **所在（番地まで）** を検索
3. **相続税路線価** リンクを開き、路線価（万円/㎡ 等）を読む
4. 倍率地域の場合は [国税庁 路線価図](https://www.rosenka.nta.go.jp/) で倍率を確認
5. 土地積算（路線価×面積×倍率等）と **購入価格に対する土地値%** を計算
6. **土地値100%判定**: 聞く（100%超え）| 保留 | 見送り
7. **方式** は `路線価` または `倍率` を必ず記載（倍率 → KURASHIFT 第一問合せで固定資産税資料を依頼）

### 2. ハザード（重ねるハザードマップ）

1. [重ねるハザードマップ](https://disaportal.gsi.go.jp/maps/) を開く
2. 上部 **住所を入力** に物件住所（番地まで）を入れ、**検索**
3. 地図中心（十字線）の地点について、レイヤを確認:
   - **洪水**（想定最大規模等）
   - **土砂災害**（土石流・地滑り等）
   - **高潮**（津波を除く）
   - **内水**（雨水出水）
4. 該当なし → `なし`、色付き・浸水想定 → `該当`、判別不能 → `要確認`
5. **評価**: OK（主要リスクなし）| 注意（軽微・要確認）| 除外（ハザード原則除外。高利回り例外は理由1行に明記）

※ KURASHIFT 買い進め条件: **ハザード原則除外（高利回りは例外可）**

## 本文テンプレート

```
件名: [Grok調査] {市区町村} {物件短名}
本文:
---
source: grok_bot
bot: 物件調査
report_id: {YYYYMMDD-HHMM}
---

## 物件
- 所在:
- 価格_万:
- 土地面積:
- 建物:
- 駐車場: あり|なし|不明
- URL:

## 耐震
- 区分: 新耐震|旧耐震|不明
- 建築年月（または確認申請日）:
- 判定根拠: 築年のみ|確認日|資料|不明
- 保険コスト注意: なし|あり（旧耐震戸建は年約10万円級増の目安・要見積）
- S6引き渡し: （旧耐震なら「保有10年想定で約100万円減額交渉を検討」1行）

## 土地評価
- 方式: 路線価|倍率
- 路線価_万円_坪:
- 倍率:
- 土地積算_万円:
- 土地値100%_比率:
- 土地値100%判定: 聞く|保留|見送り
- 根拠URL:

## ハザード（重ねるハザードマップ）
- 調査URL: https://disaportal.gsi.go.jp/maps/
- 洪水: なし|該当|要確認
- 土砂: なし|該当|要確認
- 高潮: なし|該当|要確認
- 内水: なし|該当|要確認
- 評価: OK|注意|除外
- 根拠URL:

## 人口（チャプロ軸）
- 評価: 安全|選別|攻め
- 表: （Markdown 1行）

## 総合
- 聞く価値: 聞く|保留|見送り
- 理由1行:

## 問合せ
- inquiry_action: portal_sent|kurashift_handoff|investigate_only
- agent_email_available: yes|no|unknown
- inquiry_url:
- portal: rakumachi|kenbiya|homes|nagoya_rengo|athome|other|none
- sent_at: {YYYY-MM-DD HH:MM JST または blank}
- note: （送信結果1行）
```

## Jarvis 中継（Cursor から送る場合）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_grok_report_mail.py --file report.md --send
```

## 取込

```bash
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_property_mail_match.py --grok-only --dry-run
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_property_mail_match.py --grok-only --apply
```

`inquiry_action: portal_sent` → deals に `inquiry_status=awaiting_reply` と event `inquiry_sent`（actor=s1_portal）。  
`kurashift_handoff` → `awaiting_grok` 相当のヒント（既存 Tier／第一問合せレーン）。  
証憑画像・PDF → Drive（`docs/KURASHIFT_S1問合せ証憑_Drive_20260825.md`）· メタは `kurashift_re_deal_attachments`。

**定常化**: `jarvis_morning_mac_refresh.py` が `--grok-only --apply` を朝バンドルに含む（`kurashift_grok_mail` ステップ）。
## KURASHIFT で使われる評価

| 項目 | スコア影響 |
|---|---|
| 聞く価値 聞く/保留/見送り | 大 |
| 土地値100%判定 | 中 |
| ハザード評価 除外/注意/OK | 除外は大幅減点 |
| 耐震（新/旧） | 旧耐震は保険コスト注意（即除外ではない · S6減額交渉） |
| 駐車場あり | 小 |
