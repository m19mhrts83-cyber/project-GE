# Trade Desk（株自動売買＋資産全体ビュー）

Jarvis ダッシュボードとは**別アプリ**（`apps/trade-desk`、ポート 3003）。データは既存 Supabase `jarvis-dashboard`（`trade_*` / `portfolio_*`）。ダッシュボード内に `/trade` は置かない。リンクだけお金ナビ／アプリ集から外部へ。

## いまの段階（2026-08-12）

- **実弾はまだ動かさない。** シミュレーション → 調整 → 少額トランシェ、の順
- 過去検証スクリプト: `scripts/jarvis_trade_backtest.py`（DBに書かない）
- 日次ペーパー（先の仮想約定）はバックテストのあとで日常確認用
- 立花の口座開設は並行して進めてよい（API鍵は実弾直前）

## 進め方（トランシェ制）

実弾に進むのは、各ゲートを人が「いける」と判断したあとだけ。自動昇格しない。

| 段 | 名前 | お金 | 目的 | 次へ進む目安 |
|---|---|---|---|---|
| A | 過去シミュレーション | 動かさない | 平均回帰リズムが過去1〜2年で破綻しないか | 最大DDが −20% 未満、極端な連敗がない。パラメータ調整可 |
| B | ペーパー（先回り仮想） | 動かさない | 今の相場でも同じルールが機能するか | 最低4週間。週次で見直す |
| C | Tranche 1 | **10万円** | 少額で約定・スリッページ・自分の耐性を見る | 発注は1件ずつ承認。8週プラスかつ DD −8%以内 |
| D | Tranche 2+ | +10万円ずつ | 確信が深まった分だけ増やす | ユーザーが明示したときだけ。−10%で新規停止、−20%で全停止 |

A が微妙なら B に進まずパラメータを直す。C が微妙なら増額しない。

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_trade_backtest.py
~/selenium_env/venv/bin/python scripts/jarvis_trade_backtest.py --range 2y
```

## あなたが先にやること: 立花証券e支店の口座開設

**申込済み**（2026-08-12、お申込番号 2026081200001）。次は届いた用紙に記入し、本人確認＋マイナンバーを返送。

1. 開設: [https://kouza.e-shiten.jp/actr/](https://kouza.e-shiten.jp/actr/)（受付済み）
2. **特定口座（源泉徴収あり）**（申込どおり）
3. 信用取引は申し込まない（当面は現物＋インバースETF）
4. NISA は必須ではない（短期スイングは特定口座側）
5. 本人確認・マイナンバーの返送。開設完了まで 1〜2 週間見ておく
6. 開設後、SBI から **10万円だけ** 出金して立花へ入金（残りはインデックス側に残す）

### 開設後の API 設定（実弾の直前）

公式: [APIサービス](https://www.e-shiten.jp/api/) / [v4r9 公開鍵](https://www.e-shiten.jp/api/20260513.html) / [認証ID手順 PDF](https://www.e-shiten.jp/pdf/authidmanual.pdf)

1. 標準Webで **パスキー** を登録してログイン
2. お客様情報 → **ｅ支店・API 利用設定** → **利用する**
3. 公開鍵を「登録（自動）」→ 秘密キー「登録」→ 直後に **DL**
   - `e_api_authid.txt` / `e_api_private_key.pem`
   - **この画面でしかDLできない**。チャット・Git に置かない
4. 保存したら Jarvis に「立花のAPI鍵を保存した」と一声。`.env.jarvis_private` のパスだけ正本化する

デモ環境: [https://www.e-shiten.jp/Service/demo.html](https://www.e-shiten.jp/Service/demo.html)

## 売買の原理（平均回帰リズム）

狙うのは「トレンドに全乗り」ではなく、**上がっていく平均から一時的に沈んだ優良株が、戻る確率の高い区間だけ**に乗ること。  
GAFAM やその周辺はニュースで激しく上下するが、紙くず前提にはしない。ニュースは「今どの本命が沈んでいるか」を追うために使い、売買そのものは平均回帰リズムで機械的に刻む。

OpenAI / Anthropic / SpaceX 本体は未上場または取扱確認前。当面の受け皿は東証 ETF（S&P500・NASDAQ100）と、公開代理（MSFT / AMZN / GOOGL）の監視。立花e支店 API は日本株が本線。米株個別は取扱確認が取れてから。

```
著しく沈む → 反発の兆候で少量（probe）
    → 本物の戻りなら買い増し（confirm）
    → 確信が深まったらさらに買い増し（convince）
    → リズムが崩れたら全部は売らず一部撤退
