# Jarvis データ流れ — WeStudy とパートナーやり取り／LINEオプチャ

最終更新: 2026-09-12

## 二系統（混ぜない）

| 系統 | 正本 | 検索公開 | 用途 |
|---|---|---|---|
| **WeStudy コミュニティ** | Supabase `kamiooya-qa.comments` | 週次 GHA 取込後すぐ検索対象 | Q&A 準拠「関連コミュニティ投稿」 |
| **WeStudy セミナー／lesson** | `knowledge_*` / lesson 行 | 既存どおり | 準拠のセミナー／動画ページ説明 |
| **LINE オープンチャット** | OneDrive `815_*/5.やり取り.md` → `line_openchat_logs` | **日次** sync（staging）→ **publish（ready）** | Q&A 準拠第4「関連LINEオプチャ」＋タブ |
| **823 幹事（東海飲み会）** | OneDrive `823_名古屋幹事グループ/5.やり取り.md` | 検索公開しない | LINE＋Chatwork 一本化。815 外 |
| **パートナーやり取り** | OneDrive `26_パートナー社…/5.やり取り.md` | 検索公開しない | ダッシュは要返信投影。全文ビューアではない |

## LINE オプチャの流れ

```
CHRLINE → 815 5.やり取り.md（見出しに日時 YYYY/MM/DD HH:MM）
       → jarvis_kurashift_openchat_sync.py --apply（staging・漏れなく）
       → jarvis_openchat_publish.py --apply（ほぼ全件 ready／ノイズのみ excluded）
       → Edge semantic-search（relatedOpenchat）＋ Raimo タブ／準拠第4
```

- **comments にマージしない**
- 物件紹介ルートごと切らない（チラシ定型文だけ excluded）
- WeStudy 週次 GHA には載せない（Mac／CHRLINE）

## メールトリアージ（参考）

- 夜＝パートナー **Gmail＋CW／LINE／iMessage** と admin general の判定＋下書き。815 は要約のみ
- 既読は取込時／閉じた後。自動送信なし
- `--apply-draft` はチャネル別ファイル（`4.送信下書き` / `4.LINE送信下書き` / `4.Chatwork送信下書き`）

## コマンド

`docs/運用コマンド一覧.md` の「神大家オプチャ → kamiooya-qa」節。
