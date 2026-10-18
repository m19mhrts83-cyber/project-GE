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

Drive `★AIエージェントチーム` へも写す（`--no-drive` でオフ可）。詳細: [`22_`](22_運用状態の識別_20261011.md)

## 新規社員を切ったあと（チェック）

- [ ] registry に id / path / status を追加  
- [ ] `00_チーム索引.md` に1行  
- [ ] `config/agent_team_permissions.yaml` に `can_do`（サイトPWを渡すなら `site_logins` も）  
- [ ] 社員の `CLAUDE.md` §2 合図／§3 実行権限／§4 報告・必要なら `.env.example` を埋める  
- [ ] `jarvis_agent_team_status_sync.py` を実行（マーカー＋部門ボード＋権限・運用投影）  
- [ ] `agentTeam.json` を commit／push（ダッシュ「権限」「運用」タブ）  
- [ ] `AGENTS.md` は日付同期のみ  

## 報告・対外

Slack `#report` / `#consult` / `#ops`。外に出す・金・削除は人の了承。詳細は各社員 `CLAUDE.md`。  
**FRIDAY／Jarvis／AI社員の書き出し1節（どの ch・末尾型）**: [`38_Slack書き出し_FRIDAY_Jarvis_20261018.md`](./38_Slack書き出し_FRIDAY_Jarvis_20261018.md)

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
| `#ops` | 障害・失敗・枠切れ |

`#consult` 末尾型:

```
次: Grokで続行 | Jarvisに依頼 | 人判断のみ
担当メモ: …
橋渡し: 松野が了承したら、上記の担当へ一声（当面は人が橋）
```

Cursor ルール: `.cursor/rules/jarvis-agent-team-slack-report.mdc` · 読取: `jarvis-slack-hub-watch.mdc`
