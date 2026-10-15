# KURASHIFT 業者開拓 — 間に落ちない閉ループ（2026-10-15）

## 背景

ホーク週次で判明した停滞: Grok S2 は探索できるが、Jarvis の `--next 3`／週次バッチ JSON が Mac 未接続・inbox 未処理で届かず **送信0** が続いた。再生成依頼 MD の洪水も効かない。

## 方針（4点）

| 柱 | 内容 |
|---|---|
| 入口 | YAML `kurashift_re_vendor_list.yaml`／部長 `--mark`／outbox `s2_batch` |
| 確認 | 対外送信は人／Grok。キュー補給・sync・Slack は自律可 |
| 履歴 | YAML status · KURASHIFT · Slack `#report` · 要ボスのみ Todoist |
| 停止 | `vendor_outreach_stall.json` disabled / `JARVIS_VENDOR_OUTREACH_STALL_DISABLE=1` |

## 役割分担

| 誰 | やること |
|---|---|
| **stall runner（Jarvis）** | 枯渇検知・`--batch-week` 相当を `outbox_to_teams/re` へ・inbox 依頼 archive・vendor_sync・`sync_meta`・障害 `#ops` |
| **516 業者開拓フォロー係** | 合図（時間／届いた／失敗見回り）・日次 `#report`・手順正本 |
| **Grok S2** | Web 送信・`--mark`。キュー薄いときは **再依頼しない**（自律 refill 待ち） |
| **不動産部長** | 日報メールに `--mark` 集約。再生成依頼 MD を書かない |
| **ホーク** | 週次横断。日次件数は 516 |

## コマンド

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_vendor_outreach_stall_runner.py --apply
~/selenium_env/venv/bin/python scripts/jarvis_vendor_outreach_stall_runner.py --apply --evening
~/selenium_env/venv/bin/python scripts/jarvis_vendor_outreach_stall_runner.py --apply --force-refill
```

相乗り: `jarvis_morning_mac_refresh`（朝）／`jarvis_bucho_inbox_poll`（inbox 後）。  
UI: `/realestate/vendors` · ジョブ `re_vendor_stall_check`。

## 受け入れ

1. キューが薄くても依頼 MD なしで outbox に kickoff が載る  
2. 夕方 `#report` に件数サマリ  
3. vendors 画面で stall／キュー残が見える  
4. Mac 未接続時は送信を捏造せず `#ops`  

## 関連

- 社員: `docs/AIエージェントチーム/500_不動産パイプライン実行室/516_業者開拓フォロー係/`
- paste: `config/grok_vendor_outreach_bot_grok_paste.md` · `config/grok_realestate_bucho_grok_paste.md`
- 運用: `docs/運用コマンド一覧.md`「業者開拓閉ループ」
- 実務設計（既存）: `docs/KURASHIFT_RE_業者開拓_物件候補_実務者設計_20260823.md`
