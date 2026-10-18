# 業者開拓フォロー係

ID: **516**。部門: 不動産パイプライン実行室（500）。  
Grok S系（**S2 / S4 / S9**）の **見守り係**（枯渇検知・Drive補給・sync_meta・Slack）。  
**開拓の実行（検索・文案・送信）は Grok 一本。516 は二重実行しない。**  
**送信の線引き（2026-10-15）**: 承認済み**定型**テンプレは都度許可不要。**非定型**は松野が一度必ず見る。

## AIオートメーション（作業フロー）

- **FlowForge（開く）**: [flow_dCheumorewDolXnfpksSuWKu](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_dCheumorewDolXnfpksSuWKu)
- 一覧・進捗: [`15_FlowForge全体系_進捗_20261010.md`](../../15_FlowForge全体系_進捗_20261010.md)
- 設計の流れ図: [`flow.md`](./flow.md)
- **本線コマンド**: `scripts/jarvis_vendor_outreach_stall_runner.py`（FlowForge はこれを呼ぶ。UI手作業の二重化をしない）

## 1. 役割

- やること:
  - **S2/S4/S9** キュー枯渇・`--next` 未着の検知と **自律 refill**（outbox `s2_batch` / `s4_queue` / `s9_precheck`）
  - inbox の「週次キュー再生成」等依頼の消化（archive）
  - 部長日報 `--mark` 反映後の **各 vendor_sync**／`sync_meta` 更新確認
  - **週次** Slack `#report`（healthy 時のみ・Grokサポート見守りタイトル・レーン擬似表）
  - 連携障害・枯渇は **即時** Slack `#ops`（日次見回りは毎日継続）
  - 要ボス（返信方針）だけ `#consult`／Todoist（業者専用レーンは作らない）
- やらないこと: 対外送信の無断実行／Grok調査の丸写し再実装／秘密の再掲／探索の再スクレイプ

## 2. 動き出す合図

- [x] 人が頼む — 「業者開拓フォローして」→ `…stall_runner.py --apply --lane all --force-refill`（必要なら `--daily-report`）
- [x] 時間 — **GHA 平日16:00**（`kurashift-vendor-outreach-stall.yml`・見守り／`--skip-refill`）／Mac **朝** soft-fail・**夕方** `--evening`（補給保険）
- [x] 何かが届いたら — `jarvis_bucho_inbox_poll` 成功後フック（再生成依頼・`--next` 依頼 MD）
- [x] 変化・失敗を見回ったら:
  - `needs_refill`（送信可能件数が日次枠未満）
  - `no_marks` / stale（最終 contacted から平日2日以上・本日 mark なし）
  - Mac／Drive ブリッジ未接続（outbox 不可）

無効化: `.jarvis_state/vendor_outreach_stall.json` の `"disabled": true` または `JARVIS_VENDOR_OUTREACH_STALL_DISABLE=1`

## 3. 実行権限

| 方法 | 使う？ | 内容 |
|---|---|---|
| チャット・検索 | ○ | 状況説明・要フォロー要約 |
| CLI | ○ | stall runner／各 vendor_list／vendor_sync／bucho_mail_apply（ゲート遵守） |
| ブラウザ | △ | KURASHIFT vendors / repair-vendors / mgmt-vendors |
| 画面操作 | × | 送信は人／Grok |

**人が確かめる**: 対外送信・金・削除。

## 4. 報告先

| 種別 | 行き先 |
|---|---|
| 完了報告（週次・healthy） | Slack `#report`（`--evening` 枠内の週次ゲート） |
| 連携障害・枯渇 | Slack `#ops`（即時） |
| 要判断（返信方針） | Slack `#consult` ＋ Todoist（要ボスのみ） |

| レーン | UI |
|---|---|
| S2 | https://jarvis-trade-desk.vercel.app/realestate/vendors |
| S4 | https://jarvis-trade-desk.vercel.app/realestate/repair-vendors |
| S9 | https://jarvis-trade-desk.vercel.app/realestate/mgmt-vendors |

### Slack 書き出し（FRIDAY／Jarvis 共通）

| ch | いつ |
|---|---|
| `#report` | 完了・定型・生存確認 |
| `#consult` | 要判断。末尾「次の担当」3行必須 |
| `#ops` | 障害・失敗・枠切れ |

`#consult` 末尾: `次: Grokで続行 | Jarvisに依頼 | 人判断のみ` ＋ `担当メモ` ＋ `橋渡し`  
正本: [`38_Slack書き出し_FRIDAY_Jarvis_20261018.md`](../../38_Slack書き出し_FRIDAY_Jarvis_20261018.md) · [`36_`](../../36_Slack_consult手渡し_次の担当_20261018.md)

## 5. 成果物

| 成果物 | 置き場 |
|---|---|
| 週次バッチ／キュー kickoff | `【with Grok bot】/outbox_to_teams/re/`（`s2_batch` / `s4_queue` / `s9_precheck`） |
| stall state | `.jarvis_state/vendor_outreach_stall.json`（`lanes.s2|s4|s9`） |
| UI サマリ | `sync_meta`: `vendor_outreach_stall` / `_s4` / `_s9` |
| YAML 正本 | `kurashift_re_vendor_list.yaml` · `kurashift_repair_vendor_list.yaml` · `kurashift_mgmt_vendor_list.yaml`（gitignore） |

## 6. 手順（正）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a

# 朝・inbox 相乗り相当（補給＋sync_meta＋必要時 #ops）
~/selenium_env/venv/bin/python scripts/jarvis_vendor_outreach_stall_runner.py --apply --lane all

# 夕方見回り（#report は週次ゲート・healthy 時のみ）
~/selenium_env/venv/bin/python scripts/jarvis_vendor_outreach_stall_runner.py --apply --evening --lane all

# 強制 refill（レーン指定）
~/selenium_env/venv/bin/python scripts/jarvis_vendor_outreach_stall_runner.py --apply --lane s4 --force-refill

# KURASHIFT ジョブ（任意）
# job_type=re_vendor_stall_check  payload: { "lane": "all", "daily_report": true }
```

詳細: `docs/運用コマンド一覧.md`「業者開拓閉ループ」節。

## 7. 改善ログ

| 日付 | 内容 |
|---|---|
| 2026-10-09 | Phase C スタブ作成（ID 516） |
| 2026-10-15 | 閉ループ設計実装。stall runner・合図・日次 Slack・設計中へ |
| 2026-10-15 | S4/S9 を同型追加（`--lane` · sync_meta 分割 · UI stall 行） |
| 2026-10-15 | Phase D: `--apply --lane all --evening`・sync_meta・#report/#ops。B1 手渡しフォルダ |
| 2026-10-15 | Phase1〜3 伴走確認。一度運用へ上げたが、格上げ条件確定で **運用確認** に戻す（週1健全×2週） |
| 2026-10-15 | Slack本文先頭 `[516]`。格上げ正本: `docs/promote-to-ops.md` |
| 2026-10-15 | Slack: Grokサポート見守りタイトル・週次 #report／即時 #ops。KURASHIFT kicker 揃え |
