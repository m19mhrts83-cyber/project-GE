# Jarvis 定例 — GitHub Actions と launchd の仕分け

**方針（2026-09-10）**: 定期実行のうち **定型化できたもの（API・トークン・再現可能なヘッドレス）は GHA**。  
**ブラウザ銀行／カード・CDP・ローカル path・常駐**は **launchd（Mac）**。朝オープン取りこぼしでスリープを吸収する。

関連: `docs/運用コマンド一覧.md`「最新化マトリクス」／`AGENTS.md`（Cloud で動くアプリ）

## 判定ルール（新規定例を足すとき）

次を **すべて満たす** → **GHA 本線**

1. 秘密は Secrets で足りる（銀行PW・OTP 必須でない）
2. 出力先がクラウド（Supabase／Vercel／GitHub／API）で、OneDrive／`.jarvis_state` 必須でない（または結果だけクラウドへ書ける）
3. ヘッドレス／API で同じ結果が繰り返し取れる（CAPTCHA・端末セッション非依存）
4. Mac スリープ中でも動かしたい

次が **1つでもある** → **launchd 本線**（GHA は実験のみ／やらない）

- Vpass／smile-etc／Zaim Web／証券ログイン等の **銀行・カード UI**
- Chrome CDP・保存プロファイル必須
- CHRLINE／Square／QR
- OneDrive／Documents 直書きが正本
- 常駐（watch）や GUI 操作

**過渡**: GHA で軽量版、Mac で全文／補完（例: Gmail triage は GHA、`gmail_to_yoritoori` は Mac）。

---

## A. GHA 本線（定型化済み／寄せたい）

| 定例 | Workflow | 備考 |
|---|---|---|
| admin Gmail → triage | `jarvis-dashboard-gmail-triage.yml` | 05:00 JST |
| 状況ウォッチ（軽量） | `jarvis-dashboard-situation-watch.yml` | 06:15 |
| レーン要約 | `jarvis-dashboard-lanes.yml` | Graph 委任 |
| Dashboard heartbeat | `jarvis-dashboard-heartbeat.yml` | |
| kamiooya-qa 心拍 | `kamiooya-qa-heartbeat.yml` | Free 休止対策 |
| WeStudy 週次取込 | `westudy-raimo-weekly.yml` | Playwright 可だが Secrets＋再現性あり |
| Trade Desk 週次（クラウド分） | `trade-desk-weekly.yml` | Mac 資産週次と役割分担 |
| KURASHIFT 問合せ（Tier3） | `kurashift-re-daily-inquiry.yml` | 明示 enabled 時 |
| Zaim 財務日次（API 系） | `zaim-finance-sync.yml` | Playwright CSV とは別 |
| Ops Fail Watch | `jarvis-ops-fail-watch.yml` | 失敗監視 |
| Pages / deploy | `pages-docs.yml` / `trade-desk-deploy.yml` | 定例というよりデプロイ |

---

## B. launchd 本線（GHA に寄せない／寄せられない）

| 定例 | launchd / 経路 | 理由 |
|---|---|---|
| **ETC 還元取得** | `etc-rebate-monthly` | smile-etc ブラウザ |
| **Vポイント定例**（付与サマリ＋促し） | `vpoint-routine` | ローカル state＋任意でテイチャン相乗り。TサイトOTPは人手 |
| **テイチャン抽選** | `teiki-draw` | Vpass＋Chrome CDP。headless/GHA はログイン失敗（実測） |
| Zaim CSV／銀行同期 | `zaim-csv-weekly` / `zaim-bank-sync-friday` | Playwright＋OneDrive |
| 資産週次（証券ログイン） | `portfolio-weekly` | 同上 |
| CHRLINE／オプチャ常駐 | `line.openchat.watch` 等 | Mac 専用 |
| **815オプチャ MD→DB→publish→/openchat** | `openchat-md-db-sync`（07:40/20:30） | CHRLINE＋OneDrive＋kamiooya-qa（staging→ready）。パートナー確認／朝LINEでもMDは取込済み想定 |
| 夜間フル triage | `night-triage` | ローカル path 多。Gmail general は GHA で一部代替済 |
| 朝オープン／Mac 朝バンドル | `triage-morning-open` + `jarvis_morning_mac_refresh` | 取りこぼし回収のハブ |
| dashboard push（投影） | `dashboard-push` | `.jarvis_state` 依存 |
| 家族 Journal 週次 | `family-journal-weekly` | Drive／Notion 補完 |
| 部長ボックス poll | `bucho-inbox-poll` | Drive ローカル／CDP 系 |
| Cursor revise worker | `cursor-revise-worker` | ローカルキュー |
| WeStudy Drive 添付 | `westudy-gdrive-archive` | admin Drive＋Mac |
| プライベートバックアップ | `private-backup` | ローカル age |
| 天気朝ブリーフ等 | `weather-morning-brief` 等 | Mac／ローカル前提のもの |

---

## C. 実験・やらない（GHA）

| 定例 | 状態 | メモ |
|---|---|---|
| テイチャン GHA | `teiki-barai-draw.yml` は **workflow_dispatch のみ** | 定型化未達。Secrets 実験用。本線は launchd |
| ETC / Vポイント 付与 | GHA 化しない | 銀行 UI |
| Zaim Playwright CSV | GHA 化しない | 明記済み |

---

## 最近増やした定例の位置づけ

| もの | 置き場 | 根拠 |
|---|---|---|
| ETC 月次還元 | **launchd** | smile-etc |
| Vポイント月次オーケストレータ | **launchd**（サマリは既存ファイルのみなら将来 GHA 可） | 現状は state＋テイチャン相乗り |
| テイチャン自動抽選 | **launchd** | Vpass CDP |
| Vポイント「促しだけ」 | 将来 **GHA** 候補 | Supabase に `jarvis_asks` を書くだけなら API 化できる |

---

## 運用メモ

- Mac スリープ: launchd は起床後＋`jarvis_morning_mac_refresh` で回収
- 真にノート非依存が要る launchd 仕事: **常時ON Mac**（mini 等）か self-hosted runner
- 新規定例を足すとき: この表の判定ルール → A なら workflow、B なら `launchd/install_*.sh`＋朝取りこぼし
