# Notion MCP（create-pages）parent パラメータ文字列化バグ 調査報告

**作成日**: 2026-02-11  
**対象**: `notion-create-pages` で「Expected object, received string (path: parent)」が発生する事象

---

## 1. 事象の整理

### 1.1 発生するエラー

```
MCP error -32602: Invalid arguments for tool notion-create-pages: [
  {
    "code": "invalid_type",
    "expected": "object",
    "received": "string",
    "path": ["parent"],
    "message": "Expected object, received string"
  }
]
```

### 1.2 発生タイミング

- **発生する**: `parent` パラメータを渡してデータベースに行を追加しようとするとき
- **関係ない**: `parent` を省略してワークスペースにページを作る場合は成功する（ただし DB 行にはならない）

### 1.3 一貫性のなさ

- ホームプランナー依頼時（2月頃、Obsidian ワークスペース）: **成功**
- ミニテック依頼時（同日〜1時間以内、215 ワークスペース）: **失敗**
- 同じ `parent` / `pages` 形式で呼び出しているのに結果が異なる

---

## 2. 根本原因

### 2.1 結論

**Cursor の Auto モデル選択時に、MCP ツールのネストされたオブジェクトパラメータ（`parent` など）が二重に JSON 文字列化されて MCP サーバーに渡る**ため、Notion MCP 側で「オブジェクトでなく文字列が来た」と検証エラーになる。

### 2.2 技術的な流れ

1. **Cursor クライアント（Auto モデル選択時）**
   - ツール引数（`parent` など）を JSON としてシリアライズする際、オブジェクト型のパラメータを**文字列として**送信してしまう
   - `parent` が `{"type":"data_source_id","data_source_id":"25ef6bbe-..."}` であるべきところ、`"{\"type\":\"data_source_id\",...}"` という**文字列**になって届く

2. **Notion MCP サーバー**
   - Zod スキーマで `parent` を「オブジェクト」として検証している
   - 実際には文字列が届くため `invalid_type: expected object, received string` でエラー

3. **Notion API**
   - この検証の段階で失敗するため、Notion API にはリクエストが届いていない

### 2.3 「セッションや状態で成功する」理由

- Cursor フォーラム（[thread #145807](https://forum.cursor.com/t/cursor-auto-selected-model-stringifies-mcp-tool-parameters/145807)）の報告では、
  - **Model: Auto** → 失敗
  - **Model: Sonnet / Opus を明示選択** → 成功
- ホームプランナーで成功したときは、そのチャットで **Sonnet または Opus が明示的に選択されていた**可能性が高い
- ワークスペースやチャットごとに「どのモデルが使われるか」が異なるため、同じ呼び出しでも成功・失敗が分かれる

### 2.4 関連 Issue・ソース

| 種類 | リンク | 要点 |
|------|--------|------|
| Notion MCP | [GitHub Issue #181](https://github.com/makenotion/notion-mcp-server/issues/181) | parent が string 化される |
| Notion MCP | [GitHub Issue #82](https://github.com/makenotion/notion-mcp-server/issues/82) | create-pages / move-pages の object パラメータが string 化 |
| Cursor | [Forum #145807](https://forum.cursor.com/t/cursor-auto-selected-model-stringifies-mcp-tool-parameters/145807) | Auto 時に stringify、Sonnet/Opus で正常 |
| Claude Code | [Issue #3023](https://github.com/anthropics/claude-code/issues/3023) | クライアント側バグと認定 |

---

## 3. 想定される対策（実施可能なもの）

### 3.1 【即効】モデルを明示的に選択する（推奨）

**手順**

1. チャット上部のモデル選択で **「Auto」以外** を選ぶ（例: **Sonnet** または **Opus**）
2. その状態で「Notion にタスクを登録して」と依頼する

**根拠**: Cursor フォーラムで、Sonnet/Opus を明示選択すると正常に動作することが報告されている。

### 3.2 【中期】Notion Integration + API スクリプト

Notion API を直接叩く Node スクリプトを用意し、Integration トークンでデータベースに行を追加する。

- **メリット**: MCP のバグの影響を受けない
- **デメリット**: Notion で Integration を作成し、トークンを取得・設定する必要がある
- **参考**: `C1_cursor/1b_Cursorマニュアル/Notion_タスク登録スクリプト.md`（後述）

### 3.3 【長期】Notion MCP / Cursor の修正待ち

- **Notion MCP**: GitHub Issue #181, #192 で修正が議論中
- **Cursor**: フォーラムで「エンジニアに伝えた」と回答あり。修正リリース待ち

---

## 4. 今すぐ試す手順（モデル明示選択）

1. このチャットの**モデル選択**を **Sonnet** または **Opus** に変更する
2. 「ミニテックの4点依頼・相談を Notion の所有物件タスク管理に登録して」と**同じチャットで**再度依頼する
3. 成功すれば、以降は Notion 登録の依頼時に「モデルを Sonnet/Opus に固定」することで回避できる

**注意**: Auto は課金を抑えたいときに推奨される設定だが、Notion MCP 登録だけは Sonnet/Opus で依頼する必要がある。その回だけ課金単価が上がる。手動登録や API スクリプトを選べば Auto のまま運用も可能。

---

## 5. 補足

- 現象は **Notion MCP の不具合**というより、**Cursor の Auto モデル選択時のパラメータシリアライズ**が原因
- Notion MCP 側で「文字列が来たら JSON.parse する」といった対策も可能だが、現状の公式サーバーには入っていない
- フォーク `@mieubrisse/notion-mcp-server` に修正版があるが、mcp-remote の `mcp.notion.com` から切り替えると OAuth 設定の変更が必要
