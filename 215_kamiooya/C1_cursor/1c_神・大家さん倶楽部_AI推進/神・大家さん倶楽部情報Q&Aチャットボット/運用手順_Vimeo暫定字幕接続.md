# Vimeo自動字幕の暫定検索接続

更新: 2026-10-27 / FRIDAY

## 方針

松野さんの2026-10-27依頼により、運営正本の到着を待たず、取得済みVimeo字幕を暫定ソースとして検索に利用する。運営字幕が最終正本であることは維持する。

現状理解の参照: [神大家AI推進 第3回（2026-10-28）](https://m19mhrts83-cyber.github.io/project-GE/docs/kamiooya-ai-03.html)。全85レッスンのうち動画なし4を除外した81が母数、字幕取得済み63・動画あり字幕未取得18。旧manifestの `desc_only=22` は動画なし4を含むので、運営への依頼本数と混同しない。1レッスンに複数動画を含むため、本スクリプトの `videos` は63と一致する指標ではない。

本編14〜17ページの方針も確認済み。未取得18本は本編・判断9本を優先、SRT/NottaまたはVimeo日本語字幕の付与で補完する。共有フォルダ・受渡形式・月1回取込は運営とのすり合わせ対象。資料16ページの「今後の動画は自動反映」は目指す運用であり、この変更だけでは定期取得を新設しない（取得済みMD→検索接続の手動実行を整備）。

- 正本参照先: Supabase `kamiooya-qa` / `knowledge_sources`・`knowledge_chunks`。
- 通常検索・文字起こし一覧: Raimo miniApp 1346 の同名テーブルへミラーする。
- 意味検索: Supabaseの768次元embeddingを既存Edge `semantic-search`で検索。
- （2026-10-27 廃止）タイトル先頭の `【Vimeo自動字幕・暫定】`。自動字幕の固有名詞・数字は元動画で確認する。
- レッスン内の動画をVimeo IDごとに分離し、開始秒を保持する。説明文だけのレッスンは字幕として取り込まない。

## 2026-10-27 方針変更（松野さん）

- 「暫定」の識別は利用者に見せない。取得済みVimeo字幕を上長に確認してもらい、問題なければそのまま使う。運営には字幕が取れなかった分だけ共有を依頼する。
- 新規取込のタイトルには `【Vimeo自動字幕・暫定】` を付けない。既存89ソースのタイトルはSQLの UPDATE 1回で外す（全件の再取込はしない。Supabase Free の通信量を抑えるため）。アプリ・回答生成側でも接頭辞を表示しない。
- `meta_json.transcript_provider=vimeo_auto` と `provisional` は内部管理用に残す（運営字幕が届いた動画の差し替え判定に使う）。
- 回答本文には、セミナー動画の内容を使った文の末尾に（動画タイトル 12:34頃）を付ける。関連セミナー動画の欄は、時刻ごとに話している内容の抜粋と、その位置から再生するリンクを表示する。

## 実行

リポジトリルートで実行（認証情報は内部読取、ログに値を出さない）。

```sh
# プレビュー（既定はOneDrive Graphから取得。Macのオンライン専用ファイルにも対応）
~/selenium_env/venv/bin/python '215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/scripts/import_vimeo_transcripts.py' --slug step1_1

# Supabase・embedding・通常検索用Raimoの両方へ接続
~/selenium_env/venv/bin/python '215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/scripts/import_vimeo_transcripts.py' --apply --embed --mirror-raimo
```

追加コースは `--manifest /path/to/manifest.json --course 応用 --graph-root OneDrive上のフォルダ` を指定。manifestには `lessons: [{slug,title,url,jarvis_file}]` を用意し、既存と同じ字幕MD形式を使う。ローカルMDは `--input-dir` でも可。

## 再実行・差し替え

- `westudy:{lesson_slug}:vimeo:{video_id}` が動画の安定キー。チャンクは開始秒＋本文ハッシュ。
- 同じMDの再実行は不足チャンク・未付与embeddingのみ追加。既存字幕を削除しない。
- 非暫定の既存ソースは上書きしない。元MDの内容が変わった場合は停止し、人が差し替え範囲を確認する。
- 運営正本が届いたら、同じ動画の対応を照合し、暫定ソースの置換・撤去とRaimo同期を別途行う。現時点で正本への自動昇格はしない。
- 旧 `westudy_transcript_compare` は比較メタデータのみで本文を持たず、Q&A検索先ではない。

## 検証

字幕なしは0件、複数動画の時計リセット、安定キーを `scripts/tests/test_import_vimeo_transcripts.py` で検証する。接続後はSupabaseとRaimoの動画・チャンク数、通常検索の準拠、意味検索の `relatedChunks`・`relatedSources` を確認する。

```sh
~/selenium_env/venv/bin/python '215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/scripts/verify_vimeo_transcripts.py'
```

字幕ありレッスンの欠損、Raimoの欠損・余剰、未付与embeddingがあれば終了コード1。読み取りだけを行い、字幕本文・認証情報は出力しない。

### 2026-10-27 接続テスト

- 85レッスン走査、字幕あり63レッスン内89動画・2,712チャンクの取込処理完了。説明文のみ22レッスンは字幕として取り込まない。
- 全件照合成功: 63/63レッスン、Supabase/Raimoとも2,712チャンク、欠損0・余剰0・Vimeo embedding未付与0（`verify_vimeo_transcripts.py` 終了0）。
- STEP1再実行: 52チャンクに対しSupabase追加0、Raimo追加0（二重登録なし）。
- 公開アプリの実JSをPlaywrightで実行し、文字起こし一覧の読込・準拠パネルの暫定タイトル・開始秒・「DBで見る」を確認。
- Edgeの回答生成テスト: 目標設定／市場調査の質問でVimeo12チャンクがヒットし、12件とも回答コンテキストに採用、回答1642文字。
- 新規テスト5件・既存Nottaテスト6件成功。ダッシュボード `npm run build` と型チェック成功。
- 通常検索の回答生成E2Eはアプリ用ログイン資格情報が空のため未実施。Raimoの検索対象テーブルへの反映と公開フロントの引用描画までは確認済み。
- データは既存公開アプリに即時反映。2026-10-27 松野依頼で変更をコミットし、最新mainと統合してorigin/mainへpush済み（実装コミット `aa0c3c1b`、統合 `64702a65`）。

## 字幕の誤記補正（2026-10-26）

コメント・LINEオプチャ・動画説明文に一度も出ない字幕の語を拾い、189件の補正表を作成。松野さんが全件承認（元表: Googleスプレッドシート「神大家 セミナー字幕 誤記候補リスト」、反映版は `config/kamiooya_transcript_corrections.tsv`）。

- 補正は左から最長一致。正しい語も照合対象に含め、「金融機関」の「金融機」や「雰囲気」の「雰囲」は置換しない。
- Supabase本番: 73動画・1,229チャンクの `content`・`search_text`・`content_hash` を更新。`chunk_key` は変えない。元の本文は `kc_typo_backup_20261026`（RLS有効）に保存。対象動画の `meta_json.typo_fix` に記録。
- 今後の取込: `import_vimeo_transcripts.py` が同じ表で補正してから登録する。キーは補正前の本文から作るため、再実行しても二重登録しない。
- Macで後から行う作業（Supabase無料枠内、補正したチャンクだけ読む）:

```sh
# プレビュー（件数だけ表示）
~/selenium_env/venv/bin/python '215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/scripts/apply_transcript_corrections.py'
# 埋め込みの作り直しとRaimo側の入れ替え
~/selenium_env/venv/bin/python '215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/scripts/apply_transcript_corrections.py' --reembed --mirror-raimo --apply
```

戻す場合は `kc_typo_backup_20261026` の `content`・`search_text`・`content_hash` を `chunk_id` で書き戻す。

## 神大家0・2・3・4コースへの拡張（2026-10-27）

松野さん依頼「神大家0〜4の動画もできるだけ文字起こしして登録」。AI使用料がかからない順に2段で取る。

1. **Vimeo自動字幕（無料）**: `scripts/jarvis_westudy_course_vtt_batch.py`。レッスン一覧は Supabase `comments` の `lesson_desc` 行から作り、取込済み・基礎と重複するレッスンは飛ばす。ログインは1回で全レッスンを回る。出力は OneDrive `C1_cursor/1c_神・大家さん倶楽部_AI推進/講座_文字起こし/<コース>/jarvis/`、状態は `apps/jarvis-dashboard/data/course_transcripts/courseN_status.json`。
2. **字幕なし動画はローカルWhisper（無料・外部送信なし）**: `scripts/jarvis_westudy_whisper_fallback.py`。yt-dlp で音声だけ取り、Mac 上の mlx-whisper（large-v3-turbo）で起こす。初期プロンプトに補正表の正しい語を入れて固有名詞の誤変換を減らす。元MDは書き換えず `<元名>__whisper.md` と `courseN_whisper.json` を作る。Gemini 無料枠は会員限定動画を外部に送ることになり、学習利用の懸念もあるため使わない。
3. **登録**: どちらも既存の `import_vimeo_transcripts.py --manifest … --course … --input-dir … --graph-root … --apply --embed --mirror-raimo`（コマンドは 1 の実行後に表示）。差分だけ追加し、`config/kamiooya_transcript_corrections.tsv` の補正を適用してから登録する。Whisper 分は `meta_json.transcript_provider=local_whisper`。

```sh
# 前提（初回のみ）: ~/selenium_env/venv/bin/pip install yt-dlp mlx-whisper ／ brew install ffmpeg
~/selenium_env/venv/bin/python scripts/jarvis_westudy_course_vtt_batch.py            # 0,2,3,4 の字幕取得
~/selenium_env/venv/bin/python scripts/jarvis_westudy_whisper_fallback.py --manifest apps/jarvis-dashboard/data/course_transcripts/course2_status.json
```
