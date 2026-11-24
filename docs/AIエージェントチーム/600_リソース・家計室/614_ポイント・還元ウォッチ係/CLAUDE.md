# ポイント・還元ウォッチ係（614）

複数ツール（Claude Code / Cursor / Codex / GenCode / FlowForge 等）から同じフォルダを開いて使う指示書。  
直した運用知見は**このファイルに追記**する（チャットだけの修正にしない）。

ジャンル: **リソース・家計（得る側）**。隣係: **612** は払う側（年会費・課金ガード）／**613** Zaim鮮度。  
出口: `/vpoint`（テイチャン・Vポイント）＋ `/etc`（ETC還元）。

## AIオートメーション（作業フロー）

- **FlowForge**: ノード未作成。**素案の正は [`flow.md`](./flow.md)**（作り込み後に registry URL を追記）
- ビルダー（組織図）: https://agent-team-builder-teal.vercel.app/s/uksxiDIzE1AEckKH
- 一覧・進捗: [`15_FlowForge全体系_進捗_20261010.md`](../../15_FlowForge全体系_進捗_20261010.md)
- 設計の流れ図: [`flow.md`](./flow.md)
- Slack 短報正本: `scripts/jarvis_points_rebate_slack_report.py`（`--kind teiki|etc|vpoint|card_benefit`）
- 本線スクリプト:
  - テイチャン: `jarvis_teiki_barai_chance.py` ＋ `launchd/teiki_draw_runner.sh`
  - ETC還元: `jarvis_etc_rebate_fetch.py` ＋ 月次 launchd（20〜26日）
  - Vポイント定例: `jarvis_vpoint_routine.py`（窓C）
  - 年間特典ウォッチ（Olive Infinite／Marriott Bonvoy の2枚だけ）: `jarvis_card_benefit_watch.py`（条件は `config/card_benefit_watch.yaml`、実額は `.jarvis_state/card_benefit_watch.json`）

## 設計ゲート（4点）

| 柱 | 内容 |
|---|---|
| **入口** | Vpass／smile-etc／Vポイント state（`teiki_*` / `etc_monthly` / `vpoint_*`） |
| **確認** | 抽選・還元取得は自動。OTP・Wallet・規約未同意・ログイン失敗だけ人 |
| **履歴** | Slack `#report` 控え（非公開 `.jarvis_state/points_rebate_reports/`）・各 state・ダッシュ `/vpoint` `/etc` |
| **停止** | 各本線の `*_DISABLE` ／ `JARVIS_POINTS_REBATE_SLACK_REPORT_DISABLE=1` |

## 1. 役割

- **やること（得る側の見える化）**
  1. テイチャン券確認・抽選 → `/vpoint` ＋ Slack
  2. ETC 平日朝夕の還元サマリ取得 → `/etc` ＋ Slack
  3. Vポイント定例（窓C）の要約 → `/vpoint` ＋ Slack
  4. 年間特典ウォッチ（Olive Infinite／Marriott Bonvoy）: 達成率・月あたり必要額・届くペースか → `/vpoint#card-benefit` ＋ Slack 月次短報。**今月どちらに寄せるかの判断材料**（決めるのは松野さん）。過渡期なので2枚だけ（汎用化しない）
- **やらないこと**
  - 年会費・二重課金ガード本体（**612**＝払う側）
  - Zaim 鮮度・費目（**613**）
  - 秘密の再掲・対外送信

## 2. 動き出す合図

- [x] テイチャン: 月・木 10:15／朝取りこぼし
- [x] ETC還元: 毎月 20〜26日 09:30／朝取りこぼし
- [x] Vポイント: 25〜月末 09:40（窓C）／朝取りこぼし
- [x] 人が頼む: 「テイチャン」「ETC還元」「Vポイント定例」

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| CLI | ○ | 上記本線＋ `jarvis_points_rebate_slack_report.py` |
| ブラウザ／CDP | ○ | Mac Chrome 専用プロファイル（終了時 auto-quit） |
| Slack Webhook | ○ | `#report`（失敗時 `#ops`） |

**秘密**: `.env.jarvis_private` の `VPASS_*` / `ETC_*` / `SLACK_WEBHOOK_AI_TEAM_*`。本フォルダに値を書かない。

## 4. 報告先

| 種別 | 行き先 |
|---|---|
| 定時・結果 | Slack `#report`（【614 ポイント還元｜…】） |
| 失敗 | Slack `#ops` |
| 人が見る画面 | `/vpoint` · `/etc` |

