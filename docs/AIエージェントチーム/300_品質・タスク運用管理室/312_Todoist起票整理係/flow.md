# フロー — Todoist起票整理係（312）

第2段階の作業フロー正本（会話磨き 2026-10-21）。  
作り方: [`06_社員の作り方_二段階_20261009.md`](../../06_社員の作り方_二段階_20261009.md)

- FlowForge（閲覧／編集）: [flow_M8SvKC1IDTDi496Vw-DgGjpD](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_M8SvKC1IDTDi496Vw-DgGjpD)
- Flowforge 入口: https://flowforge-259747770348.asia-northeast1.run.app/
- ビルダー共有: https://agent-team-builder-teal.vercel.app/s/uksxiDIzE1AEckKH
- 更新: 2026-10-21（運用格上げタイミング確定・PROGRESS正本）

## いまの結論（文字1行）

材料できたとき即スキャン → 塩梅（L0静かに／L1ダイジェスト見るだけ／L2個別採用・見送り）→ Slack `#consult` → **採用時に Todoist へ create**。ホーク・AI同士の直入れは L0 で維持。**Todoist起票の本線は312**。close は 313。

## Todoistへの登録動線（出口・必読）

タスク正本は **Todoist**。312まわりの **登録経路は次の3本**（どれも最終的に Todoist に載る）。

| 経路 | いつ | 人操作 | 実行 |
|---|---|---|---|
| **① L2採用 → create** | SB／111／GenMail／会話など、塩梅で L2 になった候補 | `#consult` で **採用**（当面はチャット了承可） | `create-task` ＋コメント（312） |
| **② L0 直登録** | ホーク／AI同士の `todoist_tasks` apply。116で既に **Todoist追加**済み | なし（後からラベル・二重整理のみ） | 既に Todoist 上。312は整理のみ |
| **③ 116 Todoist追加** | メール要対応カード | ボタン **Todoist追加** | Dashboard／116レール（共有）。結果は L0 扱い |

- **L1（ダイジェスト）からは create しない**（見るだけ。必要なら L2 化→①）
- **111は create しない**。宿題シグナルを312へ渡すだけ
- close／完了仕分けは **313**（登録動線の外）

```text
[材料] → スキャン → 塩梅
   ├─ L0 ──(整理)──→ Todoist（②・③）
   ├─ L1 → #consult（見るだけ）──→ （createしない）
   └─ L2 → #consult 採用 ──→ create-task ──→ Todoist（①）
```

## 確定（2026-10-21）

| # | 内容 |
|---|---|
| 1 | **投稿先**: 即時の **L1／L2 とも Slack `#consult`**（定期ダイジェストも同 ch） |
| 2 | **AI同士の完了**: 312は「完了疑いをダイジェストに載せる」まで。**実際の close は 313＋オーナー確認二段** |
| 3 | **起票本線は312**。111は取込・宿題渡しのみ（再検討で111側を要すれば変更） |
| 4 | **GenMail要対応**も312ソースに含める（当面チャット提案→将来 L1/L2） |
| 5 | **チャット残**: Cursor/Planはルールで L1候補化。**ノイズ抑制**（受け入れ済・未完了・最大5・無言create禁止）。定期transcriptは1.5b後続 |
| 6 | **運用格上げ**: A今ルール／B翌朝ソフト／C定時=初回apply翌日or10/28／D=1.5bはC安定1週後。詳細は [`PROGRESS.md`](./PROGRESS.md) |

## 合流の考え方

ソースは複数だが、**Todoist登録の出口は上表の3本**。提案の見せ方は塩梅仕分け → `#consult`（L1/L2）または L0。定期は取りこぼし保険。全部を個別ボタンにしない。

## ソース（入口）

| ID | ソース | 扱い |
|---|---|---|
| S-hawk | ホーク／部長 `todoist_tasks` apply | **② L0 直 create 維持** |
| S-box | JarvisBox `10_inbox_from_grok/` | 整理対象。poll 後すぐスキャン → ①寄り |
| S-mail | 116 メール `#consult` | **③ Todoist追加**（返信／見送りも同カード） |
| S-sb | SecondBrain／会議 Action（714材料） | 材料即 → L1 or L2 → **①** |
| S-111 | パートナー宿題シグナル | 111は渡すだけ。312が L1/L2 → **①** |
| S-genmail | GenMail要対応 | 312ソース。当面チャット提案 → 将来 L1/L2 → **①** |
| S-slack | Slack `#consult`／`#ai-hub` | 定期・即時のスキャン対象 |
| S-chat | Cursor／Planの残タスク（ルール拾い） | **L1候補のみ**（無言create禁止）。了承後 → **①**。正本: `jarvis-chat-open-tasks-312.mdc` |
| S-gencode | GenCode残（当面） | `#ai-hub`／Drive inbox 経由。チャット直スクレイプしない |
| S-man | 「起票整理して」「認定して」 | いつでも → **①** |

## いい塩梅（3段）

| 段 | 人の操作 | 内容 |
|---|---|---|
| **L0** | なし | ホーク／AI直入れ、116で既に Todoist追加したもの。後からラベル・二重整理可 |
| **L1** | **見るだけ**（一括 create しない） | ダイジェスト1通。気になるときだけ一言／L2化。列挙最大7 |
| **L2** | **採用／見送り**（個別） | 迷い・金・対外・レーン不足・二重疑い。1回最大3件 |

弱いシグナル（weak のみ）は L1 に載せない／参考行のみ。815 は起票提案対象外。

