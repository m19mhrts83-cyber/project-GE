# 618 フェーズ3：実装・検証結果

> 2026-11-14追記：了承済みの本番反映と画面・権限確認が完了。最新状態はdeploy_report.md。以下の未適用記述は設計・実装段階の記録。実画像取得と新runの照合は次の実行時に確認。
2026-11-14 / Codex / `codex/618-phase1-report`

## 現在の状態

隔離worktreeで実装・ローカル検証まで完了。本番DB・Storage・公開中のKURASHIFT・定期ジョブは未変更。金融機関ログイン・OTP・実画像取得・Slack投稿は行っていない。

実装場所：`/Users/matsunomasaharu2/Documents/Codex/2026-11-14/https-app-todoist-com-app-task/work/618-phase1`

## 何ができるようになったか

1. 数値保存の直後に、口座・記録日・金額・取得元（原価があれば原価も）をDBから読み戻して一致を確認する。失敗・欠落・違う値は成功にしない。銀行グループも対象別に読戻し結果・未取得を残す。
2. 新しく取得されたPNGに、今回の取得時間帯・実行ID・ハッシュを付ける。古いdebug画像・ログイン未完了時の画像・env評価額メモ・残債JSONから作った画像を、正常な金融機関画面の証拠へ自動昇格させない。
3. 名義・契約・正常画面・元データ基準日を確認した画像だけ、非公開Storageへ保存する。アップロード後のバイト照合とDBの参照読戻しを確認する。画像だけのための定期ログインや月別アーカイブは作らない。
4. KURASHIFT `/portfolio` に「618 資産記録」欄を追加。数値の読戻し確認件数、未取得・未確認、元データ日付が不明なことを表示する。「表示を照合して記録」で、実際に描画された口座別数値・日付をサーバーの保存結果と突合する。
5. KURASHIFT `/portfolio/evidence` に、撮影日時・元データ基準日・今回更新の成否・前回正常画像を表示する。所有者の認証付きAPIから配信し、署名URL・公開URLは発行しない。画像ハッシュ不一致も閲覧失敗として表示する。
6. Slack下書きに、数値読戻し・画像更新・当該実行の保存確認欄の照合結果を分けて載せる。未確認が残る場合は件数を保持し、部分一致を全体成功にしない。送信機能は追加していない。

JARVISは既存のKURASHIFTへの補助入口のまま。数値の二重転記や新しいJARVIS専用画面は増やしていない。配分・保険等の既存集計式は変更せず、追加した保存確認欄の一致と区別する。

## 最新正常画像を守る仕組み

- 非公開bucket：`asset-evidence`。
- 論理キー：所有者 × portfolio/liquidity × 口座 × 契約 × 画面。
- 実体：`618/latest/{owner_uuid}/{scope}/{account_id}/{contract_key}/{view_key}.{a|b}.png`。
- DB：`asset_evidence_latest` の参照先1件だけを「現在の正常画像」とする。
- 新しい画像を非アクティブ側にアップロード → ダウンロードしてハッシュ検証 → DB参照を切替 → DBを独立に読戻す。
- 更新失敗時は前回の正常画像・撮影日時・基準日を維持し、今回の更新失敗／更新確認待ちを別に表示する。差替え途中に既存の正常画像を上書きしない。
- 物理的には最大2スロットを交互利用し、閲覧可能なのは正常参照の1組。日付付き画像履歴を蓄積しない。非アクティブ側は次の差替えで再利用する。既存OneDrive/debug資料を削除・移動していない。
- DBのpending予約で別プロセスの横取りを拒否。中断でpendingが残った時は、実行者の停止確認と明示指示の後にだけrecoverする。時間だけでロックを奪わない。
- RLSは所有者のみ。別の登録ユーザーにも他人の証拠を見せない。既存の広いStorageポリシーがあっても、当bucketの読取とクライアント書込は制限する。

## 判断が必要な点と入口

最新画像取得は音声・チャットで依頼、取り直しも人の依頼のみ。Slackは出口専用。新しい窓口・Slackリアクション監視はない。

画像の鮮度（今回のファイルか・改変されていないか）はプログラムで確認する。名義・契約・元データ基準日が既存取得器から確実に分からない画像は確認待ち。実行担当者が画像を確認し、明示的なreview manifestへ記録してから登録する。未確認フラグをtrueと推測して埋めない。判別できない時は本人判断と共通判断ログへ戻す。

画像取得の既定保存先は `~/Library/Logs/jarvis_portfolio/asset618-capture/latest`。Git内への出力を拒否。既存の明示指定出力先は利用可能だが、最新証拠の正本は登録後のSupabaseとする。

`--executor`の既定はcodex。銀行IB、および既存取得器がOTPを自動処理し得るAXA・あかつき・Sony・Prudentialは、Jarvis担当以外では呼ばずスキップする。今回これらの取得器を実行していない。画像登録プログラム自身はログインやOTPを行わない。

## 実行者向けの流れ

