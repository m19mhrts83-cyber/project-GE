# 資料作成ループ（Nody /slides）：エージェントの手順

**方針**：アプリは「選ぶ・直す・採否」の画面とログだけ。案づくりと振り返りのまとめは、松野さんが使っているエージェント（Claude Code／Miss Lemon）が行う。アプリに従量課金のAI（API）は載せない。

## 1回の流れ

| # | 誰が | 何を | 合図 |
|---|---|---|---|
| ① | エージェント | `state` で基準を読み、3案を作って `put`（stage=plan） | 松野さん「資料の案を作って（題材：◯◯）」 |
| ② | 松野さん | Nody `/slides` で案を1つ選び、観点を選ぶ。外した案に理由タグ（任意） | — |
| ③ | エージェント | `state` で選んだ内容を読み、NotebookLM用ソースMarkdownとスライド生成プロンプトを作る | 松野さん「選んだ内容で作って」 |
| ④ | 松野さん | ソース・プロンプト・スライドをいつも通り直す | — |
| ⑤ | エージェント | 直す前・後を `log-fix` で記録 → 直しを概念にまとめた反映案を `put`（stage=review） | 松野さん「直した内容で振り返りを作って」 |
| ⑥ | 松野さん | `/slides` で反映案を 採用／今回だけ／違う | — |
| ⑦ | 次回の① | 採用した基準だけを使う | — |

## コマンド

作業場所は `~/git-repos`。環境変数は `.env.jarvis_private`（値は表示しない）。

```bash
set -a; . ./.env.jarvis_private; set +a
S=apps/loopware/scripts/slides_loop.py
python $S state                                   # いまのデッキ・選んだ内容・資料の基準
python $S put --file /tmp/deck.json --dry-run     # 形を確かめる
python $S put --file /tmp/deck.json               # Nody に置く（前のデッキは置き換わる。ログは残る）
python $S log-fix --deck 2026-11-dx-gojokai --before v1.md --after v2.md --subject "ソースMarkdown"
python $S export --deck 2026-11-dx-gojokai        # このデッキの判断ログ
```

デッキの形は `docs/slides_deck_sample.json`、案と反映案の決まりは `prompts/slides_proposal.md`。

## 守ること
- 反映案は**仮説**。採否は松野さんが Nody で押したものだけ（チャットでの「いいよ」は、押してもらうよう頼む）。
- 「今回だけ」「違う」を同じ×にしない。理由タグが無いものは理由不明のまま。
- 直しの記録は打ち間違い（typo）と意図のある直し（intent）を分ける。
- 10件・30件と溜まってから基準を見直す。1回で決めつけない。

## データ
- いまのデッキ：Supabase `sync_meta`（key=`loopware_slides`）
- 判断：`owner_decisions`（surface=`slide_plan`／`slide_fix`／`slide_rule`）。契約は `lib/decisionContract.ts`

## 費用
エージェントの利用枠の中。Nody 側に AI 呼び出しは無い。
