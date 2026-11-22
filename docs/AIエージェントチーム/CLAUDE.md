# AIエージェントチーム・ハブ指示（全ツール共通）

Claude Code / Cursor（Jarvis）/ Codex / GenCode / Grok Bot など、**どの実行ツールでも**このフォルダを触るときは従う。  
（社員フォルダと同じく **正本はこの `CLAUDE.md`**。`AGENTS.md` は互換の入口だけ。）

## 必読

| 文書 | 用途 |
|---|---|
| [`00_このフォルダ.md`](00_このフォルダ.md) | ハブ入口 |
| [`agents_registry.yaml`](agents_registry.yaml) | 社員ID・path・**status** の正本 |
| [`22_運用状態の識別_20261011.md`](22_運用状態の識別_20261011.md) | 状態の見え方・更新手順 |
| [`06_社員の作り方_二段階_20261009.md`](06_社員の作り方_二段階_20261009.md) | 新規作成の二段階 |
| [`05_機密とenv二層_20261009.md`](05_機密とenv二層_20261009.md) | 秘密は二層。MDに値を書かない |
| [`30_共通Agentフォルダ規格_BCP`](30_共通Agentフォルダ規格_BCP_20261017.md) | TASK／input／output／tests（ツール切替BCP） |
| [`31_作業ロック`](31_作業ロック_二重起動防止_20261017.md) | 二重起動防止。CLI `jarvis_agent_run_lock.py` |
| [`43_Claude Code 受け渡し`](43_Claude_Code参加_受け渡し_20261023.md) | Claude Code 参加・三層受け渡し |
| [`49_共通ルール`](49_共通ルール_AI使用量と入力_20261024.md) | **音声入力（Typeless）の誤記前提・文字起こしはスクリプト・PDFの元MD・「聞く」はコスパの良い順・読む量を減らす・Todoist の記録と名乗り・相手への依頼は「こちらでやること／お願いすること」を分ける（R8）・Miss Lemon は一人に見せる（クラウド＝考える・返事／Mac＝実行）・Mac の状態は確かめてから書く（R12）・Obsidianは書類正本＋OGD印（R11）** |
| [`52_議事録のまとめ方`](52_議事録のまとめ方_20261029.md) | **Notion に残す議事録はすべてこの型で仕上げてから載せる**（結論・決定・ToDo表が先頭、話者は実名、全文はリンク、A4 1枚目安）。残す前の了承・チャットは3行要約＋宿題は維持 |
| [`53_4ツール共通再開`](53_Codex_Claude_Cursor共通再開_20261101.md) | **「Codexなどの作業の続きをして」でClaude Code／Cursorが再開するための人向け入口・両宛て共有・Slack／Todoistの使い分け** |
| [`61_業務設計・実装・運用管理の役割分担`](61_AI社員の業務設計・実装・運用管理の役割分担_20261121.md) | **AI 社員を作る・直す時の進め方：FlowForge＝業務設計／ChatGPT＝設計・仕様／BL＝棚卸し・進行管理／Claude Code＝実装／Jarvis ダッシュボード＝運用実績。FlowForge の編集の決まり（`patch_flowforge_flow` 優先・了承後・`verified=true`）** |
| [`62_ボット共通ルール入口`](62_ボット共通ルール入口_20261123.md) | **新しいボットが最初に読む入口（毎回読む10項目＋正本リンク）** |
| [`55_Banto_Grok連携運用`](55_Banto_Grok連携運用_20261107.md) | **番頭さん（Banto/Muse）とホーク（Grok）の役割、監視・完了確認・権限境界、試験運用中の未確定事項** |
| [`57_ニュース配信_Webhook評価`](57_ニュース配信_Webhook評価_20261108.md) | **本人向けニュース4本：Bantoが#report Webhook投稿、Jarvisが👍👎回収** |
| [`54_Grok×番頭相互補完`](54_Grok_番頭Banto相互補完_20261107.md) | **Grok Bot＝攻め／番頭（Banto・Muse）＝守り・先回り。指摘〜解決確認・省コスト・権限。Jarvisは二重巡回しない** |
| [`48_読まなくてよいMD一覧`](48_読まなくてよいMD一覧_20261024.md) | 名指し時だけ開く MD（AI 使用量の節約） |
| 家ルール例 | [`config/claude_code_home_CLAUDE.example.md`](../../config/claude_code_home_CLAUDE.example.md) → `~/.claude/CLAUDE.md` |

## 開発プロジェクトの経緯とメモリ（非公開・2026-11-19）

Claudeプロジェクト「AIエージェントチーム開発/運用」と同じ前提で、同名の Orca 作業スペースなどから動くための入口。
フォルダ単位ではなく**チーム全体の実装**を扱う：運用中の社員のトラブル対応、社員フォルダはあるが運用に入っていない社員（registry の `候補`／`設計中`）の具体化。

