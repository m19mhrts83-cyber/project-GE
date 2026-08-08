# Quiet Edge — ヘルスケア日次ショートカット手順（初級者向け）

Apple ヘルスケアの主要指標を、毎朝（または起床後）iPhone ショートカットから Jarvis Dashboard に送ります。

- 送信先: `POST https://jarvis-dashboard-amber.vercel.app/api/quiet-edge/health/ingest`
- 保護: 共有シークレット（`QUIET_EDGE_INGEST_SECRET`）
- 画面: Quiet Edge の「Health」カードとカバレッジ

追加課金は不要です（Shortcuts 標準機能）。

**運用の順序**: まず本手順（Phase 2・Health）を毎朝回せるようにする → そのあと Journal 同期（Phase 3）を定常化すると、月次レビューの質が上がる。Phase 3 のコードは既にあるので、Health 確立と並行して Mac 同期だけ先に動かしてもよい。

---

## 事前準備（Mac / Vercel・1回だけ）

1. `.env.jarvis_private` に `QUIET_EDGE_INGEST_SECRET=`（長いランダム文字列）があること  
2. Vercel の **jarvis-dashboard** プロジェクト Environment Variables にも同名で入れる（Production / Preview）  
3. あわせて `JARVIS_SUPABASE_URL` と `JARVIS_SUPABASE_SECRET_KEY`（または SERVICE_ROLE）が Vercel にあること  
4. 変数追加後は **Redeploy** が必要（未デプロイだと `503 QUIET_EDGE_INGEST_SECRET 未設定`）  
5. URL: `https://jarvis-dashboard-amber.vercel.app/api/quiet-edge/health/ingest`

シークレットの値はチャットに貼らないでください。Jarvis に「ショートカット用のシークレットを教えて」と言えば、チャットに出さず案内できます。

---

## 送る指標（固定）

| metric | 意味 | 単位の目安 | ヘルスケアでの呼び方の例 |
|---|---|---|---|
| `sleep_hours` | 睡眠時間 | 時間（例 7.05） | 睡眠 |
| `spo2` | 血中酸素 | % | 取り込まれた酸素のレベル |
| `respiratory_rate` | 呼吸数 | 回/分 | 呼吸数 |
| `hrv` | 心拍変動 | ms | 心拍変動 |
| `resting_hr` | 安静時心拍 | bpm | 安静時心拍数 |

`source` は次のいずれか:

- `oramemo` … OraMemo / **MemoHealth** 由来（リング優先。Health 上のソース名は MemoHealth）
- `watch` … Apple Watch 由来
- `health_unknown` … 分からないとき（混在しやすいので常用しない）

同じ日・同じ metric で source が違う場合、画面では **oramemo → watch → health_unknown** の優先で表示します。

### 指標ごとの推奨 source（書き出し確認済み・2026-08）

| metric | 推奨 source | ヘルスケア検索でソースを絞る |
|---|---|---|
| `spo2` | `oramemo` | **MemoHealth**（無ければその日は送らない／後で Watch フォールバック可） |
| `hrv` | `oramemo` | **MemoHealth** |
| `sleep_hours` | `oramemo` | **MemoHealth**（AutoSleep と混在しやすい） |
| `respiratory_rate` | `watch` | Watch のみ存在するので **Apple Watch** または絞らず `watch` ラベル |
| `resting_hr` | `watch` | 同上 |

詳細・件数: `docs/Quiet_Edge_Healthソース引き継ぎ.md`

---

## リング優先の設定手順（既存 Quiet Edge Health 向け）

いま `source: health_unknown` のままだとリング優先は効きません。次の2系統に分けます。

### 1. SpO2（および後から HRV）を MemoHealth に絞る

1. SpO2 用の **ヘルスケアサンプルを検索** を開く  
2. フィルタを **すべて**  
3. **＋フィルタを追加** → **ソース**（または「データソース」）が **次と等しい** → **MemoHealth**  
4. 並び: 開始日・新しい順／制限 1  
5. 値を取得 → 変数 `spo2`  
6. サンプルが空の日は `spo2` を JSON に載せない（0 を送らない）

※ 「ソース」フィルタが無い／MemoHealth が出ない場合は、いったん絞らず次の「送信を2回に分ける」だけでも `source: oramemo` を付けられるが、Watch の値をリング扱いしてしまうリスクあり。そのときはスクショを Jarvis に共有。

### 2. 送信を2回に分ける（推奨・わかりやすい）

**POST A（リング）**

- `source`: `oramemo`（テキスト固定）  
- フィールド: `recorded_at` / `spo2`（あとで `hrv` / `sleep_hours`）  

**POST B（Watch）**

- `source`: `watch`  
- フィールド: `recorded_at` / `respiratory_rate` /（あとで `resting_hr`）  

どちらも同じ URL・同じ `x-quiet-edge-secret`。  
成功例: それぞれ `"ok": true`（upserted が指標数）。

### 3. 代替: 1回の POST で metrics 配列

本文をフラットではなく配列にする場合（上級）:

