# KURASHIFT Tier3 自動送信 — 有効化手順

**更新**: 2026-08-25  
**正本 YAML**: `config/kurashift_re_inquiry_auto.yaml`  
**worker**: `scripts/jarvis_kurashift_re_tier3_auto_send.py`  
**進捗**: `docs/KURASHIFT_問合せパイプライン_進捗_20260823.md`

## 前提（満たしてから）

1. Tier1 手動お試し送信＋`--poll-replies` が通っている  
2. Tier2 `/realestate/deals/tier2` の一括確認運用が安定している  
3. ユーザーがチャットで **「Tier3 を有効にしてよい」** と明示同意した（Jarvis は同意なしで ON にしない）

推奨ゲート（目安）: 送信累計 10・返信 3・Tier2 レビュー済み。問合せ自体は費用ゼロだが **対外送信**のため同意は必須。

## 有効化手順

1. YAML を編集:

```yaml
tier3_auto_send:
  enabled: true
```

2. 候補確認（送信しない）:

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_tier3_auto_send.py
```

3. 実送信（enabled=true のときのみ）:

```bash
~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_tier3_auto_send.py --i-confirm-send
```

4. 朝バンドルに載せる場合は `jarvis_morning_mac_refresh` へ呼び出しを追加（enabled 時のみ）。未配線でも手動実行可。

5. 進捗 doc と生きている plan の `tier3-gate` を更新。フォロー state に完了を記録。

## 無効化

```yaml
tier3_auto_send:
  enabled: false
```

## しきい値（現行）

| 条件 | 値 |
|---|---|
| Grok 聞く価値 | 聞く |
| match_score | ≥ 7.0 |
| hazard_eval | OK |
| land100 | 見送り以外 |
| 日次 cap | `daily_send_cap`（Tier1+2+3 合算目安） |

## 失敗時

- 送信失敗は digest / deals に残り、Tier1 手動ボタンで再送可  
- 宛先なし・`not_applicable` はスキップ（Grok handoff は preview の to を使用）