1. 既存 `jarvis_purchase_asset_evidence.py` で依頼された対象だけ取得する（銀行IB/OTP対象はJarvis）。`_capture_receipts.json` の候補を確認。
2. 正常画面・名義・契約・元日付を確認し、review manifestを用意する。画像ファイル・レシート・manifestはGit/クラウド同期へ載せない。
3. `jarvis_asset_618_evidence.py --manifest <private.json> --owner-id <登録済みID>` でプレビュー。`--apply`でのみ保存する。共通実行ロックと採用済み判断ログを取得する。
4. 既存の数値収集後は、KURASHIFTの保存確認欄を開き「表示を照合して記録」。実行記録が変わった場合や値が違う場合は記録しない。
5. `jarvis_asset_618_report.py --read-db` で下書きを作る。画像結果も合わせる場合は `--image-run <asset618-runs/UUID.json>` を指定する。Slack実送信は宛先・本文の了承後。

review manifestの書式：

```json
{
  "capture_receipts": "/private/path/_capture_receipts.json",
  "items": [{
    "artifact_index": 0,
    "account_scope": "portfolio",
    "account_id": "sbi_index",
    "contract_key": "primary",
    "view_key": "balance",
    "source_as_of": "2026-11-14",
    "reviewed_by": "owner",
    "validation": {
      "normal_page": true,
      "account_match": true,
      "contract_match": true,
      "source_date_match": true
    }
  }]
}
```

これは書式例であり、今回の実画面を確認した記録ではない。確認していない画像を登録しない。

数値のas_ofは既存DB列を維持する。取得元の基準日が確かでない既存取得器は、記録日と元データ基準日を区別し、後者を未確認と表示する。取得日を元日付へ読み替えない。

## 検証した範囲

- Python：618関連84件、既存営業時間11件、共通判断契約4件（計99件）。
- TypeScript：共通判断契約10件、新しい読戻し・照合・画像API11件（計21件）。
- PostgreSQL/WASM：実際のSQL適用・RLS・予約／切替／失敗保持等16件。Supabaseのauth/storageを模した隔離スキーマで実行。
- ブラウザ：本番用ビルドをローカルで起動し、合成データのHTTP fixtureで12項目を確認。未認証拒否、別ユーザー拒否、画面→API→照合記録、表示改変拒否、DB変更拒否、前回画像保持、画像ハッシュ破損、DB障害、iPhone幅390px、JavaScriptエラーなし。
- **合計148項目が成功**。KURASHIFTの本番用ビルド、Python/zsh構文、差分空白チェックも成功。
- スクリーンショットは合成データのみ。実際の金融資産や認証値は使っていない。

本番Supabaseは読取のみ。新テーブル・bucketがまだないこと、既存ログイン利用者が1人であることを確認し、その利用者を登録するSQLを準備した。実画像アップロード、金融サイトの現行画面、実SupabaseのStorage配信、本番KURASHIFT画面でのE2Eは未実施。

## 本番適用の確認事項

実装・レビュー可能なSQL・所有者登録SQL・累積コード差分を準備済み。未コミット・未マージ。

1. PRでPhase 1–3の関連コードを確認し、必要なCIを通す。既存の無関係な変更3件を含めない。
2. 財務用Supabaseに `20261114_asset_618_evidence.sql` を適用。3テーブル・非公開bucket・RLS・書込RPCを追加する。既存数値の削除・変更や既存Storage公開化はしない。
3. 既存の唯一のKURASHIFT利用者を `asset_evidence_owners` へ登録する。新アカウントやパスワードは作らない。
4. KURASHIFTとMac側Python/runnerを反映。旧runnerが終了していることを確認してから切り替える。公開画面・RLS・画像APIを本番で確認する。
5. 実画像が必要な時は人の依頼を受け、担当境界に沿ってJarvis等が取得する。Slack投稿は別途宛先・本文の了承後。

本番適用前の了承が必要な根拠：リポジトリ `AGENTS.md` の起点文書 `docs/リポジトリ構成_地図_20261108.md` に「**本番 DB への適用は松野さんの了承を取ってから**」と明記されている。今回はフェーズ3のローカル実装・検証まで進め、実DBへの権限・Storage変更は実行していない。

## 再検証用ファイルと参考

- `scripts/tests/test_asset_618_evidence.py`、`test_asset_618_runtime.py`、`test_asset_618_report.py`。
- `scripts/tests/test_asset_618_migration.mjs`（PGLITE_MODULEにローカルのPGliteモジュールを指定）。PGliteは検証用workフォルダのみへ配置し、アプリの依存を増やしていない。
- `scripts/tests/asset_618_http_fixture.py`（localhost:6418）、`asset_618_browser_check.py`（localhost:6419）。Nextを同fixture用の匿名キー・URLで起動し、`ASSET618_TEST_OUT`で画面出力先を指定する。実サービスの鍵をfixtureへ渡さない。
- 実装上の確認：[Supabase private bucket](https://supabase.com/docs/guides/storage/buckets/fundamentals)、[Storage access control](https://supabase.com/docs/guides/storage/security/access-control)、[private download](https://supabase.com/docs/reference/javascript/file-buckets-download)。
- 検証DB：[PGlite API](https://pglite.dev/docs/api)。本番SupabaseのStorageエンジン自体の代替検証とは区別する。


本番反映前のCI修正：DB読戻しテストのimportでMac用Playwrightまで読まれていたため、liquidityのブラウザ依存をscrape_zaim実行時に遅延読込へ変更。ローカル全Python720件成功。CIと本番適用結果はdeploy_report.mdへ追記する。