```json
{
  "recorded_at": "2026-08-08",
  "metrics": [
    { "metric": "spo2", "value": 96, "source": "oramemo" },
    { "metric": "respiratory_rate", "value": 14, "source": "watch" }
  ]
}
```

Shortcuts ではフィールド追加より難しいので、まずは **POST 2回** で十分です。

---

## iPhone「ショートカット」の作り方

### A. 新規ショートカット

1. iPhone で **ショートカット** アプリを開く  
2. 右上 **＋** → 「新規ショートカット」  
3. 名前を **Quiet Edge Health** などに変更  

### B. 日付を用意する

1. 「アクションを追加」→ 検索 **「日付」** → **現在の日付**  
2. もう一度追加 → **日付をフォーマット**  
   - 日付: 上の「現在の日付」  
   - フォーマット: **カスタム** → `yyyy-MM-dd`  
3. （任意）変数名を「記録日」にする  

※ 記録日は **起床側の暦日**（今日）で送ります。昨夜の睡眠も「今朝の日付」に載せる運用です。

### C. ヘルスケアから数値を取る

ショートカットの **ヘルスケア** アクションで、次を1つずつ取ります（機種・OSで表記が少し違います）。

例:

1. 「ヘルスケアサンプルを見つける」または「ヘルスケアの統計」  
2. 種類: 睡眠／酸素／呼吸数／心拍変動／安静時心拍数  
3. 期間: **今日** または **昨日の夜〜今朝**（取れる方）  
4. リング系は可能ならソース **MemoHealth**  
5. 結果を変数に入れる（例: `spo2`）

睡眠が「分」で取れた場合は、ショートカットで **÷60** して時間にしてから送ります。

取得できない項目は送らなくて構いません（あるものだけ JSON に載せる）。`0` は送らない。

### D. Web リクエストで送る

1. アクション追加 → **URL の内容を取得**（または「Webリクエストを実行」）  
2. URL: `https://（ダッシュボード）/api/quiet-edge/health/ingest`  
3. 方法: **POST**  
4. ヘッダ:
   - `Content-Type` = `application/json`
   - `x-quiet-edge-secret` = （準備したシークレット）  
5. リクエスト本文: **JSON**

最小例（数値は変数に差し替え）:

```json
{
  "recorded_at": "2026-08-07",
  "source": "health_unknown",
  "sleep_hours": 7.05,
  "spo2": 96,
  "respiratory_rate": 11.5,
  "hrv": 63,
  "resting_hr": 64
}
```

または配列形式:

```json
{
  "recorded_at": "2026-08-07",
  "source": "health_unknown",
  "metrics": [
    { "metric": "sleep_hours", "value": 7.05, "unit": "h" },
    { "metric": "spo2", "value": 96, "unit": "%" }
  ]
}
```

### E. 自動化（毎朝）

1. ショートカットアプリの **自動化** タブ  
2. **個人用オートメーション** → **時刻**（例: 7:00）  
3. 実行するショートカット: Quiet Edge Health  
4. 「実行の前に尋ねる」は慣れるまで ON でも可。慣れたら OFF  

MemoHealth / ヘルスケアを朝に開いたあと実行する運用でも問題ありません。

---

## 成功の確認

1. ショートカット実行後、レスポンスに `"ok": true` があれば成功  
2. Jarvis Dashboard → Quiet Edge → **Health** カードに数値が出る  
3. カバレッジのバーが増える  

---

## うまくいかないとき

| 症状 | 確認 |
|---|---|
| 401 unauthorized | シークレット不一致。ヘッダ名は `x-quiet-edge-secret` |
| 503 Secret / Service Role 未設定 | Vercel 環境変数と再デプロイ |
| 400 recorded_at | `YYYY-MM-DD` 形式か |
| 400 未対応 metric | 上表の名前以外を送っていないか |
| ヘルスケア権限 | ショートカット初回で「ヘルスケアへのアクセス」を許可 |
| 数値が空 | その日まだサンプルが無い／リング・Watch 未同期。MemoHealth とヘルスケアを一度開く |
| OraMemo の値がヘルスケアに無い | MemoHealth の「ヘルスケアと連携」を確認。無ければ Watch 分だけ `watch` で送る |

---

## OraMemo（MemoHealth）について

OraMemo Ring のデータが Apple ヘルスケアにどの項目で出るかは機種・アプリ設定次第です。

1. MemoHealth でヘルスケア連携が ON か確認  
2. ヘルスケア「データソース」に MemoHealth があるか確認  
3. 分かる項目は `source: "oramemo"`、分からなければ `health_unknown`  

リングと Watch で同じ metric が両方ある場合は、両方送っても構いません（表示はリング優先）。

---

## ローカル検証（任意）

```bash
curl -sS -X POST "http://localhost:3001/api/quiet-edge/health/ingest" \
  -H "Content-Type: application/json" \
  -H "x-quiet-edge-secret: （シークレット）" \
  -d '{"recorded_at":"2026-08-07","source":"health_unknown","sleep_hours":7.05,"spo2":96,"hrv":63,"resting_hr":64,"respiratory_rate":11.5}'
```

成功例: `{"ok":true,"upserted":5,...}`
