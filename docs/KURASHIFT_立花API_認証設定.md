# KURASHIFT 立花証券e支店API 認証設定（公開鍵認証）

株式ウォッチ Phase2 の前提。**本番発注はまだ行わない**。ここでは認証情報（認証ID・秘密鍵）を
取得して安全に配置し、接続確認までを行う。実発注コードは別タスク。

対象商品は**日本株（現物・信用）のみ**（立花e支店は海外株式非対応）。

## 現状（2026-09-25）

| 項目 | 状態 |
|---|---|
| 口座 | 開設済み（`.env` の `TACHIBANA_ACCOUNT_OPEN_STATUS` は `applied` のまま要更新） |
| API 認証ID・秘密鍵 | **未取得**（`TACHIBANA_API_AUTH_ID_PATH` / `TACHIBANA_API_PRIVATE_KEY_PATH` 未設定） |
| readiness | NOT READY（`scripts/jarvis_kurashift_tachibana_auth_check.py`） |

## 公式仕様（確認済み・2026-09-25）

- 最新版 **v4r10**（2026-08-29 リリース）。**v4r9 は 2026-09-27（日）廃止** → v4r10 を使う。
  - 本番 `https://kabuka.e-shiten.jp/e_api_v4r10/`
  - デモ `https://demo-kabuka.e-shiten.jp/e_api_v4r10/`
- 認証は**公開鍵暗号方式**。リクエストは「URL に JSON を付加」する独自方式、応答は **Shift-JIS**。
- **本番環境とデモ環境は別セット**（認証ID・秘密鍵・公開鍵がそれぞれ別）。
- ログインで得た**仮想URL（1日券）**をその日の API 呼び出しに使う。`p_no` は呼び出しごとに +1。
- 標準Web はパスキー認証。2026-12-12 以降、取引・出金にもパスキー設定が必須。
- 参考: 仕様書 <https://www.e-shiten.jp/e_api/mfds_json_api_menu.html> /
  サンプル <https://github.com/e-shiten-jp> /
  デモ案内 <https://www.e-shiten.jp/Service/demo.html>

## 手順 A: 立花側で鍵を取得する（本人作業・ブラウザ）

パスキー（または電話番号）認証で標準Webにログインし、【お客様情報】で API 利用設定を行う。
**デモで試すなら、デモの標準Webから別セットを取得する**（本番の鍵は本番Webでのみ発行）。

1. 標準Web にログイン
   - 本番: <https://tr2.e-shiten.jp/e-shiten>
   - デモ: <https://demo.e-shiten.jp>（ユーザID=口座番号、第一暗証番号=ログインPW。電話認証は不要）
2. 【お客様情報】→「e支店・API利用設定」を**「利用する」に変更**（初期値は「利用しない」）
3. 画面の指示に従い**秘密鍵・公開鍵を作成（生成）**し、**公開鍵を登録**
4. **認証ID（`e_api_authid.txt`）** と **秘密鍵（`e_api_private_key.pem`）** をダウンロード
5. デモを使う場合も同じ手順を**デモ環境で**行い、デモ専用の2ファイルを取得

公式の詳細手順: GitHub `e-shiten-jp/e_api_login_pubkey.py` の
「認証ID・秘密鍵等の取得方法.pdf」「セットアップマニュアル.html」。

## 手順 B: 取得物の配置（Mac）

ディレクトリを分けて保管（**Git・バックアップの平文対象にしない**）。

```bash
mkdir -p ~/.tachibana/demo ~/.tachibana/prod
chmod 700 ~/.tachibana ~/.tachibana/demo ~/.tachibana/prod
# 取得したファイルを配置（例: デモ）
#   ~/.tachibana/demo/e_api_authid.txt
#   ~/.tachibana/demo/e_api_private_key.pem
chmod 600 ~/.tachibana/demo/e_api_authid.txt ~/.tachibana/demo/e_api_private_key.pem
```

## 手順 C: .env を整備（secrets ツール経由）

値は `scripts/jarvis_kurashift_secrets.py` で追記する（`.env` を直接 cat しない）。

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
PY=~/selenium_env/venv/bin/python
$PY scripts/jarvis_kurashift_secrets.py --upsert-json '{
  "TACHIBANA_API_DEMO": "1",
  "TACHIBANA_API_VERSION": "4r10",
  "TACHIBANA_API_DEMO_BASE": "https://demo-kabuka.e-shiten.jp/e_api_v4r10/",
  "TACHIBANA_API_BASE": "https://kabuka.e-shiten.jp/e_api_v4r10/",
  "TACHIBANA_API_AUTH_ID_PATH": "'$HOME'/.tachibana/demo/e_api_authid.txt",
  "TACHIBANA_API_PRIVATE_KEY_PATH": "'$HOME'/.tachibana/demo/e_api_private_key.pem",
  "TACHIBANA_ACCOUNT_OPEN_STATUS": "opened"
}'
```

本番に切り替えるときは `TACHIBANA_API_DEMO=0` と `..._PATH` を `prod/` 側へ。

## 手順 D: 検証

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
PY=~/selenium_env/venv/bin/python

# 存在・権限・RSA形式の確認（秘密値は表示しない）
$PY scripts/jarvis_kurashift_tachibana_auth_check.py

# ログインのみ（デモ推奨）。成功で「仮想URL取得」
$PY scripts/jarvis_kurashift_tachibana_auth_check.py --probe
```

`READY` かつ `probe: ログイン成功・仮想URL取得` なら認証設定は完了。

## 安全メモ

- 発注・出金・OTP の最終送信は**本人**。Jarvis は代行しない（`config/kurashift_stock_watch.yaml` の `order.otp_note`）。
- 接続元の**固定IP制限**を強く推奨（鍵・応答ファイル流出時の不正ログイン対策）。
- `p_no` は `.jarvis_state/tachibana_p_no.json` に永続化。仮想URLは当日限り。
- 発注機能は `docs/Trade_Desk.md` の対外確認ゲート（プレビュー→オーナー確認）を必ず通す。

## 次のタスク

1. 認証設定（本ドキュメント。鍵取得→READY まで）
2. 立花APIクライアント（ログイン/残高/現物可能額/発注プレビュー）を**デモ**で実装
3. 発注プレビュー（`scripts/jarvis_kurashift_stock_order.py`）を API 連携へ差し替え（無確認自動発注は禁止のまま）
