# KURASHIFT（クラシフト）

**暮らしを整え、資産を動かす** — ライフプラン軌道の資産運用HQ。

旧称 Trade Desk。コードパスは当面 `apps/trade-desk`（ポート 3003）。Jarvis ダッシュボードとは**別アプリ**。データは既存 Supabase `jarvis-dashboard`（第3プロジェクトは作らない）。

## やりたいこと（大きな分類・正）

ユーザーが回す本線は次の **3本**。検証もこの順（`docs/KURASHIFT_検証プラン.md`）。

| 分類 | 内容 | 主な画面 |
|---|---|---|
| **① 資産運用** | 全体把握／提案・相談・実行 | ホーム・資産・テーマ・相談 |
| **② 暮らしの計画と税** | ライフプラン更新／確定申告ネタ整理（個人） | ライフプラン・ROI・個人申告 |
| **③ 不動産賃貸経営** | **③-A〜D** 運用／購入検討／物件マスタ／融資パック（4レーン） | 不動産（`/realestate` ほか） |

③の設計正本: `docs/KURASHIFT_不動産賃貸経営.md`（Phase 0＝プラン登録済み。実装は段階的）。

それ以外:

| 区分 | 扱い |
|---|---|
| 前提（設定・ジョブ worker） | ①の前に一度 |
| 安全境界（未承認の実弾・振替・弥生本登録禁止） | 横断 |
| Lab（平均回帰・立花） | 後回し・本線外 |
| Jarvis ダッシュボード（パートナー等） | **別アプリ** |

## UI 差別化（Jarvis と被せない）

| | Jarvis Dashboard | KURASHIFT |
|---|---|---|
| 役割の印象 | 業務トリアージ・オペレーション | 暮らしと資産の計画スタジオ |
| 地色 | 暖色クリーム | 涼しい紙白・ブルーグレー |
| アクセント | ティール | Tableau 系オレンジ |
| サイドバー | 暗いチャコール | 明るい紙白 |
| 見出し書体 | ゴシック中心 | メイリオ系ゴシック（Noto Sans JP／Meiryo／游ゴシック。明朝なし） |

## いまの段階（2026-08-12）

- 正式名称: **KURASHIFT**
- 正本ライフプラン: `…/Numbers/Documents/Life Plan/260621_松野家FinancePlan.numbers`
- 定型ルーティンは**アプリのボタン → Mac ローカル処理**
- 相談・例外判断は**ローカル Jarvis** → 結果をアプリで閲覧
- 投資運用の定石は固定しない。一般的な提案から始め、相談で改善する
- 個人確定申告（弥生CSV）は本アプリ。法人は税理士委託＋メール／証憑閲覧
- **未承認の実弾・振替・弥生本登録はしない**
- **ログイン情報**: アプリ `/settings` → Mac worker → `.env.jarvis_private`（値は DB に残さない）
- **保険の契約者貸付残高**: 不動産頭金枠の把握用。ソニーは解約返戻と同ページから週次取得。`/portfolio` に表示

## 役割分担

| 層 | 役割 |
|---|---|
| **Numbers** | 年次の詳細編集の正本 |
| **KURASHIFT アプリ** | **トップ＝テーマ提案・実行・資産ステータス**。LPはレーン＋年末お知らせ／物件購入時。申告・ジョブ履歴 |
| **Zaim＋zaim_budget_sync** | 月次予算・実績 |
| **Jarvis（ローカル）** | 相談・年次更新代行・一度承認で完走・OTP・弥生登録支援 |
| **Git** | コード／設定の変更履歴（変更履歴UIは作らない） |

## 層構造

| 層 | 役割 | やらないこと |
|---|---|---|
| **LifePlan** | 年次4段階ルーティン・αβγ 20/60/20・計画スナップショット | 運用だけで生活／教育を食う |
| **Core** | インデックス年1RB・Bloomo固定・保険（真治＋千景）・既存口座 | 固定スリーブの無断いじり・国債比率の無理な復元（現状） |
| **Theme** | 大きな流れ・Bloomo動的・立花等。提案→相談→承認→完走 | 日次連射・ログなし・承認後のユーザー待ち |
| **Lab** | 平均回帰の小額実験（旧 Trade Desk 本線） | 利回り本線にしない |

支出目標: **貯蓄20%（α）／生活60%（β）／自己投資・教育20%（γ）**。**δ不動産は成長評価の分母に含めない**。

## ライフプラン（年1〜3回・トップの主戦場ではない）

日常のトップは **Theme 投資の提案・実行** と **他資産ステータスを踏まえた提案**。

ライフプラン更新の入口:

| トリガー | 動き |
|---|---|
| **12月終了後（1〜2月）** | ホームにお知らせ「年間実績が確定したので、当年以降の LP／予算を更新」→ `/lifeplan?mode=annual` |
| **不動産購入時** | ライフプランレーンから「物件購入で計画更新」→ `/lifeplan?mode=re_purchase` |
| **その他** | ローカル Jarvis に相談 → 相談記録へ |

