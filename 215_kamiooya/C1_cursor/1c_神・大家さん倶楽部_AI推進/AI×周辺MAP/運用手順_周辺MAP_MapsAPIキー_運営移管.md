# 運用手順：周辺MAP Maps APIキー（運営移管・セキュリティ）

- **対象**: GitHub Pages の `shuhen-map`（番号ピン地図）
- **公開URL**: https://m19mhrts83-cyber.github.io/project-GE/shuhen-map.html
- **方針**: 会員にキー入力させない（運営負担）。Maps JS はブラウザ公開前提のため、**制限付きブラウザキー**で運用する
- **戻し方**: Git タグ `shuhen-map-before-ops-key`（キー入力 UI ありの時点）

関連: `12_Raimoミニアプリ_周辺MAP番号ピン.md` / `DEPLOY_GUIDE.md` / Q&A Phase 5（[`フェーズ管理.md`](../神・大家さん倶楽部情報Q&Aチャットボット/フェーズ管理.md)）

---

## 重要な前提（引き継ぎ時に必ず伝える）

| 誤解しやすい点 | 正しい理解 |
|---|---|
| 入力欄を消せばキーは隠れる | **隠れていない**。ページが `maps.googleapis.com?...&key=` を呼ぶため、DevTools で見える |
| だから危険で使えない | **リファラ制限＋API制限＋予算アラート＋クォータ**をかけたブラウザキーは Google 推奨の標準運用 |
| Q&A の Gemini と同じ秘匿 | できない。Gemini はサーバ、Maps JS はクライアント |

---

## 必須ヘッジ（公開前・運営移管時も再確認）

Google Cloud Console（Maps を課金しているプロジェクト）で実施。

### 1. ブラウザ用キーを分離（推奨）

- サーバ用キーと **別キー** を「周辺MAP / project-GE ブラウザ」用に作成
- 既存キーを流用する場合も、下記制限を必ず付ける

### 2. アプリケーションの制限（HTTP リファラ）

認証情報 → API キー → アプリケーションの制限 → **HTTP リファラー**:

```
https://m19mhrts83-cyber.github.io/project-GE/*
https://*.raimo-app.buzz/*
https://ma-8cfk63x74bh5.raimo-app.buzz/*
```

※ Raimo ミニアプリ経由で開く場合、Pages 直開きだけ許可だと **ピン表示がスピナーのまま止まる／地図が真っ白**になりやすい。Raimo のリファラも必ず追加する。

ローカル検証用に別キーを切る場合の例（本番キーには付けない方が安全）:

```
http://localhost:*/*
http://127.0.0.1:*/*
```

### 3. API の制限

このキーで使える API のみ:

- Maps JavaScript API
- Places API
- Geocoding API
- Directions API（徒歩動線トグル用）
- （Static キャプチャを使うなら）Maps Static API

不要な API（高額になりやすいもの含む）は付けない。

### 4. Directions API の有効化

動線トグルを使う場合、対象プロジェクトで **Directions API** を有効化する。

### 5. 予算アラート（Billing budgets）— デモ期の推奨値

