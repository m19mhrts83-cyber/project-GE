# KURASHIFT · S1 問合せ証憑（Drive 集約）— 2026-08-25

## 方針

| 層 | 置き場所 | 備考 |
|---|---|---|
| **バイナリ**（画像・PDF） | **Google Drive / OneDrive フォルダ** | Supabase Storage には載せない（容量） |
| **メタ** | `kurashift_re_deal_attachments` | `storage_path` + `payload.drive_web_view_link` 等 |
| **文字・状態** | `kurashift_re_deals` / events / messages | `inquiry_status` 等 |

Grok チャンネル画像は **人が見やすい副線**。正本は **estate メール添付 → Jarvis が証憑フォルダへ保存 → KURASHIFT からリンク**。

## フォルダ規約

既定ルート（優先順）:

1. 環境変数 `KURASHIFT_INQUIRY_EVIDENCE_ROOT`
2. OneDrive `…/230_物件調査/KURASHIFT_問合せ証憑/`
3. admin Drive デスクトップ `…/マイドライブ/230_物件調査/KURASHIFT_問合せ証憑/`（無い場合は 2）

配下:

```
KURASHIFT_問合せ証憑/
  {deal_id}/
    01_portal.png
    02_send_confirm.png
    maisoku.pdf
```

## S1 の送り方

1. チャンネルにキャプチャ（松野向け）
2. **`[Grok調査]`** または **`[Grok調査証憑] {市区} {短名}`** に画像・PDFを添付して estate へ

## Jarvis 取込

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
# deals 取込（inquiry_action 反映）
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_property_mail_match.py --grok-only --apply
# 証憑をフォルダへ＋メタ
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_s1_evidence_to_drive.py --deal-id <uuid>
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_s1_evidence_to_drive.py --poll-recent
```

- ローカルミラー: `.jarvis_state/kurashift_re_deal_attachments/{deal_id}/` にもコピー可（既存 PDF-0 互換）
- `payload.open_url`: 優先 **Drive webViewLink**（D3）。無いとき file://（ローカル同期フォルダ）
- API アップロード: `scripts/jarvis_kurashift_evidence_gdrive.py`（取込時に `s1_evidence_to_drive.py` から自動呼び出し）
- 無効化: `KURASHIFT_EVIDENCE_DRIVE_API_DISABLE=1`
- 検証: `jarvis_kurashift_evidence_gdrive.py --verify` または `s1_evidence_to_drive.py --verify-drive-api`

## KURASHIFT UI

deal 詳細に「証憑」リンク一覧（`open_url` / Drive）。件数は timeline の `attach_count`。

## 段階

| 段階 | 内容 | 状態 |
|---|---|---|
| D0 | 本ドキュメント・フォルダ規約・S1 添付指示 | 本ファイル |
| D1 | `jarvis_kurashift_s1_evidence_to_drive.py` | 同日実装 |
| D2 | trade-desk 証憑リンク表示 | 同日実装 |
| D3 | Drive API アップロード（admin · `token_drive_admin_write.json`） | **2026-08-28** 実装済み |

## 関連

- S1 paste: `config/grok_property_bot_grok_paste.md`
- 取込: `scripts/jarvis_kurashift_property_mail_match.py`（`inquiry_action`）
- 既存 PDF-0: `scripts/jarvis_kurashift_re_deal_pdf_fetch.py`
