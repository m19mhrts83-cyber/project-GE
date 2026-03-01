# Notion タスク登録スクリプト（MCP 障害時の代替手段）

Notion MCP の `parent` 文字列化バグで `create-pages` が使えない場合、Notion API を直接呼び出すスクリプトでタスクを登録できます。

**Python 版**のスクリプトで Notion API を直接呼び出します。

---

## 事前準備

### 1. Notion Integration の作成

1. [Notion Integrations](https://www.notion.so/my-integrations) を開く
2. 「＋ 新しいインテグレーション」をクリック
3. 名前（例: `Cursor タスク登録`）を入力して作成
4. **Internal Integration Secret** をコピー（`secret_...` で始まる）

### 2. データベースへの共有

1. [所有物件タスク管理(共有)](https://www.notion.so/25ef6bbe5a7680adbdd1e5c378572cac) を開く
2. 右上の「…」→「コネクト」→ 作成した Integration を選択して接続

### 3. トークンの設定

**方法A（推奨）**: このスクリプトと同じフォルダに `.env` を作成し、1行だけ記述

```
NOTION_API_KEY=secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

※ `.env` は Git にコミットしないこと（秘密情報のため）

**方法B**: ターミナルで毎回 `export NOTION_API_KEY="secret_xxxx"` してから実行

### 4. Python 依存関係（Python 版を使う場合）

```bash
cd "C1_cursor/1b_Cursorマニュアル"
pip install -r requirements_gmail.txt   # requests も含む
```

---

## スクリプトの使い方

### Python 版（推奨）

```bash
cd "C1_cursor/1b_Cursorマニュアル"
python create_notion_task.py
```

### その他の Python スクリプト

| スクリプト | 用途 |
|---------|------|
| `create_notion_task.py` | タスクを1件登録 |
| `create_minitech_tasks.py` | ミニテック向け4点依頼を4件のタスクとして登録 |
| `update_notion_task.py` | 既存タスクのプロパティを更新（引数: page_id） |
| `fix_minitech_object_name.py` | ミニテック4件の物件名を一括修正 |
| `fix_minitech_status.py` | ミニテック4件のステータスを「メンバー_進行中」に一括更新 |

初回実行時に Integration の接続・DB 共有が済んでいないとエラーになります。

---

## 登録内容の変更

スクリプト内の `TASK` や `properties` を編集して、登録するタスクの内容を変更できます。