請求 → [予算とアラート](https://console.cloud.google.com/billing/budgets?hl=ja) → **予算を作成**:

| 項目 | デモ期の推奨／実績 |
|---|---|
| 名前 | `project-GE-shuhen-map-demo` |
| 期間 | 毎月 |
| 対象 | 請求先アカウント全体、または Maps 利用プロジェクト |
| **予算額** | **¥3,000／月**（2026-07-25 作成済み。しきい値 50% / 90% / 100%） |
| しきい値 | **50% / 90% / 100%** でメール |

本番会員拡大後は実測を見て引き上げ。

### 6. クォータ上限

API とサービス → 各 API → クォータで、日次／分あたりの上限を控えめに設定（異常利用時の請求上限）。デモ期は必須ではないが、予算アラートとセットで推奨。

### すぐ開くリンク（プロジェクト `serch-property-management-co`）

- Directions 有効化: https://console.cloud.google.com/apis/library/directions-backend.googleapis.com?project=serch-property-management-co&hl=ja  
- 認証情報（リファラ／API制限）: https://console.cloud.google.com/apis/credentials?project=serch-property-management-co&hl=ja  
- 予算とアラート: https://console.cloud.google.com/billing/budgets?hl=ja  

---

## GitHub Pages へのキー注入（開発・移管作業）

リポジトリ: `m19mhrts83-cyber/project-GE`

1. GitHub → Settings → Secrets and variables → Actions  
2. Secret 名: **`GOOGLE_MAPS_BROWSER_KEY`**  
3. 値: 上記制限済みブラウザキー  
4. `pages-docs.yml` が `_site/shuhen-map.js` の `__GOOGLE_MAPS_BROWSER_KEY__` を置換してデプロイ

ローカル（置換前）はプレースホルダのままなので、画面のキー欄で開発する。

```bash
# Secret 更新例（値はチャットに出さない）
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
printf '%s' "$GOOGLE_MAPS_API_KEY" | gh secret set GOOGLE_MAPS_BROWSER_KEY -R m19mhrts83-cyber/project-GE
```

---

## 運営移管チェックリスト（Maps／周辺MAP）

Phase 5（Q&A 移管）とあわせて実施してよい。

- [ ] 運営 GCP（または運営 Google）プロジェクトで課金アカウントを確認
- [ ] ブラウザ用キーを新規発行（または移管）
- [ ] HTTP リファラを Pages URL に限定
- [ ] API 制限（JS / Places / Geocoding / Directions ± Static）
- [ ] Directions API 有効化
- [ ] 予算アラート 50/90/100%
- [ ] 日次クォータの上限設定
- [ ] GitHub Secret `GOOGLE_MAPS_BROWSER_KEY` を運営キーへ差し替え
- [ ] Pages 再デプロイ後、キー入力なしで地図・ピン・徒歩動線が動くことを確認
- [ ] 旧個人キーの無効化タイミングを合意

---

## 障害時の見方

| 症状 | 疑うところ |
|---|---|
| 地図が出ない・ApiNotActivated | API 未有効 or API 制限漏れ |
| RefererNotAllowedMapError | リファラ未登録／タイポ。**Raimo入口だけ失敗→Pages直開き**で切り分け。Raimo URL もキー制限に追加（上記 §2） |
| **「ピンを表示」が ⏳／ジオコードタイムアウト** | ①**APIキー期限切れ**（`The provided API key is expired`）→ Secret `GOOGLE_MAPS_BROWSER_KEY` を差し替え＆Pages再デプロイ ②リファラ拒否 ③Places/Geocoding 未有効・クォータ |
| ピンが立たない／未ヒットだらけ | ## E 形式崩れ・全角｜・見出し混入。**「## E 一括貼付」**に **コードブロック1つ**を貼って再実行 |
| 地図はあるが地名が無い | **クリーン表示ON**（仕様）。オフ→「表示を更新」 |
| ピンが一切見えない | 「ピンを隠す」ON |
| 動線だけ失敗 | Directions API 未有効 |
| OVER_QUERY_LIMIT／急な請求増 | クォータ／予算アラート・キー制限の漏れ |

### 貼付まわり（2026-08-10 是正）

アプリは **## E 一括貼付→自動振り分け**に対応（`shuhen-map.js`）。Step1.2 は **コードブロック1つ**（`===== 物件住所 =====` 形式）を推奨。旧・3分割コードブロックやデモ txt 全体も可。個別3欄手貼りも残す。

---

## 後回しでよいもの（運営から費用感が出たら）

- 自前サーバでのキー proxy
- 会員ログイン必須配信
- キーローテーションの定期運用
- Q&A の会員各自 Gemini キー（推奨しない）
