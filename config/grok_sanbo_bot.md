# Grok「不動産賃貸・部長」Bot — 運用説明（正本）

更新: 2026-08-23

## 方式C — チャンネル「不動産Dailyチーム」（2026-08-23〜）

| Bot（Grok UI） | 役割 |
|---|---|
| **参謀** | 部長 · `本日分` 統括 · estate Gmail **読取** · `[Grok部長]` メール |
| **物件調査** | S1 · 自律探索・キュー調査・第一問合せ · `[Grok調査]`（**Gmail 非接続**） |
| **物件紹介業者開拓** | S2 · Web 問合せ · チャンネルへ `--mark`（**Gmail 非接続**） |

**松野の入口**: 参謀 DM **または** 不動産Dailyチーム — `本日分` / `メール確認` /（10:30）**S1物件探し**。  
**Jarvis**: estate の `[Grok部長]`（`--mark` + 探索）と `[Grok調査]`（deals＋inquiry 履歴＋証憑）。

Instructions: `grok_*_grok_paste.md` を各 Bot に再貼り付け。  
ルーティン: `grok_bucho_routine_本日分.md` · `grok_bucho_routine_S1物件探し.md`  
証憑: `docs/KURASHIFT_S1問合せ証憑_Drive_20260825.md`

## estate Gmail（参謀のみ）

| 拾う | 動作 |
|---|---|
| 件名 **`[調査依頼] …`** | `s1_pending` → `@物件調査` |
| 業者返信・物件PDF（住所が分かる） | 住所等を抽出 → `@物件調査`（路線価・HZ） |
| `[Grok部長]` / `[Grok調査]` | **拾わない**（自走ループ防止） |

松野の調査依頼メール例:

```
件名: [調査依頼] 岡崎市 岡町800万
本文: 住所: … / 価格: … / URL: …
```

KURASHIFT から当面: チーム or 参謀 DM へ **`調査追加:` + Grok調査用コピー**。

物件調査 Bot に estate Gmail は **繋がない**。

## 組織イメージ

```text
松野
 ├── Jarvis（Mac · 右腕・参謀） … 台帳 · deals · メール取込
 └── Grok
      └── 【部署】不動産賃貸（現時点1つのみ）
           ├── 部長 Bot（参謀）… Grok 窓口 · Gmail 読取
           └── 社員 Bot … 物件調査 / 業者開拓 / 周辺MAP 等
```

| 名前 | 場所 | 役割 |
|---|---|---|
| **Jarvis** | Cursor / Mac | 右腕 · 参謀 · 正本 |
| **部長** | Grok Bot | 不動産賃貸部署の統括 |
| **社員** | Grok Bot | 専門作業 |

松野は Grok では **部長（参謀）だけ** に指示（方式Cではチームに `本日分` も可）。

## 部長日報 → estate メール（正本 · 手動コピー不要）

部長が業務完了後、**matsuno.estate@gmail.com** へ `[Grok部長]` メールを送る。  
Jarvis が estate 受信から **`--mark` と探索 vendors YAML** を反映する。

| 種別 | 件名 |
|---|---|
| 日次 | `[Grok部長] 日報 YYYY-MM-DD` |
| 週次 | `[Grok部長] 週次 YYYY-MM-DD` |

本文に `📎 Jarvis 用（Mac同期）`（`--mark`）と `📎 Jarvis 用（探索追記）`（vendors YAML）を含める（Instructions テンプレ参照）。

### Jarvis 取込

```bash
cd ~/git-repos
~/selenium_env/venv/bin/python scripts/jarvis_grok_bucho_mail_apply.py --apply
# 物件調査結果:
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_property_mail_match.py --grok-only --apply
```

パートナー確認のついで・週1で実行可。プレビューは `--dry-run`。

処理済み message_id は `.jarvis_state/grok_bucho_mail_apply.json` に記録（二重反映防止）。

### 障害時

`--apply-marks grok_summary.txt`（手動ファイル）にフォールバック。

## Instructions 貼り付け

`config/grok_sanbo_bot_grok_paste.md` のコードブロック内。  
ルーティン指示の写し: `config/grok_bucho_routine_本日分.md`

## 毎週の流れ（業者開拓 · 方針B）

### 週の開始（月曜 or キュー枯渇時）

Jarvis: `--batch-week --grok-kickoff` → 出力を **部長** に1通（初回・補充時）。  
キューが尽きたら **部長 Bot から通知** → Jarvis に再生成依頼 → 同スレッドへ JSON 貼付。

### 毎日（月〜日）

部長スレッド **または 不動産Dailyチーム**: **`本日分`**  
→ Gmail確認 → S2 + S1 + 探索 → **`[Grok部長] 日報`**。  
調査待ち: `調査追加:` / `[調査依頼]` メール / キックオフ `s1_pending`。  
S2 のみ: `本日分 業者だけ` · 探索のみ: `探索` · Gmailのみ: `メール確認`。

### 土曜 or 日曜（週次締め · どちらか1日）

部長が **`[Grok部長] 週次 YYYY-MM-DD`** を estate へ（その週の `--mark` 全行一覧）。  
松野の習慣: **毎日 `本日分`**（または Grok ルーティン）· 週次メールは部長側の締め。

Jarvis: `jarvis_grok_bucho_mail_apply.py --apply`（日報＋週次取込 · パートナー確認ついで可）。

## 検証チェックリスト（Grok 再貼り付け後）

1. **参謀** Instructions を `grok_sanbo_bot_grok_paste.md` コードブロックで全置換
2. **物件調査** Instructions を `grok_property_bot_grok_paste.md` コードブロックで全置換
3. ルーティン指示を `grok_bucho_routine_本日分.md` の「指示」で更新
4. 物件調査 Bot に **estate Gmail が未接続**であることを確認
5. チームで `メール確認` → 参謀が拾い報告（0件でも可）
6. （任意）estate へ件名 `[調査依頼] テスト …` を1通 → 参謀が `@物件調査` → `[Grok調査]` 着信
7. Jarvis: `jarvis_kurashift_property_mail_match.py --grok-only --apply`

## 関連

| ファイル | 内容 |
|---|---|
| `config/grok_sanbo_bot_grok_paste.md` | 参謀 Instructions |
| `config/grok_bucho_routine_本日分.md` | Grok ルーティン指示（コピペ） |
| `scripts/jarvis_grok_bucho_mail_apply.py` | 部長日報取込 |
| `scripts/jarvis_kurashift_vendor_list.py` | `--apply-marks` 手動 |
| `docs/KURASHIFT_GrokBot_不動産パイプライン.md` | パイプライン |

