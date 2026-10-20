# Todoist起票整理係（312）

**作業を始めたら、まず [`PROGRESS.md`](./PROGRESS.md) を読む**（続き・Phase 状態がここにある）。

**タスク認定・起票整理の入口**。宿題・要対応を塩梅つきで整え、了承後（または L0）に Todoist へ載せる。  
**完了仕分け・確認のみクローズ**は [`313_完了候補確認係`](../313_完了候補確認係/CLAUDE.md)。  
作業フロー正本: [`flow.md`](./flow.md)  
伴走 Phase1: [`docs/phase1-l1-digest.md`](./docs/phase1-l1-digest.md)

## AIオートメーション（作業フロー）

- **FlowForge（開く）**: [flow_M8SvKC1IDTDi496Vw-DgGjpD](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_M8SvKC1IDTDi496Vw-DgGjpD)
- 一覧・進捗: [`15_FlowForge全体系_進捗_20261010.md`](../../15_FlowForge全体系_進捗_20261010.md)
- 設計の流れ図: [`flow.md`](./flow.md)
- Cursor コマンド: `/todoist`（起票寄り）／掃除は `/todoist-batch`（313）
- Cursor ルール: `jarvis-todoist-owner-confirm.mdc`／JarvisBox: `jarvis-grok-jarvisbox-fork.mdc`
- メール共有レール: [`116_メール要対応係`](../../100_連絡・物件動向把握室/116_メール要対応係/CLAUDE.md)

## 1. 役割

- **やること**
  - **Todoist起票の本線**（登録動線は [`flow.md`](./flow.md)「Todoistへの登録動線」①②③）
  - **材料ができたとき即**スキャン（SB／会議・111宿題・GenMail・JarvisBox・会話・Slack）
  - いい塩梅仕分け: **L0**静かに／**L1**ダイジェスト（見るだけ）／**L2**個別採用・見送り
  - レーン／ラベル／二重起票の点検・整理（properties＝物件＋PM）
  - **①** L2 採用後（またはチャット了承後）の `create-task` ＋コメント
  - **②③** AI同士・ホーク直入れ／116 Todoist追加済のラベル整理。**完了疑いはダイジェストに載せるまで**（close しない）
  - 定期は取りこぼし保険（横断ダイジェスト）
- **やらないこと**
  - 全件を個別ボタン化、L1一括 create
  - 了承なしの対外送信・秘密の再掲
  - **完了 close**（→ **313＋オーナー確認二段**）
  - 815 からの自動起票提案

### 受け渡し

| 係 | 関係 |
|---|---|
| 111 | 取込まで。宿題は即312へ。**create しない** |
| 116 | メール判断UI。**③ Todoist追加**＝共有レール |
| 714 | 会議材料。Action → 312 |
| GenMail | 312ソース（当面チャット提案） |
| ホーク／JarvisBox | **② L0** 直 create 可。Box は整理対象 |
| 313 | 完了側（登録しない） |

## 2. 動き出す合図

- [x] 人が頼む（`/todoist`・「起票整理して」「認定して」「起票して」）
- [x] 何かが届いたら（材料できたとき即: SB／111／JarvisBox／hawk create）
- [x] 時間（取りこぼし保険・当面は相乗り。専用定時は後続）
- [ ] 変化・失敗を見回ったら（二重疑い・API失敗 → `#ops`）

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| チャット・検索 | ○ | 候補・認定 |
| 外部連携（API/MCP） | ○ | Todoist／Slack |
| CLI | ○ | `jarvis_todoist_api.py`／`jarvis_todoist_sb_propose.py`／inbox poll |
| ブラウザ | △ | 画面照合 |
| 画面操作 | × | 送信・課金は人 |

**人が確かめる**: L2 採用／見送り、116の返信了承、金・対外・削除。L1は把握のみ。L0は操作なし。

### いい塩梅（要約）

| 段 | 操作 |
|---|---|
| L0 | なし（ホーク／AI直入れ・116 Todoist追加済） |
| L1 | ダイジェストを見るだけ（一括 create しない） |
| L2 | 採用／見送り（最大3件/回）。投稿先 `#consult` |

## 4. コメント必須

```
【Jarvis】
サマリ: （出典・期限・ボール・1〜3行）
アウトプット:
- [表示名](https://…)
```

| とき | 必須？ |
|---|---|
| create（了承後） | **必須** |
| レーン／ラベル直し | サマリ1行以上 |
| L1 候補のみ | Todoist コメント不要 |
| 秘密 | **禁止** |

書き手: Jarvis=`【Jarvis】`／FRIDAY=`【FRIDAY】`／ホーク=`【ホーク】`

## 5. 報告先

| 種別 | 行き先 |
|---|---|
| **即時・定期の L1／L2**（確定） | Slack **`#consult`** のみ |
| 完了疑いの列挙 | L1 ダイジェスト等（`#consult`）。close は 313 |
| 起票反映・定型 | `#report`（短く。省略可） |
| API失敗・二重疑い | `#ops` |

書き出し: `【報告】312 Todoist起票整理`／`【相談】312 Todoist起票整理`  
`#consult` 末尾（L2・要判断時）: `次: …` ＋ `担当メモ` ＋ `橋渡し`（[`38_`](../../38_Slack書き出し_FRIDAY_Jarvis_20261018.md)）

## 6. 成果物の置き場

- このフォルダ: `logs/`／`flow.md`
- 外部正本: Todoist／JarvisBox／`config/todoist_projects.yaml`／`config/todoist_extract_signals.yaml`
- メール: triage＋116

## 7. 作業手順（チェックリスト）

1. ソースを読む（即時 or 定期 or 人依頼）
2. 二重・レーン／ラベル点検
3. L0／L1／L2 に仕分け
4. L1→`#consult` ダイジェスト／L2→採用・見送りカード（当面チャット可）
5. 採用・了承後だけ `create-task` ＋コメント
6. 完了疑いは列挙して 313 へ（close しない）

### CLI

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_todoist_sb_propose.py --latest
~/selenium_env/venv/bin/python scripts/jarvis_todoist_api.py create-task \
  --lane properties --title '[GrandoleI][ミニテック] …' \
  --label GrandoleI,ミニテック \
  --comment '【Jarvis】
サマリ: …
アウトプット:
- [出典](https://…)'
```

## 8. 改善ログ

| 日付 | 変更 |
|---|---|
| 2026-10-09 | ビルダー構成に合わせ候補フォルダ作成（ID 312） |
| 2026-10-19 | コメント必須・`/todoist`・CLI 具体化 |
| 2026-10-19 | 書き手識別 `【Jarvis】` 必須 |
| 2026-10-21 | flow 本線化。認定入口・いい塩梅3段・材料即時・JarvisBox／AI同士 L0・116ボタン区別・closeは313 |
| 2026-10-21 | 確定: L1/L2投稿先=`#consult`／AI完了疑いは312列挙のみ・closeは313＋オーナー確認二段 |
| 2026-10-21 | C確定: 起票本線=312／111は渡しのみ／GenMailをソースに。登録動線①②③を正本に明示 |
| 2026-10-21 | Phase1: `jarvis_todoist_312_digest.py`（L1→#consult→了承後①create） |
| 2026-10-21 | Phase1.5a: チャット残→L1候補ルール `jarvis-chat-open-tasks-312.mdc`（ノイズ抑制・無言create禁止） |
| 2026-10-21 | Phase1＋1.5a **意図OK**（松野）。通しapplyは運用時任意 |
| 2026-10-21 | 運用格上げ確定: A今／B 10-22ソフト／C 初回apply翌日or10-28／D 1.5bはC安定1週後（PROGRESS正本） |