### ボタン文言

| ソース | ボタン |
|---|---|
| 純タスク提案 | **採用／見送り** |
| 116 メール | **返信する／見送り／Todoist追加**（返信がありうる） |

## フロー図

```mermaid
flowchart TD
  Box["JarvisBox"] --> Immediate["材料できたとき即"]
  Partner["111 宿題渡し"] --> Immediate
  SB["SB・会議・GenMail"] --> Immediate
  SlackCh["Slack・チャット"] --> Immediate
  Immediate --> Rank{"塩梅仕分け"}
  Periodic["定期・取りこぼし保険"] --> Rank
  Hawk["ホーク・AI同士"] -->|② L0直| Td[(Todoist 登録)]
  Mail["116 メール"] -->|③ Todoist追加| Td
  Rank -->|L0 整理| Td
  Rank -->|L1| Digest["#consult ダイジェスト<br/>createしない"]
  Rank -->|L2| Card["#consult 採用/見送り"]
  Card -->|採用 ①| Create["create-task + コメント"]
  Card -->|見送り| Skip["再提案抑制"]
  Create --> Td
  Td --> Done313["完了仕分けは313<br/>登録ではない"]
  Create -->|失敗| Ops["#ops"]
```

## ステップ一覧

| # | 内容 | 方法 | 人/AI | ツール例 |
|---|---|---|---|---|
| 1a | **即時**: 材料検出（Box／SB／111／会話） | イベント | AI | inbox poll／sb_propose／シグナル |
| 1b | **定期**: 横断取りこぼしスキャン | 時間・相乗り | AI | 将来 launchd／GHA。当面は人依頼・パートナー確認ついで |
| 1c | **人**: 認定して／`/todoist` | 依頼 | AI | Cursor |
| 2 | 二重起票・レーン／ラベル点検（properties＝物件＋PM） | CLI／API | AI | `jarvis_todoist_api.py` |
| 3 | 塩梅仕分け L0／L1／L2 | ルール | AI | signals YAML |
| 4 | L1 ダイジェスト or L2 カードを `#consult` | Slack | AI | Webhook／Bot（116同型を将来） |
| 5 | **① Todoist登録**: L2 採用 → `create-task`＋コメント。見送り → 抑制 | ボタン／一言 | **人**＋AI | Todoist API |
| 5b | **②③**: L0整理／116 Todoist追加結果のラベル・二重 | CLI／Dashboard | AI／人 | 既に Todoist 上 |
| 6 | 完了疑いは L1 ダイジェスト等に列挙のみ | CLI／Slack | AI | 312。**close はしない** |
| 7 | 完了仕分け → オーナー確認 → 了承後 close | — | **313**＋人 | `/todoist-batch`・二段完了 |

**人が確かめる印**: ステップ5（L2採用／見送り）。L1は把握のみ。116の返信了承は116。金・対外・削除。  
**やらない**: 全件個別ボタン、L1一括 create、815自動起票、了承なし対外送信、312による close、秘密の再掲。

## 係の境界

| 係 | 役割 |
|---|---|
| ホーク／AI | Todoist 直登録（L0）。完了もコメントで残す |
| JarvisBox poll | 材料取込。認定・整理は312 |
| 116 | メール判断（返信UI）。Todoist追加＝共有レール |
| 111 | 取込・差分。宿題は即312へ。**create しない**（111側は再検討で要すれば変更） |
| 714 | 会議／Notion残し。Action → 312 |
| **312** | **Todoist起票の本線**（①）。整理・塩梅・認定・ラベル／二重。完了疑いはダイジェスト列挙まで |
| **313** | 完了仕分け・確認のみ close（＋オーナー確認二段）。**新規登録はしない** |

## FlowForge 作り込みメモ

- [x] 即時トリガー（ソース別）→ 塩梅 → `#consult` 合流（2026-10-21・キャンバス反映済）
- [x] L0（ホーク）は create 分岐で人待ちなし（L0ノード＝ラベル・二重のみ）
- [ ] 停止条件（env／disabled）をガード（コード／運用側）
- [x] 作成後: registry と本ファイル先頭リンクを同期 → `jarvis_agent_team_status_sync.py`
- [ ] 共有URLを `config/flowforge_share_urls.json` に追記（要確認）

## 手順メモ（実装本線・いま動くもの）

```bash
# 人依頼・候補（チャット／将来 Slack）
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_todoist_sb_propose.py --latest
# 了承後（当面チャット了承。Slack 採用ボタンは後続）
~/selenium_env/venv/bin/python scripts/jarvis_todoist_sb_propose.py --apply --select 1

# 了承後 create（手動・Jarvis）
~/selenium_env/venv/bin/python scripts/jarvis_todoist_api.py create-task \
  --lane properties --title '[GrandoleI][ミニテック] …' \
  --label GrandoleI,ミニテック \
  --comment '【Jarvis】
サマリ: …
アウトプット:
- [出典](https://…)'

# JarvisBox
~/selenium_env/venv/bin/python scripts/jarvis_bucho_inbox_poll.py
# 116 メール（別UI・共有レール）
~/selenium_env/venv/bin/python scripts/jarvis_mail_action_slack_post.py --from-triage --dry-run
```

**未実装（フロー正・コードは後続）**: L1/L2 の Slack カード本線、材料即時の自動投稿、定期取りこぼしジョブ。当面は CLI＋チャット了承＋116既存ボタンで回す。
