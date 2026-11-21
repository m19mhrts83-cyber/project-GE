# FlowForge 読み取りプロキシ — OpenAPI（ChatGPT Actions 用）

- 実装: `apps/jarvis-dashboard/app/api/flowforge/`
- 調査: [`54_FlowForge読み取りAPI調査_20261106.md`](./54_FlowForge読み取りAPI調査_20261106.md)
- **Production**: 2026-11-06 デプロイ済（`jarvis-dashboard` / `FLOWFORGE_READ_PROXY_KEY`）

## 認証

| 方式 | ヘッダ |
|---|---|
| Bearer | `Authorization: Bearer $FLOWFORGE_READ_PROXY_KEY` |
| 専用 | `x-flowforge-read-key: $FLOWFORGE_READ_PROXY_KEY` |

キーは `.env.jarvis_private` / Vercel Secret。チャット・GPT Instructions 本文に書かない（Actions の認証欄のみ）。

## エンドポイント

ベース（本番想定）: `https://jarvis-dashboard-amber.vercel.app`  
ローカル: `http://localhost:3001`

### 1. shareId 直指定

`GET /api/flowforge/share/{shareId}?summary=1`

### 2. URL / flowId / agentId 解決

`GET /api/flowforge/resolve?url=…`  
`GET /api/flowforge/resolve?flowId=flow_…`  
`GET /api/flowforge/resolve?agentId=312`  
`GET /api/flowforge/resolve?shareId=…`

`summary=1` でノード要約のみ（トークン節約）。

## OpenAPI 3.1（Actions 貼付用）

```yaml
openapi: 3.1.0
info:
  title: Jarvis FlowForge Read Proxy
  version: "1.0.0"
  description: Read-only FlowForge (AI Automation) flow JSON via share API.
servers:
  - url: https://jarvis-dashboard-amber.vercel.app
    description: Production
paths:
  /api/flowforge/resolve:
    get:
      operationId: resolveFlowforgeFlow
      summary: Resolve share/flow/agent URL and return flow JSON
      parameters:
        - name: url
          in: query
          schema: { type: string }
          description: FlowForge share or edit URL
        - name: flowId
          in: query
          schema: { type: string }
        - name: agentId
          in: query
          schema: { type: string }
          description: e.g. 312
        - name: shareId
          in: query
          schema: { type: string }
        - name: summary
          in: query
          schema: { type: string, enum: ["1"] }
      responses:
        "200":
          description: Flow payload
        "401":
          description: Unauthorized
  /api/flowforge/share/{shareId}:
    get:
      operationId: getFlowforgeShare
      summary: Fetch flow by shareId
      parameters:
        - name: shareId
          in: path
          required: true
          schema: { type: string }
        - name: summary
          in: query
          schema: { type: string, enum: ["1"] }
      responses:
        "200":
          description: Flow payload
        "401":
          description: Unauthorized
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
security:
  - bearerAuth: []
```

## ChatGPT 登録手順（2026-11-06 更新）

**注意**: Plus アカウントでは **Custom GPT の新規作成は不可**（GPT 自体は 2026-12-11 廃止予定）。旧「Actions に OpenAPI 貼付」は使えない。代替は **Plugins**。

### 済（Jarvis 実施）

1. Plugin Creator（Work）で個人用プラグイン **「FlowForge読取（Jarvis）」** を作成・インストール済み
2. スキル指示（share URL / agentId / `summary=1`・読み取り専用・キー非再掲）を登録済み
3. 本番プロキシは稼働中（`FLOWFORGE_READ_PROXY_KEY`）

### 自動取得（カスタム MCP・2026-11-07）

実装: `GET|POST https://jarvis-dashboard-amber.vercel.app/api/flowforge/mcp`  
Auth: `Authorization: Bearer $FLOWFORGE_READ_PROXY_KEY`（REST プロキシと同じキー）  
Tool: `resolve_flowforge_flow`（`url` / `shareId` / `flowId` / `agentId`、既定 `summary=true`）