年次ルーティン（モード選択後）:

1. 財務から対象年度の**実績を取り込む**
2. 実績を見ながら**補正し、その年の予算を作る**
3. 予算ベースで**100年ライフプランを更新・チューニング**して固める
4. 固めた予算を**財務（Zaim等）へ反映**する

関連シート（Numbers `260621`）:

- キャッシュフロー（〜100歳・計画vs実績・コメント必須）
- シングルインカム・表1（月別予算→Zaim）／表2（収入・実績×約1%）
- バランス評価 A成長／B節約、10.2教育、19不動産
- ROI・リバランスまとめ（CF/返済の横並び・年1RB）

計画スナップショット比較は本命。変更履歴シートUIは不要。

## 一度承認で完走（Theme／資金移動）

1. アプリまたはチャットにプレビュー（何を・いくら・経路・OTP想定）
2. 「これで進めてよいですか？」→ **一度承認**
3. Jarvis が画面操作・最終送信・OTP（SMS=Messages DB／メール=Gmail API）まで完走
4. 生体認証など技術的に取れない壁だけユーザー依頼

## アプリ ↔ Mac ローカル

| 種類 | 入口 | 流れ |
|---|---|---|
| 定型ルーティン | アプリの実行ボタン | `kurashift_jobs` に queued → Mac worker が実行 → 結果・ログ・成果物をアプリ表示 |
| 相談 | ローカル Jarvis | 相談記録を `kurashift_consultations` へ → アプリで閲覧 |
| 個人申告 | アプリ申告画面＋Jarvis | CSV生成・検査・弥生登録支援・税理士メール／証憑 |

許可されたジョブ種別のみ worker が実行する（任意シェルは禁止）。正本: `config/trade_theme_playbook.yaml`。

## 個人確定申告

- **個人のみ**（弥生青色申告用 CSV）。法人は税理士。
- 税理士メール＋添付は Gmail API で取込 → アプリで検索・閲覧（**既定アカウント: admin** `token_livingsupport.json`。切替は `KURASHIFT_TAX_GMAIL_TOKEN`）
- 添付は年度・案件・資料種別と紐づけ、**証憑として再出力**できる

## テーマ提案（ステージ2）

- ホーム／テーマ画面の「ステータスから提案を生成」→ `theme_propose_from_status`
- 資産スナップ＋リサーチから draft を作成（既存タイトルはスキップ）
- 手動草案は `/api/themes` フォームからも登録可
- Mac worker: `./launchd/install_kurashift_job_worker_launchd.sh`（15分間隔）

## Core 資産網羅（要約）

- Bloomo Web・固定／動的スリーブ（公開 API なし）
- **取得ハブ（2026-08-12 確定）**: **Bloomo → マネーフォワード ME**（実 Chrome セッション・評価の正）。**SBI インデックス → Zaim「SBI 証券」**（サイト直ログインは使わない）。**あかつき → 公式サイト Playwright**（メールOTP。MF連携は不可のため不採用）。証券内訳は `jarvis_securities_holdings.py`（SBI=Zaim／Bloomo=MF）。Bloomo→Zaim 週次反映は後段
- **アクサ生命**は保険 Core の本線。特別勘定比率は **IFA石河さん反映の正（参考）**
- ソニー生命・プルデンシャル生命は **真治＋千景** を分けて載せ、**/portfolio で対アクサ差分**を見る
- プルデンシャルは Web 取得せず手登録（`PRUDENTIAL_WEB_FETCH_DISABLE=1`／`PRUDENTIAL_*_VALUE_JPY`）
- 保険の月額・配分％: `config/insurance_allocations.yaml`（正）＋ `.jarvis_state/insurance_allocations_snap.json`（スクレイプ結果）。失敗時は前回 snap を維持
- **後回し**: 比率確認 → 石河さんへ **iMessage** 連絡 → 返信要約と変更／見直しの確認（不足時はメール）。`docs/KURASHIFT_検証プラン.md` B-IFA-1
- 既存: SBIインデックス／持株／あかつき／立花 等
- インデックス **年1リバランス**（現状は国債比率保持なし）

## Lab（旧平均回帰・参考）

過去検証はインデックスに負けやすい結論。Lab として残す。実弾はまだ進めない。

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_trade_backtest.py
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_job_worker.py --dry-run
```

立花口座開設・API鍵の手順は従来どおり（実弾直前）。詳細コマンドは `docs/運用コマンド一覧.md` §7.6。

## 関連

- playbook: `config/trade_theme_playbook.yaml`
- 戦略ラベル: `config/trade_strategy.yaml`（Lab）
- Theme入力: `config/trade_research_themes.yaml`
- 予算抽出: `215_kamiooya/.../zaim_budget_sync/numbers_budget_extract.py`（正本 `260621`）
