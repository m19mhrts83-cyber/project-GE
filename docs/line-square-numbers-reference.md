# LINE / Square（オープンチャット）— 数字の意味早見表

パートナー確認・オプチャ同期のログや API エラーで出る **件数** と **エラーコード** を整理する。  
同じ数字でも文脈で意味が違う（例: **503** は件数にも API コードにもなる）。

**正本**: 実装は `line_unofficial_poc/chrline_open_chat_to_md.py` / `chrline_client_utils.py` / CHRLINE-Patch `SquareErrorCode`。

---

## 1. まず見分ける

| 種類 | 例 | どこに出るか |
|---|---|---|
| **件数（カウント）** | 503, 446, 466, 37, skipped=70 | `# thread diff:` / `# thread sync:` / YAML 件数 |
| **Square API エラーコード** | 401, 403, 404, 410, 503 | `SquareException: Code: 401` 等 |
| **LINE ログイン・セッション** | 8, 100, HTTP 403 | QR ログイン、`V3_TOKEN_CLIENT_LOGGED_OUT`、`refreshToken` |
| **state の health** | ok / degraded / closed | `.chrline_open_chat_state.json` |

---

## 2. ログに出る件数（運用カウント）

### 2.1 `# thread diff:` 行

```
# thread diff: YAML登録 503 件のうち 取得可能 503 件を対象（閉鎖済みスキップ 0 件）
```

| 数字の位置 | 意味 |
|---|---|
| **YAML登録 N 件** | `open_chat_routes.yaml` の全ルート `thread_mids` 合計（現在 **503**） |
| **取得可能 M 件** | 上記のうち state が `closed` / `deleted` / `join_denied` でない件数（日常 fetch 対象） |
| **閉鎖済みスキップ K 件** | `YAML登録 − 取得可能`。誤 `closed` 解消後は **0** が正常 |

**ルート別内訳（2026-07-05 時点）**

| ルート | thread_mids |
|---|---:|
| 30空室相談G | 70 |
| 34保険相談G | 34 |
| 33融資相談G | 190 |
| 31修繕相談G | 134 |
| 12東海北陸G | 75 |
| **合計** | **503** |

### 2.2 `# thread sync:` 行

```
# thread sync: total=503 ok=503 skipped=0 closed=0 degraded=0 deleted=0 appended=0
```

| フィールド | 意味 |
|---|---|
| **total** | 今回ループしたスレッド数（通常 = 取得可能件数） |
| **ok** | fetch 成功し state を `ok` に更新した件数 |
| **skipped** | `closed` 等で **fetch せず飛ばした** 件数 |
| **closed** | 今回の実行で新たに `closed` 化した件数 |
| **degraded** | 一時失敗で `degraded` にした件数 |
| **deleted** | 404 等で `deleted` にした件数 |
| **appended** | `5.やり取り.md` に **新規追記したメッセージ件数**（0 でも同期成功のことが多い） |

### 2.3 過去ログ・ドキュメントに残っている件数（歴史的参考）

復旧作業前の数字。**現在は 503 件すべて取得可能**。

| 件数 | 意味 |
|---|---|
| **503** | YAML 登録スレッド総数（変わらず正本） |
| **446** | 30空室を 70 に戻す**前**の登録合計（13+34+190+134+75） |
| **37** | 復旧前に state 上 `degraded` で再試行可能だった件数の目安 |
| **466** | 復旧前の「閉鎖済みスキップ」例（503−37）。誤 `join_denied` が主因 |
| **70** | 30空室のスレッド登録数（13 本番 + 57 archived 復帰後） |
| **57** | 30空室で一度 archived に退避した MID 数（再 probe で全件 OK→復帰） |
| **13** | 30空室の初回 probe で OK だった件数（一時的に日常対象を絞った時期） |

### 2.4 probe 結果行

```
# thread probe 結果: ok=34 ng=0 total=34
# archived probe 結果: ok=57 ng=0 total=57
```

| フィールド | 意味 |
|---|---|
| **ok** | `fetchSquareChatEvents` が **1件テストで成功** したスレッド数 |
| **ng** | 同上 **失敗**（多くは 401 permission） |
| **total** | 対象スレッド総数 |

**ng > 0** の MID は `thread_mids_archived` 退避の候補。**ng=0 なら YAML 整理不要**。

### 2.5 その他の定常カウント

| 数字 | 意味 |
|---|---|
| **retryキュー 43** | Tcell 等グループ LINE の E2EE 復号リトライ待ち（`LINE本文ヘルス`） |
| **プレースホルダー 8** | MD 上 `[本文なし]` 等で本文未取得の行数（公式エクスポート推奨の目安） |
| **6 ルート** | オプチャ YAML のメイン同期対象グループ数（01〜34 等） |

---

## 3. Square API エラーコード（CHRLINE `SquareErrorCode`）