**ChatGPT への登録**

ChatGPT の「カスタム MCP」UIは **OAuth / 認証なし**のみ（Bearer 欄なし）。  
→ 登録 URL に `?key=` を埋め、認証は **認証なし** を選ぶ。

1. [chatgpt.com/plugins](https://chatgpt.com/plugins) → **追加** → **カスタム MCP サーバーを追加**
2. 名前: `FlowForge Jarvis MCP`
3. 説明: `FlowForge フロー読取（read-only）`
4. URL: `https://jarvis-dashboard-amber.vercel.app/api/flowforge/mcp?key=` + `FLOWFORGE_READ_PROXY_KEY`
5. 認証: **認証なし**
6. リスク確認にチェック → **プラグインとして作成** → インストール
7. 既存 **FlowForge読取（Jarvis）**（スキル）と併用可

curl / Jarvis 本線は従来どおり `Authorization: Bearer …`（`?key=` 不要）。

### チャッピー（ChatGPT）での使い方

| 渡し方 | できる？ | 例 |
|---|---|---|
| **FlowForge の share URL を貼る** | **はい**（MCP 接続後） | `https://flowforge-….run.app/share/xxxx` を貼って「設計改善して」 |
| **編集画面の `/flows/flow_…` URL** | はい（agent 登録の share に解決できるとき） | 312 の編集 URL |
| **「agentId 312 を見て」** | はい | `@FlowForge読取（Jarvis） agentId 312 を読んで改善案を` |
| **URL なし・MCP 未接続** | 不可（自動取得できない） | Jarvis に取ってもらい要約を貼る |

推奨プロンプト:

```
@FlowForge読取（Jarvis）
このフローを読んで、優先度順に設計改善案を出して。
https://flowforge-259747770348.asia-northeast1.run.app/share/tn9-F4fhdIgHVpRl
```

または:

```
@FlowForge読取（Jarvis） agentId 312 のフローを summary で読んで改善案を。
```

停止: `FLOWFORGE_READ_PROXY_DISABLE=1`

## 編集用の読み取りと修正文の待ち箱（2026-11-21）

松野さんが修正文をコピーして貼る作業をなくすための追加。FlowForge には書き込み口が無いので、
**FlowForge 画面の AIアシスタントへ、Mac のプログラムが代わりに入力する**形にした。

### 流れ（番号は会話と対応）

| # | 主体 | 実行者／道具 | 作業 |
|---|---|---|---|
| 1 | AI | ChatGPT＋MCP `resolve_flowforge_flow`（`view=edit`） | フローを読む（ノードの ID・種別・タイトル・説明・所属サブフロー、矢印、つながっていないノード） |
| 2 | AI | ChatGPT | 図・改訂案 → 修正文（1文1操作・実際のタイトルで名指し・1回4項目程度） |
| 3 | 人間 | 松野さん（ChatGPT のチャット） | 修正文を読み「これで反映して」と言う |
| 4 | AI | ChatGPT＋MCP `queue_flowforge_edit` | 了承済みの修正文を待ち箱（Supabase `flowforge_edit_queue`）へ置く |
| 5 | プログラム | Mac `scripts/jarvis_flowforge_assistant_paste.py --queue-once` | 待ち箱から拾い、置き場の Chrome で AIアシスタントへ入力・送信、返事と前後のノード数を書き戻す |
| 6 | 外部サービス | FlowForge の AIアシスタント | フローを書き換える |
| 7 | AI | ChatGPT＋MCP `get_flowforge_edit_status` → `view=edit` で読み直し | 狙いどおりか照合。ずれていれば 2 へ戻る（今回の取り直し） |

- 5 は AI を呼ばない。Mac が起きていて、Chrome が開いている時だけ動く
- 5 を自動で回す見張り（launchd 常駐・5秒ごと）: `launchd/install_flowforge_edit_queue_launchd.sh` で登録する
  - 置かれてから60分を過ぎた依頼は送らない（了承が古い）。`cancelled` になる
  - 持ち主のタブが無ければ、置き場のプロフィール（`FLOWFORGE_CHROME_PROFILE`、既定 `Default`）で FlowForge のトップを開いて探し直す
  - 初回は macOS が「Google Chrome の制御を許可しますか」と聞く。許可が要る
  - AIアシスタントの会話は10ターンで打ち切られる。上限に達していたら、プログラムが「新しい会話」を押してから送る（フローはそのまま。2026-11-21）
  - 取り消しは AIアシスタントの入力欄を使わないので、上限に達していても動く
  - ログ: `~/Library/Logs/jarvis_flowforge_edit_queue/`。止める: `launchctl bootout "gui/$(id -u)/com.matsunoma.jarvis.flowforge-edit-queue"`
- 7 の読み直しは共有リンク経由。共有リンクは編集の最新を映す（2026-11-21 確認）

### 置き場の決まり

- **FlowForge の編集は「Chrome の既定プロフィール」だけで行う**（2026-11-21 松野さん）。
  FlowForge は最初に保存したブラウザを持ち主として扱うため
- 持ち主でないブラウザで `/flows/flow_…` を開かない。同じ ID の空の「新しいフロー」がそのブラウザに作られる
  （プログラムは先に保存内容を確かめ、持ち主でなければ編集画面を開かずに止める）
- Cursor のブラウザにある元のフローは、移し終わるまで消さない
- **FlowForge の編集タブは、同時に1つだけ開く**（2026-11-21）。FlowForge はタブごとに「全フローの内容」を持ち、
  編集のたびに全フローをまとめて保存する。タブ同士で内容を合わせないので、古いタブで編集すると、
  他のタブで直したフローが古い内容で上書きされる
  - プログラムは編集の直前に、タブの内容とブラウザの保存内容を比べ、古ければタブを読み込み直す。直らなければ止める
  - 編集の後、同じブラウザの他の FlowForge 編集タブを読み込み直す（結果の `other_tabs_reloaded`）
  - 人が手で編集する時は守られない。複数開いていたら、編集の前にそのタブを読み込み直す
- 移し方: 元のブラウザで「フローを共有」→ 共有 URL を Chrome の既定プロフィールで開く →
  上部の「このフローを自分の作業用にコピー」。ID が変わるので registry を付け替える。
  「みんなのフローに載せる」は押さなくてよい
- Chrome の「表示 > デベロッパー > Apple Events からの JavaScript を許可」がオンであること
- **編集の共通ロック**（2026-11-22）: 待ち箱の常駐・手元の編集（`jarvis_flowforge_assistant_paste.py`）・新規作成
  （`jarvis_flowforge_create_flow.py`）は `~/git-repos/.jarvis_state/flowforge/edit.lock` を取ってから動く（同時に1つ）。
  常駐はロックが取られていると待ち箱を拾わずに次の見回りへ回す（依頼は queued のまま）。
  常駐がこのロックを使うのは、main へのマージ後に本体が追従し、常駐を読み込み直してから（それまでは新規作成側が待ち箱の空を確かめて待つだけ）

#### 置き場へ移すコマンド（2026-11-21）

社員ごとに1回。AI は呼ばない。**worktree で実行する**（`~/git-repos` の本体では登録を付け替えない）。

```bash
~/selenium_env/venv/bin/python scripts/jarvis_flowforge_migrate_to_home.py --agent 315 --dry-run     # 何も作らず状況だけ
~/selenium_env/venv/bin/python scripts/jarvis_flowforge_migrate_to_home.py --agent 315 --write-repo  # コピー・照合・共有リンク発行・登録の付け替え
```

- やること: 登録の共有リンクを読む → 置き場の Chrome でコピー → 中身を元と照合 → 新しい共有リンクを発行 → registry・共有リンク一覧・資料の ID を付け替え
- 止まる時: 共有リンクが未登録（317）／共有リンクが登録の ID と違うフローを指している／置き場に同じ内容のコピーがすでにある／照合で違いが出た
- 実行の後: `jarvis_agent_team_status_sync.py --no-drive` で `agentTeam.json` を作り直し、意図したファイルだけを PR にする
  （同期は他の部門ボードの日付も書き換えるので、それらは戻す）
- 元のフロー（Cursor 側）は消さない。FlowForge 側には、コピーを消してもクラウドに写しが残る（画面からは消せない）
- 2026-11-21 時点: `--dry-run` と止まる条件は実機で確認済み。コピー・共有リンク発行の部分は 315 で初めて通す

### 道具（MCP）

| Tool | 用途 |
|---|---|
| `resolve_flowforge_flow` | `view`: `summary`（既定）／`edit`（修正文づくり・照合用）／`full` |
| `queue_flowforge_edit` | `agentId`・`instructions`・`confirmedByUser=true`。2000文字・箇条書き6項目まで。待ち5件で満杯 |
| `get_flowforge_edit_status` | `id` → `queued`／`running`／`sent`／`error` 、AIアシスタントの返事、増えた／消えた矢印とノード |
| `patch_flowforge_flow` | **既存フローの変更はこれが本線。** `agentId`・`operations`（12件まで）・`confirmedByUser=true`。AIアシスタントを通さない |
| `undo_flowforge_edit` | 送信済みの修正の `id`・`confirmedByUser=true`。その修正の直前の状態まで「元に戻す」を押す |

待ち箱の表は `apps/jarvis-dashboard/supabase/migrations/20261121_flowforge_edit_queue.sql`（適用が要る）。
ChatGPT 側は、道具が増えたあとプラグイン「FlowForge Jarvis MCP」をつなぎ直す。

### 1社員に複数フローがある時の agentId（2026-11-21・315-B）

- 本体は社員番号のまま（`315` ＝ 315-A）。2本目以降は **社員番号＋`-`＋英大文字**（例: `315-B`）で、`agents_registry.yaml` の
  その社員の `extra_flows`（id・label・flowforge_id・flowforge_url）に登録し、共有リンクは
  `config/flowforge_share_urls.json` の `by_agent_id` に同じキー（`"315-B"`）で足す。`status_sync` が `agentTeam.json` の
  その社員行に `extra_flows` として写す（社員の行は増やさない・置き換えない）。
- 形式は3桁、または3桁＋`-`＋英大文字。`resolve`／`queue`／`patch` の `agentId` は同じ表で解決し、未登録は今までのエラー。
- 登録済み: 315-A（`315`）週次連携健全性点検 ＝ `flow_S5g_i7CCiE0P6RKIp2_MkMTA`／
  315-B 300番台 停止・空回り監視（日次）＝ `flow_ZQIfYZY4GJF2XspXY8i0sGWD`（共有 `smnVr23mbD8pb2sT`、2026-11-22 切替）。
  旧315-B（`flow_qJcURKdC36ARzDdSwEfLisvt`／共有 `oHjDFZowlMMaxtkb`）は記録として残し、削除・編集していない。
- Mac の待ち箱処理は、待ち箱の `agent_id`（`315-B`）から registry の今の flowId を引く。Mac の `~/git-repos` が古いと
  `315-B` が見つからないか旧315-Bを参照する。マージ・デプロイ後に Mac の `~/git-repos` を `main` へ追従させ、共有リンク経由で resolve を確認する。
  `flow_id_for_agent` は1件ごとに `agentTeam.json` を読み直すため、今回の参照先だけの変更では見張り再起動は不要。処理中の依頼があれば完了を待ち、旧flowIdを持つ待ち箱の扱いは別途確認する。

### Mac 側のコマンド

```bash
cd ~/git-repos && ~/selenium_env/venv/bin/python scripts/jarvis_flowforge_assistant_paste.py --agent 311 --check
cd ~/git-repos && ~/selenium_env/venv/bin/python scripts/jarvis_flowforge_assistant_paste.py --queue-list
cd ~/git-repos && ~/selenium_env/venv/bin/python scripts/jarvis_flowforge_assistant_paste.py --queue-once
```

### 頼んでいない変更に気づく（2026-11-21 の試験で判明）

FlowForge は、頼んでいない変更をすることがある。311 で「経路B → 合流 の矢印を1本追加」を2回試し、2回とも同じ結果だった。

- 頼んだ矢印は追加された
- もともとあった「経路A → 合流」が消えた（1つのノードに矢印を2本合流させる形を保てない可能性。1例だけで断定はしない）
- 孤立していたノードが自動でつながれた（返事に「孤立を機械接続しました」。意味として誤った輪ができた）
- 「それ以外は変更しないで」と書いても防げない

対応: 送信の結果に、増えた／消えた矢印とノードを記録する。ChatGPT は頼んだ内容と比べ、余分があれば本人へ伝え、
`undo_flowforge_edit`（Mac 手動なら `--agent 311 --undo N`）で戻す。取り消しは直後向け（間に別の編集があると戻りきれない）。

### 根本原因と直接編集（2026-11-21）

「頼んでいない変更」の原因を、FlowForge の画面のプログラムを読んで特定した。AI の気まぐれではなく、決まった処理。

| # | 原因（FlowForge 側の処理） | 起きること |
|---|---|---|
| 1 | AIアシスタントの返事のあと、変更されたノードに孤立があると「孤立の修復」が走る（AI に聞く → だめなら機械的に接続） | 説明文だけの更新でも矢印が足される |
| 2 | AIアシスタントの返事のあと、必ず「入り1本・出1本の強制」と自動整列が走る | 合流・分岐の矢印が外される。位置が動く |
| 3 | 矢印の追加の操作そのものが、同じ始点／同じ終点の既存の矢印を外してから足す | 1つのノードへ2本目を引くと、1本目が消える |

1〜3 は自然言語の指示では止められない。3 は FlowForge のデータの形（各ノードの矢印は入り1本・出1本。
サブフローの中は中で数える。サブフローをまたぐ矢印はサブフローそのものに付く）で、合流・分岐は描けない。

**対策: 直接編集（`patch_flowforge_flow`）を本線にする。** AIアシスタントを通さず、画面が使っている保存部品の操作を、
ノード ID・矢印 ID の指定で Mac のプログラムが呼ぶ。手で編集した時と同じ経路なので、履歴（元に戻す）と
クラウド同期はそのまま働き、1・2 の処理は走らない。

| 段階 | 主体 | 内容 |
|---|---|---|
| 計画 | プログラム | 実行の直前に最新の状態を読み、操作を点検し「実行後こうなるはず」を計算する。1件でも問題があれば何も適用しない |
| 実行 | プログラム | 履歴1件ぶんとして適用する |
| 検証 | プログラム | 実行後の状態を計画と比べる（ノードの増減・種別・所属・位置・文言、矢印の増減） |
| 復元 | プログラム | 違いがあれば1手戻す。いちばん上の履歴が自分の入れたものである時だけ戻し、戻せたか（矢印の ID まで一致）も確かめる |

操作は3種類: `update_node`（`title`／`description`／`meta`／`toolName`）、`add_edge`、`remove_edge`。

- 既存の矢印を外すことになる `add_edge` は断る。置き換えてよい時だけ `replace=true`（本人了承が前提）
- ノードの追加・削除は直接編集に入れていない。AIアシスタント経由（`queue_flowforge_edit`）を使う
- AIアシスタント経由で「ノードと矢印は変えない」依頼を送る時は `lockStructure=true`。
  ノードか矢印が増減したら、送信前の状態まで自動で戻して `error` にする
- 合流・分岐を表したい時は、1本の流れにして、分かれ方をノードの説明文に書く

Mac で手動: `--agent 311 --patch-file ops.json --dry-run`（計画だけ）／`--patch-file ops.json`（適用）。

### 検証（2026-11-21）

- 済: 311 のコピーを Chrome の既定プロフィールに作成（中身は元と一致）。確認モード・入力だけ・送信
  （編集を伴わない質問）・返事の取り込み・前後比較
- 済（追記）: 311 の registry 付け替え、待ち箱を通した送信、実際の修正文での書き換え、差分の記録、取り消し（送信前の状態へ復帰を確認）。共有リンクは編集の最新を映す
- 済（追記2）: 本番 MCP から送信→取り消しを通す試験、見張り（`--queue-watch`）を手元で動かして自動で拾うこと
- 済（追記3）: 見張りの launchd 登録、10ターン上限の対応
- 済（追記4・直接編集）: テスト用コピー（311 の写し。311 本体は未変更）で、説明文4か所の更新で矢印・ノードが変わらないこと、
  合流になる矢印の追加が断られること、衝突しない矢印1本の追加で他が変わらないこと、置き換え・削除、
  計画との不一致からの自動復元、`lockStructure` での自動復元（AIアシスタント経由で矢印4本追加・1本削除を再現 → 送信前に復帰）
- 未: 待ち箱を通した `patch_flowforge_flow` の一連の試験（表の列追加・デプロイ・本体追従の後）、312〜317 の移行
- 残るリスク: FlowForge の画面の作りが変わると保存部品に届かなくなる（その時は何も変えずに止まる）。
  復元の直前に途中の状態がクラウドへ同期されている可能性（その後の同期で実行前の内容に戻る）

## curl 例（値は出さない）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
curl -sS -H "Authorization: Bearer $FLOWFORGE_READ_PROXY_KEY" \
  "http://localhost:3001/api/flowforge/resolve?agentId=312&summary=1"
```

### ローカルCLIでの新規作成・ノード追加（2026-11-22）

本人が具体的な図を承認した時だけ使用する。AIアシスタントは呼ばない。MCPのpatch/queue契約は変更しない。

- 新規: `python scripts/jarvis_flowforge_assistant_paste.py --create-file approved-flow.json --dry-run` → `--dry-run`を外して作成。
- JSON: `id: flow_…`, `name`, `description`, `nodes`（id/kind/title/x/y、任意parentId/subtype/description/meta/toolName）、`edges`（id/source/target）。開始・終了各1、各scopeは一本道。位置は整数。
- 既存ノード追加: ローカル `--patch-file` の操作に `{"op":"add_node","node":{"id":"stable_id","kind":"tool","title":"処理","x":400,"y":170}}`。矢印は追加しないので、remove_edge/add_edgeを明示する。同じ12操作上限。既存ID・不明親・不正種別は拒否。
- 新規作成は置き場の安全なトップで、ID不存在・タブ鮮度を確認してからstore.loadFlow。未知の編集URLへ先に移動しない。既存フローは従来の所有確認を必須とする。
- 適用前の全フローの写しを `.jarvis_state/flowforge_backups/` へ権限600で保存。公開しない。差分外変更は直接編集のundo、新規は自分が作った同じ版のみ取り消す。verified=falseは失敗。
- verifiedはローカル内容の照合。さらに所有確認後の編集タブで同期し、共有を発行・共有API読取でノード/矢印/本文を照合してから実作図成功と報告する。共有発行も本人承認範囲でのみ行う。
- 新社員を増やさず既存社員に図を付ける場合、registry本体行にflowforge_id/url、共有configのby_agent_id/by_flow_idを登録し、status_sync --no-driveで投影する。過去のID別共有リンクは残す。


2026-11-22 実機検証の補足:

- サーバーは新しい任意IDのクラウド所有登録をsyncで受け付けず、HTTP403 flow_owner_mismatchとなった。ローカルstoreに保存できても新規フローの共有発行にはならない。CLIはlocal_verified=trueでもクラウド失敗ならverified=falseを返し、所有チェックを回避しない。人が「新しいフロー」で作成して共有を発行し、その所有フローをCLIで整えるのが確認済みの手順。未同期の下書きは削除了承を得るまで残す。
- 714の確定7ノードへの整形で明示了承されたノード削除を追加。ローカルpatchのremove_nodeはID指定のみ。開始/終了は削除不可、接続矢印と子は事前に明示して外す必要がある。自動再接続しない。削除も1つの履歴に入り、差分外変更はundoし照合する。MCP側の対応操作は従来どおりで増やしていない。
- Chromeのウィンドウ/タブはindexではなく永続IDで参照する。新規の所有編集タブは元のactive tabを保って背景に開く。画面が切り替わって別タブを操作する事故を避ける。
- 対象以外の全フローを写しと比較し、差分外変更があればverifiedにしない。同期は画面と同じsession/sync APIを使用し、クラウド失敗なら既存フローの変更はundo・復元照合。共有APIでの最終照合は別途必要。
- 714は所有フローを10→7ノード、312は10→11ノードへ変更し、同期と共有APIの一致を確認した。新規任意IDの所有登録と他ブラウザへの移行は保証しない。

### 新規作成コマンド（画面で作る・2026-11-22 松野さん了承）

ラスカル（Mac 上のプログラム）が、確定した工程文から新しいフローを1コマンドで作る。AI は呼ばない（生成は FlowForge の画面のボタン）。
上の `--create-file`（データを直接作る）は 403 flow_owner_mismatch になるので新規には使わない。新規は必ずこのコマンド。

```bash
~/selenium_env/venv/bin/python scripts/jarvis_flowforge_create_flow.py --text-file 工程.txt --plan 確定.json --dry-run   # 何も変えない
~/selenium_env/venv/bin/python scripts/jarvis_flowforge_create_flow.py --text-file 工程.txt --plan 確定.json --agent 318
~/selenium_env/venv/bin/python scripts/jarvis_flowforge_create_flow.py --text-file 工程.txt --status                     # 台帳だけ
```

- `工程.txt`: 本人が確定した工程文（2000文字まで）。トップの「自動化したい業務を一言で」に入れる
- `確定.json`（任意・推奨）: 確定の形。`name`・`description`・`nodes`（id・kind・title、任意で parentId・subtype・description・meta・toolName・x・y、サブフローは width・height）・`edges`（id・source・target）。
  開始・終了は各1、各範囲は一本道。開始・終了の id は生成されたもの（start／end）に読み替え、位置も生成のまま。x・y を省くと並び順で置く。
  無い時は生成されたまま（`note` が出る。使う前に整える）
- 出力（JSON）: `flow_id`・`edit_url`・`share_url`・`nodes`・`edges`・`sync`（画面の表示・画面が送った sync の HTTP 状態・同じ sync API の結果だけ）・
  `diffs_before`／`diffs_after`・`shape`（整形の回ごとの verified）・`share_check`・`other_flows_changed`・`verified`・`next_steps`。秘密（匿名 ID・cookie・sync の本文）は出さない

工程（番号はコードの説明と同じ）:

| # | 実行者 | 作業 | 成功の条件 |
|---|---|---|---|
| 1 | プログラム | 共通の編集ロック（最大15分待つ）→ 待ち箱が空になるまで待つ（最大15分） | ロック取得・queued／running が0件。待ち箱を読めない時は「空」と扱わず止める |
| 2 | プログラム（Chrome） | 置き場の FlowForge タブを1つに絞る。他のタブは元 URL を台帳に書いてから about:blank。作業タブは永続 tab ID で指す | 作業タブの保存内容を読める |
| 3 | プログラム | 全フローの写し（`.jarvis_state/flowforge_backups/`・0600） | 書けた |
| 4 | プログラム → FlowForge の生成AI | トップに工程文を入れ、「AIにフローを作ってもらう」を1回だけ押す（押す前に台帳へ「押した」と書く） | 新しい flowId がちょうど1本増えた（最大5分待つ） |
| 5 | プログラム | 画面「クラウド同期済」＋画面が送った sync に 403 が無い＋同じ sync API が 200 | 3つとも |
| 6 | プログラム（#554 の直接編集） | 確定の形との差分 → 操作（フロー名・説明、矢印を外す、ノードを消す・足す、本文、矢印を足す）を計画だけで全部通してから、12操作ずつ適用 | 各回 verified（違えば その回を1手戻して止まる） |
| 7 | プログラム（Chrome） | 「フローを共有」で閲覧リンク（台帳にあれば再発行しない）→ 共有 API の中身と手元を照合 | 名前・説明・ノード・矢印が一致 |
| 8 | プログラム | 対象以外の全フローを写しと比較 → 2 で外したタブを元の URL へ戻す | 変化0件 |
| 9 | 人 | `next_steps` のとおり registry・`config/flowforge_share_urls.json`・`status_sync --no-drive` で登録（自動では書かない） | 本人了承の PR |

台帳（`~/git-repos/.jarvis_state/flowforge/create_ledger.json`・0600。worktree が違っても同じ場所）:

- 鍵は工程文のハッシュ（本文は残さない。前後の空白・改行の違いは同じとみなす）。同じ工程文では二度作らない
- verified 済み・同じ確定の形 → 何もせず前回の結果を返す（`already_done`）。確定の形だけ変えた → 同じフローを整え直す（生成しない）
- 途中で止まった → 同じコマンドで続きから（作成済みなら生成しない。整形は今の状態から差分を取り直すので何度でも同じ結果）

止まる条件（終了コード）:

- 2: 工程文が空・長すぎる／台帳が読めない／置き場のタブを読めない／トップの入力欄・ボタンが見つからない／タブの内容が保存内容と食い違う
- 3: 待ち箱が空にならない・読めない　4: ロックが取れない（他の編集が使用中）
- 5: 生成が5分で終わらない（押し直さない）／新しいフローが2本以上／前回押した記録があるのに新しいフローが無い
  （画面で作られていないと確かめてから `--retry-generate`）
- 11: クラウド保存を確かめられない（403 など。フローは消さない）／整形の回が verified にならない／共有の照合・他フローの比較で違い
- 13: 確定の形の点検で止まった（作成済みなら `flow_id` を出す。整形は未実行）

戻し方:

- 作ったフローは消さない（消すか、公開一覧に載せるかは本人が決める。「みんなのフローに載せる」は押さない）
- 整形の途中で止まった: その回は自動で1手戻っている。前の回までは `--patch-file` の直接編集か画面の「元に戻す」で戻す。直してから同じコマンドで続き
- タブ: 止まっても最後に元の URL へ戻す。戻せなかったタブは台帳の `parked_tabs` に元 URL が残る
- 写し: `.jarvis_state/flowforge_backups/`（Git 対象外・0600）。中身を貼らない

2026-11-22 実機確認（確認用フロー1本）: `flow_tZFb1G8dJm1KBi-SdYbaD3kQ`「テスト用：週次の予定まとめ」。生成 9ノード／6矢印 → 2回（12＋12操作）の直接編集で
確定の 6ノード／4矢印（サブフロー1つ・子2つ）。画面「クラウド同期済」・sync 200（403 なし）・共有 `DYS58HEyqmLLrT0_` の中身が一致・verified。
既存12フローは前後の全比較で変化0、外したタブ1枚は元の URL へ戻った。同じコマンドの再実行は `already_done`（二重に作らない）。待ち箱の常駐は止めていない。

残るリスク:

- 画面の作り（入力欄・ボタンの文言・生成時間）が変わると止まる（変えずに止まる側に倒してある）
- 常駐が新しいロックに従うのは、本体の追従と常駐の読み込み直しの後。それまでは「始める前・押す前・各整形の前に待ち箱が空か」を確かめるだけで、
  その間に常駐が拾うと競合しうる
- 生成AIは工程文に無いもの（時刻・道具など）を足す。`--plan` で整えない場合は、そのまま使わない
- 置き場（Chrome 既定プロフィール）に依存。保存領域を消すと持ち主の情報も消える
