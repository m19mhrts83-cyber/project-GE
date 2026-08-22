# Grok「不動産賃貸・部長」Bot — 運用説明（正本）

更新: 2026-08-22

## 組織イメージ

```text
松野
 ├── Jarvis（Mac · 右腕・参謀） … 台帳 · deals · メール取込
 └── Grok
      └── 【部署】不動産賃貸（現時点1つのみ）
           ├── 部長 Bot … 松野の Grok 窓口
           └── 社員 Bot … 物件調査 / 業者開拓 / 周辺MAP 等
```

| 名前 | 場所 | 役割 |
|---|---|---|
| **Jarvis** | Cursor / Mac | 右腕 · 参謀 · 正本 |
| **部長** | Grok Bot | 不動産賃貸部署の統括 |
| **社員** | Grok Bot | 専門作業 |

松野は Grok では **部長だけ** に指示。

## 部長日報 → estate メール（正本 · 手動コピー不要）

部長が業務完了後、**matsuno.estate@gmail.com** へ `[Grok部長]` メールを送る。  
Jarvis が estate 受信から `--mark` を YAML に反映する。

| 種別 | 件名 |
|---|---|
| 日次 | `[Grok部長] 日報 YYYY-MM-DD` |
| 週次 | `[Grok部長] 週次 YYYY-MM-DD` |

本文に `📎 Jarvis 用` ブロックと `--mark` 行を含める（Instructions テンプレ参照）。

### Jarvis 取込

```bash
cd ~/git-repos
~/selenium_env/venv/bin/python scripts/jarvis_grok_bucho_mail_apply.py --apply
```

パートナー確認のついで・週1で実行可。プレビューは `--dry-run`。

処理済み message_id は `.jarvis_state/grok_bucho_mail_apply.json` に記録（二重反映防止）。

### 障害時

`--apply-marks grok_summary.txt`（手動ファイル）にフォールバック。

## Instructions 貼り付け

`config/grok_sanbo_bot_grok_paste.md` のコードブロック内。

## 毎週の流れ（業者開拓）

### 月

`--batch-week --grok-kickoff` → **部長** に1通。

### 火〜金

部長スレッド: **`本日分`** → **S2 業者開拓（3社/日）+ S1 物件調査（調査待ち先頭1件/日）** → 完了後 **部長日報メール**（日次）。  
調査待ちは `調査追加:` で積む · キックオフ JSON の `s1_pending`（任意）でも可。  
S2 のみ: `本日分 業者だけ`。

### 週末

Jarvis: `jarvis_grok_bucho_mail_apply.py --apply`（週次メール取込）。

## 関連

| ファイル | 内容 |
|---|---|
| `config/grok_sanbo_bot_grok_paste.md` | Instructions |
| `scripts/jarvis_grok_bucho_mail_apply.py` | メール取込 |
| `scripts/jarvis_kurashift_vendor_list.py` | `--apply-marks` 手動 |
| `docs/KURASHIFT_GrokBot_不動産パイプライン.md` | パイプライン |
