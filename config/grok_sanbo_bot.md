# Grok「参謀」Bot — 運用説明（正本）

更新: 2026-08-22

## 位置づけ

| 名前 | 場所 | 役割 |
|---|---|---|
| **Jarvis** | Cursor / Mac | 右腕 · 台帳 · deals · `--apply-marks` · 正本 |
| **参謀** | Grok Bot（役割=参謀） | Grok 社員の統括 · 松野の **Grok 窓口1本** |
| **物件調査** | Grok 社員 | `[Grok調査]` |
| **物件業者開拓** | Grok 社員 | Web 問合せ初回 |
| **周辺MAP** | 参謀内 §周辺MAP（将来独立 Bot 可） | 購入後 MAP |

松野は **Grok には参謀だけ** に話す。参謀が社員役を実行（またはグループで指示）。  
結果の Mac 反映は **Jarvis と相談**。

## Instructions 貼り付け

`config/grok_sanbo_bot_grok_paste.md` のコードブロック内を Grok Bot Instructions に貼る。

Grok UI で **役割「参謀」** を選べる場合はそれを使用（Chief of Staff 相当）。

## 毎週の流れ（業者開拓 · 既存 Bot2 運用を参謀経由に）

### 月（週1）

```bash
cd ~/git-repos
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_vendor_list.py --batch-week --grok-kickoff
```

出力（キックオフ + JSON）→ **参謀** に1通（物件業者開拓 Bot への直接貼付は不要）。

### 火〜金

参謀スレッドで:

```
本日分
```

### 金 or 日（Mac · Jarvis）

参謀の週次サマリー **`📎 Jarvis 用`** ブロックを保存 →

```bash
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_vendor_list.py \
  --apply-marks grok_week_summary.txt
```

## 物件調査

deals「Grok調査用コピー」または物件概要を **参謀** に渡す:

```
この物件を調査して（物件調査モード）
```

参謀が §物件調査モードで `[Grok調査]` 送信。取込は Jarvis:

```bash
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_property_mail_match.py --grok-only --apply
```

## 周辺MAP（段階導入）

購入後:

```
【物件名】の周辺MAP。住所: ... ターゲット: ...
```

参謀が Step1.2 相当 + Canva チェックリストを返す。PNG 保存・フォルダ整理は Jarvis。

## 独立社員 Bot との関係

- **v0**: 参謀1体が社員役を **内包実行**（方式A）。既存 Bot1/Bot2 Instructions は正本として残す。
- **v1（任意）**: グループ「不動産チーム」+ 独立 Bot。松野は参謀 DM のみ。

独立 Bot を残す理由: 長期スレッド・専用 VM · 参謀がグループ経由で再利用。

## 禁止（再掲）

- 松野に「Bot2 に貼って」と丸投げ
- Jarvis 領域（YAML / deals）を Grok 参謀が直接更新
- approved 改変 · リスト外送信

## 関連

| ファイル | 内容 |
|---|---|
| `config/grok_sanbo_bot_grok_paste.md` | Instructions 貼り付け |
| `config/grok_property_bot_grok_paste.md` | 社員: 物件調査 |
| `config/grok_vendor_outreach_bot_grok_paste.md` | 社員: 業者開拓 |
| `docs/KURASHIFT_GrokBot_不動産パイプライン.md` | 全体パイプライン |
