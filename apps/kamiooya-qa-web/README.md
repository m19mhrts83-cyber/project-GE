# 神・大家さん倶楽部 情報Q&A（Vercel公開用）

参照ファイル（CSV）を根拠に回答する、公開用のQ&AチャットWebアプリです。

## できること

- **検索＋引用**: `data/knowledge.csv` を全文検索し、上位一致（根拠）を表示
- **AI回答（任意）**: `OPENAI_API_KEY` がある場合のみ、参照（抜粋）を渡して回答文を生成
  - 未設定でも動きます（その場合は検索結果の提示のみ）

## 参照データ（ナレッジ）の入れ方

このアプリは **`apps/kamiooya-qa-web/data/knowledge.csv`** を読みます。

1. 既存の仕組み（WeStudy差分運用）で `full_*.csv` を生成  
   - 例: `215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/scripts/run_westudy_pipeline.sh`
2. 生成した **管理者形式CSV**（ヘッダに `コメントID` / `投稿日時` / `コメント内容` 等がある形式）を
   `apps/kamiooya-qa-web/data/knowledge.csv` として配置（置き換え）
3. GitHubへコミットしてVercelにデプロイすると、公開アプリの参照データが更新されます

注意: 公開アプリなので、`knowledge.csv` に個人情報・機密情報が含まれないように必ず確認してください。

## ローカル起動

```bash
cd apps/kamiooya-qa-web
npm install
npm run dev
```

ブラウザで `http://localhost:3000` を開きます。

## GitHub → Vercel で無料公開する手順

### 1) GitHubにプッシュ

このリポジトリ（`~/git-repos`）を GitHub に置いていればOKです。

### 2) Vercelで新規プロジェクト作成

- Vercelにログイン
- **New Project** → 対象GitHubリポジトリを選択
- **Root Directory** を **`apps/kamiooya-qa-web`** に設定

### 3)（任意）環境変数を設定

AI回答を使う場合のみ、Vercelの Environment Variables に設定します。

- `OPENAI_API_KEY`: OpenAI APIキー
- `OPENAI_MODEL`: 任意（未設定時 `gpt-4o-mini`）

未設定でもデプロイは成功し、検索結果ベースで動作します。

### 4) Deploy

Deploy後に発行されるURLを共有すれば、誰でも使えます。

## API

- `POST /api/search` `{ "query": "..." }`
- `POST /api/chat` `{ "message": "..." }`

