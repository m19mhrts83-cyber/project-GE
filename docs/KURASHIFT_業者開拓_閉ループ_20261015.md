# KURASHIFT 業者開拓 — 間に落ちない閉ループ（2026-10-15）

## 背景

ホーク週次で判明した停滞: Grok S2 は探索できるが、Jarvis の `--next 3`／週次バッチ JSON が Mac 未接続・inbox 未処理で届かず **送信0** が続いた。再生成依頼 MD の洪水も効かない。  
S4（修繕）・S9（管理会社）も同じ「Mac 側手渡し」がボトルネックになりうるため、**同型の stall runner** で閉じる。

## 方針（4点）

| 柱 | 内容 |
|---|---|
| 入口 | YAML（S2/S4/S9 各リスト）／部長 `--mark`／outbox `s2_batch` · `s4_queue` · `s9_precheck` |
| 確認 | 対外送信は人／Grok。キュー補給・sync・Slack は自律可 |
| 履歴 | YAML status · KURASHIFT · Slack `#report` · 要ボスのみ Todoist |
| 停止 | `vendor_outreach_stall.json` disabled / `JARVIS_VENDOR_OUTREACH_STALL_DISABLE=1` |

## レーン

| lane | 役割 | outbox action | sync_meta key | UI |
|---|---|---|---|---|
| **s2** | 地場物件紹介 | `s2_batch` | `vendor_outreach_stall` | `/realestate/vendors` |
| **s4** | 修繕業者 | `s4_queue` | `vendor_outreach_stall_s4` | `/realestate/repair-vendors` |
| **s9** | 管理会社 | `s9_precheck` | `vendor_outreach_stall_s9` | `/realestate/mgmt-vendors` |

既定実行は `--lane all`（朝 refresh／inbox poll／夕方 mark 後）。

## 役割分担

| 誰 | やること |
|---|---|
| **stall runner（Jarvis）** | 枯渇検知・outbox へ kickoff・inbox 依頼 archive・各 sync・`sync_meta`・障害 `#ops` |
| **516 業者開拓フォロー係** | 合図（時間／届いた／失敗見回り）・日次 `#report`・手順正本 |
| **Grok S2/S4/S9** | Web 送信・`--mark`。キュー薄いときは **再依頼しない**（自律 refill 待ち） |
| **不動産部長** | 日報メールに `--mark` 集約。再生成依頼 MD を書かない |
| **ホーク** | 週次横断。日次件数は 516 |

## コマンド

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_vendor_outreach_stall_runner.py --dry-run --lane all
~/selenium_env/venv/bin/python scripts/jarvis_vendor_outreach_stall_runner.py --apply --lane all
~/selenium_env/venv/bin/python scripts/jarvis_vendor_outreach_stall_runner.py --apply --evening --lane all
~/selenium_env/venv/bin/python scripts/jarvis_vendor_outreach_stall_runner.py --apply --lane s9 --force-refill
```

相乗り: `jarvis_morning_mac_refresh`（朝・`--lane all`）／`jarvis_bucho_inbox_poll`（inbox 後）／部長 mark 夕方。  
ジョブ: `re_vendor_stall_check`（payload `lane`: `s2`｜`s4`｜`s9`｜`all`）。

## 受け入れ

1. キューが薄くても依頼 MD なしで outbox に kickoff が載る（S2/S4/S9）  
2. 夕方 `#report` に件数サマリ（レーン横断）  
3. 各 UI で stall／キュー残が見える  
4. Mac 未接続時は送信を捏造せず `#ops`  

## 関連

- 社員: `docs/AIエージェントチーム/500_不動産パイプライン実行室/516_業者開拓フォロー係/`
- paste: `config/grok_vendor_outreach_bot_grok_paste.md` · `config/grok_realestate_bucho_grok_paste.md`
- 運用: `docs/運用コマンド一覧.md`「業者開拓閉ループ」
- 実務設計（既存）: `docs/KURASHIFT_RE_業者開拓_物件候補_実務者設計_20260823.md`