### Slack 書き出し（FRIDAY／Jarvis 共通）

| ch | いつ |
|---|---|
| `#report` | 完了・定型・生存確認 |
| `#consult` | 要判断。末尾「次の担当」3行必須 |
| `#ops` | 障害・失敗・枠切れ |

`#consult` 末尾: `次: Grokで続行 | Jarvisに依頼 | 人判断のみ` ＋ `担当メモ` ＋ `橋渡し`  
正本: [`38_Slack書き出し_FRIDAY_Jarvis_20261018.md`](../../38_Slack書き出し_FRIDAY_Jarvis_20261018.md) · [`36_`](../../36_Slack_consult手渡し_次の担当_20261018.md)

## 5. 成果物の置き場

| 種類 | 場所 |
|---|---|
| state | `.jarvis_state/teiki_barai_chance.json` / `etc_monthly.json` / `vpoint_*.json` |
| Mac ログ | `~/Library/Logs/jarvis_teiki/` 等 |
| Slack 控え | 非公開 `.jarvis_state/points_rebate_reports/`（年間特典は `card_benefit_reports/`）。本フォルダ `reports/` の既存分（2026-10〜11 の41件）は旧置き場で、新規は書かない |

## 6. 作業手順

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
# テイチャン（ダッシュ＋Slack）
~/selenium_env/venv/bin/python scripts/jarvis_teiki_barai_chance.py --run --push
# ETC（取得反映＋ダッシュ＋Slack）
~/selenium_env/venv/bin/python scripts/jarvis_etc_rebate_fetch.py --apply --push
# Vポイント定例
~/selenium_env/venv/bin/python scripts/jarvis_vpoint_routine.py --apply --push
# Slack だけ dry-run
~/selenium_env/venv/bin/python scripts/jarvis_points_rebate_slack_report.py --kind etc --from-state --dry-run
```

## 状態

`agents_registry.yaml` の `status` を変えるときは**先にチャットで提案**し、了承後:

```bash
cd ~/git-repos && ~/selenium_env/venv/bin/python scripts/jarvis_agent_team_status_sync.py
```

## 7. 改善ログ

| 日付 | 変更 |
|---|---|
| 2026-10-17 | 係新設（旧名・テイチャン単体）→ Slack #report |
| 2026-10-17 | **ポイント・還元ウォッチ**に改名・拡大。ETC／Vポイント定例も `#report` 相乗り。612（払う側）と分離 |
| 2026-10-17 | ビルダー組織図に追加（共有 `uksxiDIzE1AEckKH`）。`flow.md` 素案を613型で充填 |
| 2026-10-29 | Vポイント Slack の文面を人の言葉に: 「要Jarvis確認」→「手で確認する項目: N件（一覧は下のページ）」、「窓C定例」→「月末の定例チェック（25日〜末日）」（松野FB） |
| 2026-11-23 | **年間特典ウォッチ**を追加（親: 600 ラコ #25）。Olive は Gmail 月次メール『各種特典条件達成状況』＝**確定値**、Bonvoy は Zaim 取込行＝**概算**（取込日ベースで画面とずれる）。条件の金額は `threshold_status`（確認済み／推定／要確認／未確認）を画面と Slack に必ず併記し、公式で確かめるまで「確認済み」にしない。`/vpoint` に年間特典・Olive 履歴（達成済み＝入会特典／これから＝継続特典）・Vポイントの出口（確認済み／注意／未確認。**Vポイント投資を先頭・大きめ**に出し「元本割れの可能性・判断は松野さん」を注記、その下にPay・請求額充当・景品）。Slack `--kind card_benefit`（dry-run まで。実投稿と launchd は松野さんの了承後。停止は `JARVIS_CARD_BENEFIT_SLACK_REPORT_DISABLE=1`）。実額入りの控えは公開リポの `reports/` でなく state 側 |
| 2026-11-23 | **年間特典の月次自動実行**を追加。毎月28日 09:50（Olive の月次メールが25〜27日ごろ届いたあと）＋朝オープンの取りこぼし（28日以降で今月まだ成功印なし）。本体 `jarvis_card_benefit_monthly.py`（取込 `--refresh` → Slack `--kind card_benefit --from-state`。失敗は `#ops`、成功した月だけ state に印）。Zaim の基準日が `zaim_stale_days`（既定10日）より古いと短報に「Zaim が古い（基準日◯）」。Olive の確定値が `stale_days`（45日）より古い月も「Olive は◯月◯日現在の確定値（古い）」。停止 `JARVIS_CARD_BENEFIT_DISABLE=1` |

