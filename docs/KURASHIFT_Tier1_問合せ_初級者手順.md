# KURASHIFT — Tier1 第一問合せ（初級者向け）

**更新**: 2026-08-23  
**対象**: Grok 調査済みの物件に、不動産会社へ **1件ずつ** 第一問合せメールを送る操作  
**本番 URL**: https://jarvis-trade-desk.vercel.app/realestate/deals

---

## 用語（3つだけ）

| 言葉 | 意味 |
|---|---|
| **Tier1** | 「問合せしてよい候補」。Grok が「聞く/保留」またはスコア2以上 |
| **estate** | 送信元メール `matsuno.estate@gmail.com`（Mac が自動送信） |
| **Mac worker** | Mac 上で動くプログラム。KURASHIFT の「送信」ボタン → 実際の Gmail 送信 |

---

## 事前準備（1回だけ）

1. **KURASHIFT にログイン**  
   https://jarvis-trade-desk.vercel.app/login

2. **Mac worker が動いているか**（Mac 側）  
   ターミナルで次を実行すると、キューに溜まった送信ジョブが処理されます。

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_kurashift_job_worker.py --once
```

   常駐している場合は `--once` なしでも可（launchd `jarvis_kurashift_job_watch`）。

3. **1日の上限**  
   問合せは **1日5件まで**（Tier1 も Tier2 も合算）。YAML 正本: `config/kurashift_re_inquiry_auto.yaml`

---

## Tier1 で今日やること（仕分け）

一覧: https://jarvis-trade-desk.vercel.app/realestate/deals?tab=candidates&inquiry=ready  
（「問合せ候補のみ」リンクでも同じ）

各行を見て、次の **どれか1つ** を選ぶ。

| 判断 | ボタン | 結果 |
|---|---|---|
| **問合せする** | 黄「問合せ」 | プレビュー確認 → 送信（1日最大5件） |
| **まだ残す（見た印）** | 「確認した」 | 候補タブに残る。Gmail 既読キュー。あとで問合せ可 |
| **見送り（候補から外す）** | 「対象外」 | `status=passed`。候補タブから消える。**これがスキップ／消し込み** |
| **本文を直してから送る** | 「開く」→ 橙「詳細編集して問合せ」 | 宛先・本文を編集して送信 |

### おすすめの進め方

1. `inquiry=ready` で候補だけ表示  
2. 上から1件ずつ  
   - 明らかに違う → **対象外**  
   - 良さそう → **問合せ**（今日の残り枠内）  
   - 迷う・Grok未調査 → **確認した** か、あとで戻る（候補に残る）  
3. 今日の問合せは **5件まで**（Tier2 と合算）  
4. 送信後は `/jobs` で `succeeded` を確認  

### 見送りについて

- **「対象外」＝見送り**です。候補一覧から外れ、「見送り」タブ側に寄ります。  
- Grok「聞く／保留」付きの passed は、ルール上 **再検討** で Tier1 に戻ることがあります（バッジ「再検討」）。完全に消したいときは対象外のまま触らない。  
- 「スキップしてあとで」だけなら **確認した** か、何も押さず次の行へ（一覧には残る）。

---

## 5件送る流れ（1件あたり 3〜5 分）

### ステップ A — 候補を開く

1. ブラウザで **候補一覧** を開く  
   https://jarvis-trade-desk.vercel.app/realestate/deals?tab=candidates&inquiry=ready

2. 表の上に **「問合せ候補 N」** のようなサマリーが出ていれば OK  

3. 送りたい行の **黄「問合せ」** を1つクリック（二重表示は解消済み）

### ステップ B — プレビューを確認

モーダルが開いたら、次を **目視** してください。

| 確認項目 | OK の目安 |
|---|---|
| **宛先（To）** | 不動産会社のメールアドレス（`@` あり） |
| **From** | estate（表示上「松野エステイト」系） |
| **件名・本文** | 物件名・所在が合っている |
| **倍率地域** | 本文に **固定資産税** の依頼文が入っている（Grok が「倍率」と判定した案件） |

宛先が空のときは、メールに載っていたアドレスを **手入力** してから送れます。

### ステップ C — 送信

1. 「内容を確認した」に **チェック** を入れる  
2. **送信** をクリック  
3. 画面に「送信キューに入れました」等が出れば KURASHIFT 側は完了  
4. **Mac worker** が estate から Gmail 送信（数十秒〜数分）

### ステップ D — 送信できたか確認

1. **ジョブ画面**  
   https://jarvis-trade-desk.vercel.app/jobs  
   `re_deal_inquiry_send` が **succeeded** になっているか

2. 失敗（failed）のとき  
   Mac で worker を再実行（上記 `--once`）。Mac 版 LINE は起動しない（CHRLINE 競合防止）。

3. 同じ物件を再度開くと `inquiry_status` が **awaiting_reply**（返信待ち）になっているはず

---

## 5件終わったあと

### 返信の取込（翌日以降でも可）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
/Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_inquiry.py --poll-replies
```

または朝バンドル（`jarvis_morning_mac_refresh.py`）に含まれます。

返信が付くと KURASHIFT で **has_reply** → ドロワーに本文・PDF 確認 → 運営相談フォーム（別手順）。

### 日次ダイジェスト

```bash
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_daily_digest.py
```

パートナー確認や朝ルーティンの末尾に貼られるブロックで、要返信・Tier2 送信待ちも確認できます。

---

## Tier2 との違い（参考）

| | Tier1（この doc） | Tier2 |
|---|---|---|
| 条件 | 緩め（聞く/保留 or score≥2） | 厳しめ（聞く + score≥5 + HZ≠除外） |
| 画面 | 候補表の **1件ずつ** | `/realestate/deals/tier2` **一括確認** |
| いつ使う | **今すぐの主線** | Tier1 に慣れたあと（YAML で enabled） |

---

## 困ったとき

| 症状 | 対処 |
|---|---|
| 送信ボタンを押しても Gmail が出ない | Mac worker 実行・`/jobs` で queued のままか確認 |
| 候補が0件 | Grok `[Grok調査]` 取込 → `--dry-run` で Tier 分類 |
| 1日5件で止まる | 仕様。翌日 JST 0:00 以降 |
| 倍率なのに固定資産税文がない | 送信前に止める。Grok レポートの `方式: 倍率` を確認 |

分類 dry-run:

```bash
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_inquiry_rules.py --dry-run
```

---

## 正本リンク

- 進捗一覧: `docs/KURASHIFT_問合せパイプライン_進捗_20260823.md`
- E2E: `docs/KURASHIFT_re_inquiry_E2E_checklist.md` §9
- 閾値 YAML: `config/kurashift_re_inquiry_auto.yaml`
