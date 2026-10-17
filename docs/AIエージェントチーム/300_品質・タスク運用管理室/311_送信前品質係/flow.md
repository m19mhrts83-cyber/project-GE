# フロー — 送信前品質係

DXデモ用に **変更前フローは残す**。本線は改訂版。入口は [README.md](./README.md)。

| 版 | FlowForge | 開始トリガー |
|---|---|---|
| **改訂版（本線）** | [flow_x4Sw8mVvuGVme1fXz9JGfs3v](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_x4Sw8mVvuGVme1fXz9JGfs3v) | **イベント／都度起動** — 下書きパス受領（入口 A／B） |
| 変更前（デモ） | [flow_AKQv6lgUEtudWlE5fQUhQnh2](https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_AKQv6lgUEtudWlE5fQUhQnh2) | 定期 毎日18:00（捨てた設計） |

## 型（改訂版・2026-10-17）

設計の理解: **トリガーは A と B** → **合流して同じゲート** → 点検 → Slack。  
次の担当は **AI（人待ちなし）**。人が見るのは図の外（送信直前 outbound-confirm）。

```text
開始（イベント／都度起動・パス受領）
        ├─ 経路A: inbox MD（input/）→ poll／Jarvis が拾う  ──┐  次の担当=AI
        └─ 経路B: CLI 直接（--draft --source）            ──┤  次の担当=AI
                                                             ▼
                                              合流: 311ゲートCLI（担当=AI／人待ちなし）
                                                             ▼
                                              下書き読込 → 点検1〜3 → 総合判定
                                                             ▼
                                              OK→#report ／ NG→#consult
```

| 経路 | 誰向け | 入口 | 次は誰？ |
|---|---|---|---|
| **A** | S9／ホーク（簡単） | `input/` に短い MD | **AI**（launchd 15分 poll → CLI。人間ノードなし） |
| **B** | 211 GHA・手動 | CLI 直呼び | **AI**（そのままゲート。人間ノードなし） |
| 合流後 | 共通 | 同じ点検〜Slack | **AI** |
| 送信 | 図の外 | outbound-confirm | **人**（送信ボタンのみ） |

入口だけ分岐。点検以降は共通。本文は渡さず `draft_path`＋`source` のみ。

FlowForge 上のノード文言（開始／A／B／合流・「次はAI」）が設計の正。矢印が崩れても **上表の担当** を正とする（必要なら開始→A／開始→B→合流を手でつなぎ直し）。

## 手順メモ

- 18時スケジュールは保険にも使わない（送った後ではゲートにならない）
- 「これで送ってOK」があるまで送信系コマンドは走らせない（outbound-confirm）
- FlowForge は設計図。実行の正は `jarvis_send_gate_311.py` ＋ launchd `send-gate-311-inbox-poll`（経路A）／CLI・GHA（経路B）
- Phase 2〜3 済（2026-10-18）: poll ＋ 上流 enqueue（211／ホーク action）
