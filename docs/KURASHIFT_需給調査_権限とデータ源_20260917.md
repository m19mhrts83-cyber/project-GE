# 需給三次（S3）— 権限とデータ源（2026-09-17）

松野確定: スマサテ／SUUMO賃貸経営サポートは **セキュリティリスク許容**。  
S3 がログインして調査し、**自律判断**する。

## 権限

| 主体 | スマサテ / SUUMO賃貸経営サポート | 生活保護住宅扶助（公開） | 銀行・カード・財務 |
|---|---|---|---|
| **S3 需給** | ログイン可・調査・go/hold/passまで | 市区町村公表を調査 | 触らない |
| **S5 / S13 / 部長** | ログインしない（S3結果を使う） | S3結果を参照 | — |
| **Jarvis** | 資格情報の控え・再発行時フォールバック | — | 秘密管理本線 |

## 資格情報の置き方

1. `.env.jarvis_private` に控え（`SUMASATE_*` / `SUUMO_ONR_*`）
2. **S3 が使う正**: 需給三次判断 Bot の Instructions／S3専用メモへ **当該2サイト分だけ** 転記
3. チャンネル・outbox・一般Drive・git に ID/PW を書かない

## データ源

| 源 | URL／根拠 | レポートに入れること |
|---|---|---|
| 公開ポータル | SUUMO / at HOME / LIFULL HOME'S | 供給表（既存） |
| IPSS | 将来推計人口 | 需要統計（既存） |
| スマサテ | https://owners.sumasate.jp/home | エリア平均 vs 自物件の位置づけ |
| SUUMO賃貸経営サポート | https://www.suumo-onr.jp/ | 同価格帯競合数・上下分布 |
| 生活保護・住宅扶助 | 物件住所の市区町村公表 | 想定家賃 vs 保護基準・収入ライン検討材料 |

## 生活保護家賃

- 都道府県だけでは足りない。**市区町村**まで特定
- 調査日・出典URL必須。捏造禁止。不明は「要自治体確認」
- S5 は収入レンジ検討時に S3 の保護基準行を参照

## paste 正本

- S3: `config/grok_supply_bot_grok_paste.md`
- S5: `config/grok_persona_bot_grok_paste.md`
- 部長: `config/grok_realestate_bucho_grok_paste.md` §需給三次
- スキーマ: `config/kurashift_re_supply_schema.yaml`
