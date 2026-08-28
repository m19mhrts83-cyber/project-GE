# Grok ↔ Jarvis — JarvisBox フォーク原則（正本）

**更新**: 2026-08-28  
**Drive**: admin `【with Grok bot】/` · 設定: `config/kurashift_grok_bridge_folders.yaml`

## フォーク（基本形）

| 側 | 役割 | 本体 |
|---|---|---|
| **Grok** | 整理 · 委譲 · 助言 · 文案 · ルーティン実行 · 日報メール | Grok Bot / チャンネル |
| **Jarvis** | Mac 実行 · 取込 · DB · 送信承認 · 秘密 · launchd | Cursor / Mac |

**松野がチャットをコピペしなくてよい** — 運用上のやり取りは **Drive JarvisBox 必須**。

## 必ず JarvisBox 経由（正）

| 向き | フォルダ | 書く人 | 読む人 |
|---|---|---|---|
| Jarvis → Grok | `20_outbox_to_grok/`（`target:` 付） | Jarvis | ホークアイ → 各 `outbox_to_teams/*/` |
| Jarvis → 部長／統括 | `outbox_to_teams/{re,resource,…}/` | Jarvis（`--target`） | 該当 Bot ルーティン先読み |
| Grok → Jarvis | `10_inbox_from_grok/` | **部長 · 各統括**（完了・依頼・メモ） | Jarvis poll（15分） |
| 済 | `90_archive/` | 処理後 | 参照 |

`30_shared_working/` は **手順 · B1 正本**。日常キューは **inbox / outbox / team フォルダ**。

## Grok Bot Instructions に載せる一文（統括・部長）

```
## Jarvis への共有（必須 · フォーク）

- Mac 実行・取込・送信・秘密は **Jarvis**。あなたは Grok 内で完結させ、結果を Drive へ書く。
- Jarvis に伝えること（完了 · 依頼 · 長メモ）は **必ず** admin Drive
  `【with Grok bot】/10_inbox_from_grok/` に `YYYY-MM-DD_題名.md`。
- 先頭 YAML 推奨: `action:` / `priority:` / `target: jarvis`
- **松野にチャット全文コピーを求めない**（JarvisBox が正本）。
```

サブ Bot（コーチ・アドバイザー）は **統括 Bot 経由**でよい。統括が inbox にまとめる。

## Jarvis の動作（必須）

1. Grok へ依頼・結果共有 → `jarvis_bucho_outbox_write.py --target …`（チャットだけで終わらない）
2. Grok inbox 未処理 → `jarvis_bucho_inbox_poll.py`（パートナー確認ついで可）
3. Instructions 更新 → git `config/grok_*_paste.md` → Drive `B1_*_全文.txt` 再生成を案内

## 例外（JarvisBox 以外の正本）

| 種類 | 正本 |
|---|---|
| `[Grok部長]` 日報 / 夕方 / 週次 | **estate Gmail** → Jarvis 取込 |
| `[Grok調査]` 等社員成果 | **estate Gmail** |
| 急ぎ Jarvis 依頼（任意） | estate 件名 `[Jarvis依頼] …` |
| 天気 ch 直投 | `outbox_to_teams/weather/` → 天気Bot（ホーク日次報告不要） |

## 関連

- 索引: `config/grok_org_handoff_index.md`
- ホーク L2: `config/grok_hawk_routine_Jarvisボックス.md`
- Jarvis ルール: `.cursor/rules/jarvis-grok-jarvisbox-fork.mdc`