ログ例: `SquareException: Code: 401, Message: ...` / `don't have permission`

| Code | 定数名 | 意味 | Jarvis での典型対応 |
|---:|---|---|---|
| **400** | ILLEGAL_ARGUMENT | 引数不正 | thread_mid / chat_mid の typo、空 token 等を確認 |
| **401** | AUTHENTICATION_FAILURE | **権限なし・認可失敗** | 未参加スレッド、30日制限、**セッション切れ**、旧 CHRLINE バージョン。sync_token リセット→再試行。誤判定で `closed` 化しない（2026-07 修正済み） |
| **403** | FORBIDDEN | 禁止（参加・操作不可） | join 不可、オプチャポリシー |
| **404** | NOT_FOUND | スレッド削除・不存在 | state を `deleted`、日常スキップ |
| **409** | REVISION_MISMATCH | 版数不一致 | 稀。再 fetch |
| **410** | PRECONDITION_FAILED | 前提不一致（古い token 等） | sync/continuation リセット後に再試行 |
| **500** | INTERNAL_ERROR | サーバー内部エラー | 時間をおいて再試行 |
| **501** | NOT_IMPLEMENTED | 未実装 API | `iter_threads` 等。YAML 登録運用で回避 |
| **503** | TRY_AGAIN_LATER | **一時障害・混雑** | スロットル（`LINE_CHRLINE_CALL_INTERVAL_MS`）・後で再試行。**件数の 503 とは別** |
| **505** | MAINTENANCE | メンテナンス | 待つ |
| **506** | NO_PRESENCE_EXISTS | プレゼンスなし | 稀 |

### 401 と「LINE で見えるのに取れない」

| 原因 | API | アプリ上 |
|---|---|---|
| スレッド未参加・30日超 | 401 になりやすい | 見えない／参加できない |
| 誤 `closed:join_denied`（旧ロジック） | fetch していない | **見えるのに Jarvis がスキップ** → reopen + probe で解消 |
| セッション失効 | 401 または code 8 | 再 QR |

---

## 4. LINE ログイン・Talk API（Square 以外）

| Code / 文言 | 意味 | 対応 |
|---|---|---|
| **8** / `V3_TOKEN_CLIENT_LOGGED_OUT` | セッション切断 | 同一プロセス内 `recover_session_midrun`、ダメなら QR（`--allow-qr-login`） |
| **100** / `行動條碼過期` | QR 期限切れ | LINE アプリで再スキャン |
| **HTTP 403**（refreshToken） | 保存トークン無効 | QR 再ログイン。別プロセスでトークン再利用は不安定→ **1プロセス統合**（`chrline_yoritoori_inbox_fetch.py`） |
| **EOFError**（E2EE 復号） | グループ LINE 暗号化メッセージ | retry キュー。本文は **公式エクスポート** が正本 |

---

## 5. state `health.status`（`.chrline_open_chat_state.json`）

| status | 意味 | 日常差分 |
|---|---|---|
| **ok** | 取得成功履歴あり・監視中 | ✅ 対象 |
| **degraded** | 一時失敗（401 等）。`skip_until` でバックオフ | ✅ `--heal-degraded-threads` で再試行 |
| **closed** | 恒久スキップ扱い。`closed_reason` 参照 | ❌ スキップ（`--include-closed-threads` でのみ再スキャン） |
| **deleted** | 404 系 | ❌ スキップ |

| closed_reason | 意味 |
|---|---|
| **join_denied** | join 失敗＋fetch 401 で閉じた（**誤判定が多かった**）→ reopen 対象 |
| **degraded** | 旧: 401 で closed 化（セッション誤判定）→ `_reopen_false_closed_threads` 対象 |

---

## 6. 見たときの早見（フロー）

```
数字がログの total=/ok=/skipped=  →  §2 件数
「Code: 401」permission            →  §3 401（権限・参加・セッション）
「Code: 503」TRY_AGAIN             →  §3 503（再試行・スロットル）
「LOGGED_OUT」/ Code: 8            →  §4 セッション切れ
「YAML登録 503」                    →  §2.1 登録スレッド総数
「閉鎖済みスキップ 466」            →  §2.3 旧運用（今は 0 が正常）
```

---

## 7. 関連ファイル

| 役割 | パス |
|---|---|
| 運用コマンド | `docs/運用コマンド一覧.md` §4 |
| probe 状態 | `.jarvis_state/square_probe.json` |
| ルート定義 | `line_unofficial_poc/open_chat_routes.yaml` |
| スレッド state | `line_unofficial_poc/.line_auth/.chrline_open_chat_state.json` |

**更新履歴**

| 日付 | 内容 |
|---|---|
| 2026-07-05 | 初版。503 日常同期・401 誤 closed 復旧後の件数整理 |
