# Cloud Jarvis → Local 提案（312 GAS · 2026-10-22）

PR [#118](https://github.com/m19mhrts83-cyber/project-GE/pull/118) の **Agentic Security Review（MEDIUM）**、FRIDAY 引き継ぎ（`#ai-hub`）、および前後の相談（Codex 家訓・Claude/GAS 切り分け）を踏まえた **提案のみ**。実装・GAS 適用は **Local Jarvis（admin）**。

---

## Security Review の要点（受けた指摘）

`poll()` が「`DIGEST_MARKER` を含む最新メッセージ」を無条件に 312 ダイジェストとみなす。  
`#consult` に書ける人なら偽ダイジェスト→番号返信で Todoist 起票でき、コメントが **`【FRIDAY】` 固定**のため FRIDAY 名義の偽起票になる。

---

## 提案（優先順）

### P0 — 適用前に入れる（推奨）

| # | 提案 | 理由 |
|---|---|---|
| **A** | ダイジェストは **Webhook／Bot 投稿だけ**採用。`bot_id` 必須、または `DIGEST_BOT_USER_IDS`／アプリ ID の allowlist | 偽ダイジェスト封じの本命。人間のコピペ誘導を無効化 |
| **B** | Todoist コメント接頭辞を **`【GAS-312】`**（または `【312 cloud】`）にし、**`【FRIDAY】` 固定をやめる** | なりすまし指摘への直接対応。実 FRIDAY 実行とクラウド常駐をログで区別できる |
| **C** | 起票タイトルに由来印を残す（例: `[312][gas]`）／description に `digest_ts` | 監査・誤起票の追跡 |

※ `#consult` がほぼ松野のみならリスクは低いが、**A+B はコストが小さく先に入れる価値が高い**。

### P1 — 312 稼働確認のあと

| # | 提案 | 理由 |
|---|---|---|
| **D** | **313 は別関数／別マーカー**（`閉じてよければ` 等）。番号空間は **スレ単位**で 312 と分離 | FRIDAY 引き継ぎどおり。誤 close 防止 |
| **E** | 313 は **オーナー確認列＋明示「閉じて N」のみ**。確認のみ自動 close は **やらない**（既存ルール） | 誤完了の再発防止（#1/#2 再開の教訓） |
| **F** | close コメントも `【GAS-313】`（FRIDAY 固定にしない） | B と同型 |

### P2 — 運用・入口（会話の続き）

| # | 提案 | 理由 |
|---|---|---|
| **G** | admin で既存 GAS に `.gs` 貼付→プロパティ4つ→`poll`→5分トリガー（Cloud 不可のため Local） | `#ai-hub` 既報 |
| **H** | `config/codex_home_AGENTS.example.md` → Mac `~/.codex/AGENTS.md` | Codex 家訓（2番・賛成済） |
| **I** | Claude API は本線に載せない。曖昧返信の後段のみ（`42_`） | Dify/Claude 相談の整理 |

### やらない／後回し

- 毎回 Claude で番号解釈（遅延・課金・誤解釈）
- 313 を 312 と同ダイジェスト文字列で混在起動
- GHA 新規 workflow への再挑戦（登録されない前提のまま）

---

## Local への具体化チェックリスト（短い）

1. PR #118 を拉取／マージ方針確認  
2. **A+B（+C）を `.gs` に入れてから** admin GAS に貼る  
3. プロパティ: 既存4つ ＋ 任意 `DIGEST_BOT_USER_IDS`  
4. `poll` 承認・5分トリガー  
5. 偽ダイジェスト試験（人がマーカー付き投稿→**起票されない**こと）  
6. 正規ダイジェストで `起票して 9` → 番号なし応答  
7. 実番号1件で Todoist に `[312]` が付き、コメントが `【GAS-312】` であること  
8. 問題なければ 313（D+E+F）を追加  

---

## 参照

- Security Review: PR #118 review comment on `gas_todoist_312_slack_ingest.gs`  
- `#ai-hub` 312→Jarvis 引き継ぎ / Cloud 診断投稿  
- `docs/.../42_GASクラウド常駐_Claudeとの切り分け_20261022.md`  
- `docs/.../43_エージェント入口_AGENTS層_解説_20261022.md`  
- `config/codex_home_AGENTS.example.md`
