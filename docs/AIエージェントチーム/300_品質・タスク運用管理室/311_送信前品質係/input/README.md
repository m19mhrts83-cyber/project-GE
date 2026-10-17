# input/ — 311（経路 A: inbox MD）

上流（S9／ホーク等）または手動で短い依頼 MD を置く。  
**15分 poll**（`com.matsunoma.jarvis.send-gate-311-inbox-poll`）が拾ってゲート→Slack。

## ファイル名

| 名前 | 扱い |
|---|---|
| `README.md` / `example*` | **スキップ**（見本） |
| その他 `*.md` | 処理対象 → 完了後 `processed/` へ |

## 最小フィールド

```yaml
---
draft_path: /絶対パス/4.送信下書き.txt
source: hawk   # s9 | 211 | hawk | s2 | manual
partner_or_thread: （任意）
---
```

本文は書かない（下書き正本を 311 が読む）。

## 手動1回

Jarvis／手元から `--from-inbox --dry-run` または `--post`。

## 上流からの書き方（Phase 3）

| 誰 | 方法 |
|---|---|
| 211 | 朝便が自動 `--enqueue`（手動不要） |
| ホーク／S9 | Drive inbox に `action: send_gate_311`（bucho poll）または CLI `--enqueue` |
| 手動 | このフォルダに MD を置く／CLI `--enqueue` |

詳細: [`docs/phase3-upstream.md`](../docs/phase3-upstream.md)

## 経路 B

CLI 直呼び（`--draft --post`）。このフォルダは使わない。