```

| 段階 | いつ | 枠（1銘柄上限の内訳） |
|---|---|---|
| probe | SMA60／直近高値から 8〜22%沈み、かつ反発サインが2つ以上 | 25% |
| confirm | 初回よりプラス、陽線が続き、一時的な戻りではない | +35% |
| convince | 短期平均を回復し RSI が中立以上 | +40% |

反発サイン: 陽転・陽線・安値切り上げ・RSI上向き。  
**下がったから買い増す（ナンピン）はしない。** 買い増しは反発が確認できたときだけ。  
ナイフ（SMA20 が急傾斜で沈み続け）や 22%超の沈みは構造悪化の可能性として見送り。

崩れ方:

- 初回のリズムが折れたら **半分だけ売る**
- そのあと戻らなければ **残り撤退**
- 平均（SMA60）付近まで戻ったら **半分利確**
- 硬損切は平均取得から −8% またはスイング安値割れ

単元が高い銘柄は1株が probe 枠を超えることがある。そのときは1株で止まり、一部売却も実質全売却になる。

正本: `config/trade_strategy.yaml` / 実行パラメータ: `trade_params.strategy_v1`

## リスクルール（要約）

| 層 | 内容 |
|---|---|
| 構造 | 現物のみ。レバレッジなし |
| Tranche 1 | 入金 10万円 |
| 昇格 | 直近8週プラス かつ DD −8%以内 → +10万円 |
| 新規停止 | 元手比 −10% |
| 全停止 | 元手比 −20% |
| 1銘柄 | 運用枠の 20%（その中を 25/35/40 で刻む） |
| 同時建玉 | 最大 4 |
| 損切 / 利確 | −8% 硬損切 / 平均回帰で半分、伸び切り +12% |

## 資産全体ビューに載せる口座

ソニー生命 / アクサ生命 / SBIインデックス / 三菱重工持株会 / あかつき債券 / 立花自動売買。

### 週次の取り方（GHA と Mac の分担）

ログインが必要なサイトは **GitHub Actions に載せない**（OTP・利用規約・秘密）。

| ソース | 経路 | 取得するもの |
|---|---|---|
| ソニー生命 | Mac Playwright | 解約返戻金 |
| アクサ生命 MyAXA | Mac Playwright | 積立金／払いもどし |
| SBI証券 | Mac Playwright | 評価額（発注しない） |
| 三菱重工持株 | Mac・Zaim 連携口座 | **評価額**（毎月買い足すので口数固定にしない） |
| あかつき債券 | Mac Playwright → **Zaim 財務登録** | 評価額。差分は 2026-04-15 と同じ `外国債減収`（増収は `J.外国債増収`）。集計に含めない |
| 立花ペーパー | GHA / Mac | `trade_risk_state` |

- 本線: 日曜 09:00 `com.matsunoma.jarvis.portfolio-weekly`（`RunAtLoad` あり。成功済みの週はスキップ）
- 取りこぼし: Mac を開けば `jarvis_morning_mac_refresh` が裏起動
- クラウド: `.github/workflows/trade-desk-weekly.yml`（日足＋Tavily＋レビュー）

手入力の補完は `scripts/jarvis_portfolio_snapshot.py`。

## 情報の使い方（ニュースは売買の主因にしない）

判断は常にこの順:

1. **市況（regime）** — 日経ETFの長短移動平均。守り相場なら新規買いは抑制
2. **セクター相対** — 資金が集まっている分野だけ厚くする
3. **銘柄テクニカル** — 平均からの沈み幅・反発サイン・リズム（買い増し／一部撤退）
4. **ニュースは加点のみ** — ChatGPT週次 / Tavily / Deep Research。Tavily はオンライン時にキャッシュし、オフラインは蓄積を読む

分野: マクロ・為替 / AI・半導体 / 宇宙・防衛 / 日本大型 / ヘルスケア / 地政学リスク  
定義: `config/trade_research_themes.yaml`

### ChatGPT 週次ニュースの横流し

AI・宇宙の週次メモは次のいずれか:

- ファイルを `~/git-repos/.jarvis_state/trade_research_inbox/` に置く（`.md` / `.txt`）
- またはチャットに「保存した」と一声

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_trade_research_ingest.py --from-inbox --topic ai,space
~/selenium_env/venv/bin/python scripts/jarvis_trade_research_ingest.py --tavily
# オフライン（APIを呼ばずキャッシュだけ）
~/selenium_env/venv/bin/python scripts/jarvis_trade_research_ingest.py --tavily --cache-only
```

画面の「リサーチ」は `trade_research` を表示するだけ（Tavily を呼ばない）。キャッシュ実体は `.jarvis_state/tavily_cache/`。

## 関連

- コマンド正本: `docs/運用コマンド一覧.md`「Trade Desk」
- ルール: `.cursor/rules/jarvis-trade-desk.mdc`
- ウォッチリスト: `config/trade_watchlist.yaml`