### 年間特典の月次 launchd（導入は松野さんの了承後に Mac で）

```bash
cd ~/git-repos
# 先に投稿なしで確認（取込は行う・Slack は表示のみ）
~/selenium_env/venv/bin/python scripts/jarvis_card_benefit_monthly.py --force --dry-run
# 導入（毎月28日 09:50）
zsh launchd/install_card_benefit_monthly_launchd.sh
# 外す
zsh launchd/uninstall_card_benefit_monthly_launchd.sh
```

- ログ: `~/Library/Logs/jarvis_card_benefit/`
- 停止: `JARVIS_CARD_BENEFIT_DISABLE=1`（短報だけ止める時は `JARVIS_CARD_BENEFIT_SLACK_REPORT_DISABLE=1`）
- 成功印: `.jarvis_state/card_benefit_watch.json` の `last_monthly_run`（月 `YYYY-MM`）。**PR-P0a（2026-11-24〜）**: 全取得元（Olive・Bonvoy）が『成功』かつ保存の読み戻し成功の時だけ付く（Slack の成否とは独立。Slack より先に確定し、投稿失敗でも消えない）。取得元ごとの成否・基準日・error_code は同 state の `sources`、月の進み（取得済み・最後に試した日・短報済みの目印）は `monthly`
- 成功・部分成功・取得待ち・失敗・未確認の5状態。成功以外は月印なし・寄せ先推奨は保留（取れた方の達成率は表示）。失敗は #ops、`jarvis_card_benefit_watch.py --refresh` の終了コードは失敗で 2（state 破損 3・保存の読み戻し不一致 4）
- **Zaim の鮮度**: Bonvoy 行の最新日ではなく『取込CSVの範囲の終了日』（`zaim_csv_weekly.json` の `end_date`＝週次エクスポート成功時／失敗時は最後に成功した日、と取込 index の更新日のうち古い方）で10日判定。Bonvoy 行の最新日は `last_use_date`（最終利用日）として補足表示。Olive の45日基準は変更なし
- 再試行: 28日〜月末の翌朝に1日1回、未成功の取得元だけ。短報は状態が変わった時だけ・投稿だけ失敗したら投稿だけやり直す。保存の読み戻しに失敗したら取得済みデータを `.jarvis_state/card_benefit_watch.pending.json` に残す（自動復元は未実装＝再起動後の扱いは未決）
- `--force` は『28日前でも動かす』だけ（成功済みの取得元は取り直さない）。全部取り直す時は `--all`。launchd の入れ直しは不要（runner は変えていない）。同時起動は排他（`card_benefit_watch.lock`）
| 2026-11-23 | **Bonvoy 概算にアメックスでの Amazon 購入を加算**。Zaim ではこれが「振替（支払元=アメックス、入金先=Amazon）」で入り、zaim_learn のインデックス（支出行のみ）に無く概算が過少だった。インデックスは学習の差分に使うため触らず、614 が index の `csv` パスの CSV を直接読む（`aggregate_zaim_transfers`）。対象は設定 `zaim_transfer_to_include`（入金先キーワード）に合う transfer 行のみ。カード引落（銀行→カード）・残高行は足さない。年会費除外は維持 |
| 2026-11-23 | Bonvoy 概算の振替加算に**警告と件数**を追加（#579 の補強）。足さなかった振替（カード→ウォレット等）の件数 `other_transfer_rows` を state に持ち、画面に「概算（振替含む）: 振替N件を加算・未算入M件」。Zaim CSV を読めない時は黙って過少にせず、画面「振替行は未加算」・短報「Bonvoyの振替は未加算（要再取込）」。短報は「Bonvoyは振替N件を含む概算」（件数のみ）。負の振替（Amazon からの返金）は純額で引く（実データで #578 版と利用額が一致するよう統一） |
| 2026-11-23 | **作業フローを磨き込み（『魂を込める』第1段階・docs のみ）**。`flow.md` を全面改訂し `flow.json`（正本）・`flow.html`（図の確認用）を追加。24工程・判断点8・未確認15。実行時にAIを呼ぶ工程は0。**気づき**: テイチャンのサイトが 10/22 朝からメンテ停止中なのに「確認のみ・券=2枚」と報告し毎朝起動（D4）。Vポイント定例は Tサイト履歴が 9/10 のまま印だけ付く（D6）。年間特典は取込失敗でも月印が付く疑い。いずれも未修正（判断待ち）。FlowForge は触らない（54b） |
| 2026-11-23 | **フロー第2稿（Codex レビュー反映・docs のみ）**。Codex の指摘（誤り6件・優先修正5件）を `flow.md`／`flow.json`／`flow.html` に反映: 『毎日・メンテ開始』を推定・未特定に直す／10/25 の run ログは0バイトで成功の証拠にならない／正常スキップ（新ノード32）と控え（dry-run でも作られる）を分離／全矢印に［現行］［提案］を付与／提案ノード25〜31（取得元別の成否・月印と再試行・基準日判定・保存検証・排他・再開検知・run 結果集約）を追加。判断点は D4→D6→D1/D2→D5→D7/D8→D3 の順。**決定: Slack の短報には実額を載せてよい（松野さん本人宛）／公開リポ（コード・docs・PR・テスト・reports）には実額を書かない**（D9 決定済み）。気づき F7〜F9（mask 指定の確認・ETC 控えに金額が入る・recommend が鮮度を見ない）。コードは未修正 |
| 2026-11-23 | **D6 実装（Vポイント：履歴が古い時は『部分成功』）**。付与サマリの成否を基準日で判定（Tサイト履歴の取得日が対象月の末日以降＝成功／前・不明・監査フォールバック＝部分成功／履歴も行も無い＝失敗）。**月印 last_check_c は成功の時だけ**。部分成功は短報『部分成功（履歴が古い・基準日=…）』（Slack は本人通知なので具体値あり）・asks に『Tサイト取って』。付与サマリ以外の定例は止めない。F3（last_routine_at／asks が PDCA 後に消える）も保存順で修正。`scripts/tests/test_vpoint_grant_quality.py`。取得時期（6a）は決めない（松野さん決定） |
| 2026-11-23 | **D4 実装（テイチャン：メンテ停止中は3日に1回・短報『メンテナンス停止中（最終確認日）』）**。画面本文の『メンテナンス＋停止』で `site_status=maintenance`（再開予定の行を保存・券数と規約は前回値のまま）。停止中は朝の取りこぼし（morning_refresh）も本線 `is_due` も券数>0 では起動せず、3日間隔。再開（通常画面に戻る）を検知したら通常の間隔に戻り、その回の短報に『メンテナンス明けを検知』。停止中の間隔内スキップは Slack に出さない。本線に flock の排他（`.jarvis_state/teiki_barai_chance/run.lock`）。停止スイッチ `*_DISABLE` は不変。`scripts/tests/test_teiki_maintenance.py` |
| 2026-11-24 | **PR-P0a（年間特典の誤成功防止・第3稿 P0）**。取得元ごとの5状態・月印は取得＋保存の読み戻し成功だけ・推奨停止（F5・F9）・排他と読み戻し付き保存（`jarvis_614_verified_state.py`）。Vポイント・ETC・テイチャンの挙動は変えていない（11/25 09:40 の窓C の前）。本番確認は 11/28 の初回。単体テスト `scripts/tests/test_card_benefit_p0.py` |
| 2026-11-23 | **F8 実装（Slack 控えを非公開側へ）**。`jarvis_points_rebate_slack_report.py` の控えを、公開リポ docs の `reports/` ではなく `.jarvis_state/points_rebate_reports/`（gitignore 済み）へ。ETC・テイチャン・Vポイントとも（年間特典は従来どおり `card_benefit_reports/`）。dry-run の控えは `_dryrun` の別名で『未配信』と明記。本フォルダ `reports/` の既存41件は消していない（うち実額を含むのは ETC の1件・扱いは松野さんに確認）。`scripts/tests/test_points_rebate_report_archive.py` |
| 2026-11-23 | **言葉の訂正（docs のみ）**。『チャッピー』は ChatGPT のチャットモード（松野さんがチャットで作業フローを見ながら確認する）。Codex（Orca の worker）のレビューは任意の別の目（補助）で、チャッピーとの確認の代わりではない。ボットの役目はチャットに持ち込む材料を用意し、結果を受けて直すこと。`flow.md`／`flow.json`／`flow.html` の該当語を直した。 |
