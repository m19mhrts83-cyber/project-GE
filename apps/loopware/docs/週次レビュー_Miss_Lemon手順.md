# Nody 週次レビュー：Miss Lemon の手順

**方針**: ログを溜めるまではアプリ、そこからの判断（仮説づくり・了承・反映）は松野さんが使っているエージェントツール（Miss Lemon＝Claude）で行う。アプリに従量課金のAI（API）は載せない。

## 流れ
1. **毎日（見た日だけ）**: アプリで仕分け・コメント。ログが溜まる。毎日見なくてよい。
2. **月曜朝**: GitHub Actions が先週のログを集計し、Slack `#consult` に「確認をお願い」を出す（ログが1件でもあれば。7日分そろっていなくてよい）。
3. **松野さんが「Nodyの週次レビューをして」と言う** → Miss Lemon が下の手順で進める。
4. **Miss Lemon**: その週のログから「基準を更新する仮説」をまとめて提案する。
5. **松野さん**: 仮説を1つずつ 了承／見送り（理由つき）。
6. **Miss Lemon**: 了承したものだけ基準として追記し、週を「確認済み」にする → 翌朝 Slack に「確認済み」が返る。

## Miss Lemon がやること（コマンド）
作業場所は `~/git-repos`。環境変数は `.env.jarvis_private`（値は表示しない）。

```bash
set -a; . ./.env.jarvis_private; set +a
python scripts/loopware_weekly_review_slack.py --mode export --week YYYY-MM-DD   # その週の生ログ（月曜の日付）
python scripts/loopware_weekly_review_slack.py --mode criteria-list              # 承認済みの基準
```

### 仮説の出し方（設計書「依頼のタスク化」「完了条件つきタスク」「重複タスクのまとめ方」に沿う）
- 「次も同じに」が付いた判断だけを基準の根拠にする。付いていないものは「今回だけ」。
- 本人の理由とAIの推測を分ける。理由が未選択のものは理由不明のまま。
- 「知っている」「今は不要」「誤り」を同じ×にしない。見送った＝嫌い、ではない。
- 件数が少ない週は断定せず「見直す候補」として出す。
- 1つの仮説ごとに：**基準の文／範囲／根拠（ログ◯件）／反対の例（ある場合）／確かめ方** を添える。
- 既存の基準と食い違う・重なるものは、そこも示す（取り消し候補）。
- 顧客名・社名・連絡先は、外に出す前に伏せる。

### 了承されたら（松野さんが明確に了承したものだけ）
```bash
python scripts/loopware_weekly_review_slack.py --mode criteria-add --text "基準の文" --range "範囲" --basis "根拠"
python scripts/loopware_weekly_review_slack.py --mode criteria-revoke --id cr-...   # 取り消すとき
python scripts/loopware_weekly_review_slack.py --mode review-done --week YYYY-MM-DD  # 週を確認済みに
```
- 書き込み前に `--dry-run` で内容を見せてよい。
- 了承されていないもの・見送られたものは書き込まない（見送った理由は、必要なら次週の材料として会話に残す）。

### 反映先
- 承認した基準は Supabase `owner_decisions`（surface=`loopware_criteria`）に追記され、アプリの `/review` に出る。
- タスク案を作る指示（`apps/loopware/prompts/proposal.md`、候補を作るスクリプト）へ書き足すのは、基準が固まった後に松野さんの了承を取ってから。自動では書き換えない。

## 費用について
Miss Lemon（Claude）の利用枠の中で行う。アプリ側に従量課金のAI呼び出しは無い。Supabase・Vercel・GitHub Actions は既存のもの。