**目的（プロジェクト設定の写し・2026-11-19）**: 1フォルダ1社員で松野の作業自動化が自立的にうまく回る仕組みを作る。トリガー／権限／作業内容／報告がそれぞれの社員でしっかりまとまり、ATB（Agent Team Builder）・作業フロー・ジャービスダッシュボードで視える形になっていて、Slackレポートで状況把握・判断が瞬時にでき、必要な対応はSlackに頼めば作った仕組みの中でうまく対処してくれる。さらにGrok botとも連携するところを上手に連携し、品質確認で冗長性が必要なところはエージェントも同機能を持ち、お互い評価し高め合う状態になっている。

- 経緯・決定・進行中の案件は非公開メモリにある。作業前に読む
  - 場所: `docs/AIエージェントチーム/memory/`（入口 `MEMORY.md`）
  - `.gitignore` 対象。Mac の `~/git-repos` と非公開リポ `project-GE-private` にだけある（Drive にも写さない）
  - 記録が食い違うときは日付の新しい方を優先し、実ファイル（registry・社員 `CLAUDE.md`・scripts）で確かめる
- 新しく分かった決定・方針は同じ `memory/` に1件1ファイルで足し、`MEMORY.md` に1行の案内を書く
- メモリの中身（取引先名・金額・個人情報）を公開側の MD・PR 本文・Slack に書き写さない

## 作業開始前（必須・短い）

1. 当該社員の **`TASK.md`** に依頼・完了条件・executor を書く（`status=running`）
2. Todoist／run 単位で **ロック取得**（失敗＝実行中 → 止める）:

```bash
cd ~/git-repos && ~/selenium_env/venv/bin/python scripts/jarvis_agent_run_lock.py acquire \
  --task-id … --agent-id NNN --executor cursor --folder 'docs/AIエージェントチーム/…'
```

3. 終了後 `release` ＋ `TASK.md` を done／failed。Cursor ルール: `.cursor/rules/jarvis-agent-run-lock.mdc`

## 状態識別（必須）

1. **フォルダ名（`NNN_名前`）は状態で変えない**
2. `agents_registry.yaml` の `status` を正とする（`候補` / `設計中` / `運用確認` / `運用` / `停止`）
3. **status を変えるときは先にチャットで提案**し、松野了承後にだけ registry／マーカーを更新する（無言で `運用` に上げない）
4. 社員フォルダ: `設計中` 以上ならマーカー  
   `00_🔵設計中.md` / `00_🟡運用確認.md` / `00_🟢運用.md` / `00_⛔停止.md`  
   （**ファイル名が印。中を開かなくてよい**。`候補`はマーカーなし）
5. 部門直下: **`00_状態ボード.md`** を同期（配下一覧）
6. README 見出しに `【運用】` 等の接頭辞
7. 了承後の反映は手書きより **同期スクリプト**:

```bash
cd ~/git-repos && ~/selenium_env/venv/bin/python scripts/jarvis_agent_team_status_sync.py
```

Drive `★AIエージェントチーム` へも写す（`--no-drive` でオフ可）。社員フォルダの文書・`output/`（成果物）と `91_ルール/`（家ルール・Cursor ルール・config）は `jarvis_agent_team_drive_sync.py` が写す（status_sync の最後＋毎日 6:10 launchd。片方向・Drive で直しても git に戻らない）。Drive 直下の `CLAUDE.md`／`AGENTS.md` だけは、このファイルの写しではなく Drive 用の入口 [`_drive/`](_drive/CLAUDE.md)（「正本・プログラムは `~/git-repos`」と案内し、このファイルを取り込む）を写す。詳細: [`22_`](22_運用状態の識別_20261011.md)

## 新規社員を切ったあと（チェック）

- [ ] registry に id / path / status を追加  
- [ ] `00_チーム索引.md` に1行  
- [ ] `config/agent_team_permissions.yaml` に `can_do`（サイトPWを渡すなら `site_logins` も）  
- [ ] 社員の `CLAUDE.md` §2 合図／§3 実行権限／§4 報告・必要なら `.env.example` を埋める  
- [ ] **`flow.md` 初回叩き台**（文字1行・Mermaid・ステップ一覧・やらないこと。`_template/flow.md` 型。空禁止。FlowForge URL は後追い可）  
- [ ] Builder 組織図に追加  
- [ ] `jarvis_agent_team_status_sync.py` を実行（マーカー＋部門ボード＋権限・運用投影）  
- [ ] `agentTeam.json` を commit／push（ダッシュ「権限」「運用」タブ）  
- [ ] `AGENTS.md` は日付同期のみ  

詳細: [`06_社員の作り方_二段階_20261009.md`](06_社員の作り方_二段階_20261009.md)「新規作成時の必須」

## 報告・対外

神大家の個別有償業務は、共通ルール49のR9に従い、事前見積もり・承認と作業中の実績／残工数／超過見通しを記録する。Miss Lemon・Jarvis・FRIDAY・Codex共通。工数表示は本人用JARVIS Dashboardの内部管理であり、運営へ請求する新規開発案件ではない。

Slack `#report` / `#consult` / `#ops`。外に出す・金・削除は人の了承。詳細は各社員 `CLAUDE.md`。  
完了報告は `#ai-hub` に「変更内容／テスト結果／未完了／次の推奨」。番頭さん（Banto／Muse）のスレ返信は松野さんの FB と同じ扱いで拾う。投稿の重複・誤判定の防止は [`56_`](./56_Slack運用ルール追補_番頭さん参加と投稿品質_20261107.md)。

番頭さん（Banto/Muse）とホーク（Grok）の連携では、[`55_Banto_Grok連携運用`](55_Banto_Grok連携運用_20261107.md)を参照する。Slackの設計共有だけで新しい自動化・権限を有効化した扱いにしない。Todoistへのホークの直接書き込みは11/7に個別承認された範囲として記録し、他の外部操作・権限拡大へ一般化しない。

## 他ツール共有（必須）

Codexからのローカル引き継ぎは `/Users/matsunomasaharu2/git-repos/agent-handoff/`。Claude Codeは `to_MissLemon/`、Cursorは `to_Jarvis/` のpendingを起動・再開時に確認する。松野さんの「Codexなどの作業の続きをして」は、現在の案件に一致するメモ、正本、実ファイルを確認して続行する合図。両ツールで把握が必要な案件は、同じ `handoff_group_id` の短い入口を両宛てに置き、詳細は案件の正本だけを更新する。別worktreeでも同じ絶対パスを参照。手順・権限・正本の扱いは [51_ローカル受け渡し](51_ローカル受け渡し_20261026.md)、人向け入口は [53_共通再開](53_Codex_Claude_Cursor共通再開_20261101.md)。

新機能・運用変更は **チャットだけで終わらせない**。担当社員 `CLAUDE.md`・`docs/運用コマンド一覧.md`・必要なら Grok paste／B1 を同じ作業で更新する。  
Cursor／Jarvis の正本ルール: `.cursor/rules/jarvis-multi-agent-share.mdc`。  
**FRIDAY／Jarvis／AI社員の書き出し1節（どの ch・末尾型）**: [`38_Slack書き出し_FRIDAY_Jarvis_20261018.md`](./38_Slack書き出し_FRIDAY_Jarvis_20261018.md)  
**スマホレイアウト（草案・行長／空行／過去見栄えFB）**: [`41_Slackスマホレイアウト_草案_20261022.md`](./41_Slackスマホレイアウト_草案_20261022.md)  
**Slack 運用追補（番頭さん参加・共通運用改訂・重複／誤判定の防止）**: [`56_Slack運用ルール追補_番頭さん参加と投稿品質_20261107.md`](./56_Slack運用ルール追補_番頭さん参加と投稿品質_20261107.md)

### Slack 書き出し（必須・2026-10-18）

**最初の1行に「社員番号＋短い役割語」の両方**を入れる。

- 番号だけ → 何の作業か分からない（不可）
- 役割語だけ → 番号で探せない（不可）
- 「係」は不要。正式名を短く要約してよい（例: 返信案内下書き係 → **返信案内下書き**）

| 用途 | 例 |
|---|---|
| 報告 | `【報告】211 返信案内下書き・朝便` ／ `【111 パートナー連絡整理・昼】` |
| 相談 | `【相談】211 返信案内下書き` |
| ops | `【ops】211 返信案内下書き・朝便` |
| Webhook 表示名 | `211 返信案内下書き` |

| ch | いつ |
|---|---|
| `#report` | 完了・定型・生存確認 |
| `#consult` | 要判断。**末尾に「次の担当」3行必須**（[`36_`](./36_Slack_consult手渡し_次の担当_20261018.md)） |
| `#ops` | 障害・失敗・枠切れ **＋是正結果（振り返り用）**。投稿は **Webhook** 本線（通知）。未設定時は MCP 可 |

`#consult` 末尾型:

```
次: Grokで続行 | Jarvisに依頼 | Claude Codeで続行 | 人判断のみ
担当メモ: …
橋渡し: 松野が了承したら、上記の担当へ一声（当面は人が橋）
```

Cursor ルール: `.cursor/rules/jarvis-agent-team-slack-report.mdc` · 読取: `jarvis-slack-hub-watch.mdc`


## 作業フローの確認から実装指示（2026-11-15・本人依頼）

作業フローの設計/確認/社員具体化を依頼された時は、[workflow-review/README.md](workflow-review/README.md) と同フォルダのひな形を使う。各工程の主体・実行者、保存/表示/報告、判断ログの保存と実行前取得、今回/次回の戻り矢印を明示し、同じ工程から実装TASKを作る。既存社員・既存資産を再利用し、FlowForge経由を必須にしない。Claude側の入口は `.claude/rules/matsuno-workflow-review.md`。単発の説明やコード修正へ一式を強制しない。
