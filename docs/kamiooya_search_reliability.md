# Q&A search reliability and reference display

The auth gateway admits a persistent answer job and returns its identifier immediately. The existing approved membership, credential version and chat ownership checks apply to admission and every status read. Job tables/RPCs are service-only. A stable client request identifier and atomic admission serialize active jobs per user, so a lost response or repeated status request does not start another model call. A lost worker becomes an explicit timeout; it is not silently restarted with an uncertain generation outcome.

The processing budget is 300 seconds, with time reserved for persistence. Normal search uses the existing guarded Raimo route with a background deadline rather than the legacy one-minute HTTP relay. Semantic search executes the shared `semantic-search/handler.ts` implementation inside the background worker; it does not nest another synchronous Edge HTTP request. `EdgeRuntime.waitUntil` is still subject to the platform worker's lifetime/CPU/memory limits; validate actual deployment behavior rather than promising that every task has a fresh worker lifetime.

The browser polls through short authenticated requests, retains only the pending request/job identifiers and question in per-user session storage, and can resume delivery after reconnection or login. It stores no credentials there. Logout stops that browser's retrieval; subsequent retrieval requires a valid current approved session. An explicit retry following a terminal failure must not be confused with automatic deduplication of an in-flight request. When an upstream continues after a cancellation, inspect saved history before retrying.

## Reference identity and dates

Semantic context labels are generated before similarity/recency presentation sorting and returned on the corresponding source records. Reordering never renumbers them. The answer's source markers link to those exact records. Video references retain the title and each individual start time. Club videos prefer the canonical WeStudy member page because direct Vimeo pages can be unavailable despite a working embedded player. The UI explicitly asks the member to seek to the displayed time there; it does not claim automatic seeking on that external page. For sources without a member-page mapping, direct Vimeo timestamps use `#t=...s` while preserving unlisted URL parameters. Never substitute a newly invented date for a missing publication/post date.

The UI groups community and LINE references by calendar year, newest first. The current JST calendar year is subdivided by month. Missing dates can be hydrated by exact comment ID from the service-only reference metadata endpoint, independently of the large legacy comment download.

The inspected legacy semantic deployment saved its answer-context ID order in recent search events. The owner-scoped history endpoint can recover that order for an unambiguous query and assistant timestamp match. Missing or ambiguous history is not assigned a guessed number. Referenced video chunks can be recovered from their recorded keys. This recovery is limited to the inspected recent protocol window; it does not rewrite old answer text or perform additional model generation.

`scripts/jarvis_qa_reference_date_repair.py` defaults to a dry run against an audited Raimo export. It validates source dates, holds conflicting IDs, repairs only null Supabase dates and records a private audit. Existing non-null dates, original content and ingestion timestamps are never overwritten. Do not commit or sync private source exports/reports.

## Attachment initialization

Read-only session/index loading retries bounded transient network/5xx failures. Authentication/permission errors are not retried. Page offsets must advance and records are published to the UI only after a complete index; stale login generations cannot overwrite a newer user. A visible retry control replaces the previous one-shot error toast. Passwords are not kept for retry. The existing private Storage and per-request membership checks remain unchanged.

## Deployment order

1. Apply `20261106_reference_metadata.sql` and `20261106_answer_jobs.sql`; verify anonymous denial and service access.
2. Audit and conditionally apply the missing-date repair from a private canonical export. Record counts and source assumptions.
3. Bundle and deploy `raimo-auth` with external npm/HTTPS imports, then the shared semantic entry point. Preserve existing environment values and the previous code for rollback. No new key or paid service is required.
4. Publish the matched frontend HTML/JS and existing catalog prefix, setting the verified auth-gateway URL. Preserve the business source's existing reference-filter/navigation features. A frontend source change alone does not update the live Raimo app.
5. Validate real normal and semantic answers, exact source-label links, chronological groups, per-position video URLs, attachment index/open, anonymous denial and logout. Synthetic clocks are useful regression tests, not evidence of real multi-minute worker execution. Keep unresolved real-role and next daily-operation checks explicit.

Test entrypoints: Node tests under `apps/kamiooya-qa-web/tests`, Deno check for both Edge entry points, and the date-repair Python tests.

## Bounded and on-demand reference reads

The legacy Raimo comment response was about 70 MB on the wire and could exhaust the gateway's compute resources (HTTP 546). A server-proof-protected `POST /internal/read/comments-page` reads at most 500 rows by an ascending numeric primary-key cursor. The approved-member gateway validates the cursor, fixes the upstream route and hard page size, and projects display fields, omitting email/IP/user-agent and internal credentials. `scripts/jarvis_qa_comment_pages.py` prepares this one additive alias from the current private live definition, preserving all original routes and guards. Never commit its private input/output definitions.

The client publishes a complete, cursor-validated list only after successful paging. It loads comments/lesson descriptions and full video chunks on first opening their corresponding views, shares an in-flight read, caches for that login, and clears on logout. Q&A uses compact reference metadata and returned answer sources without downloading both full reference datasets at login.

## Year-only inference and cited-source priority

`20261106_reference_years.sql` leaves `posted_at` unchanged and records only `inferred_year` plus bound-comment evidence. A numeric missing-date comment is inferred only when the maximum known year below its ID equals the minimum known year above it. Use prefix window aggregates in opposite sort directions, bounded lock/statement timeouts and an atomic transaction. The audited 140 remaining source comments all satisfy these bounds for 2026; month/day remain unknown. Videos and lesson descriptions are never grouped by inferred dates.

Answer markers have a compact source index at the top in first-mention order, with dates for comments/LINE and title/position playback for videos. Detailed comment and LINE references remain newest first by calendar year/current-year month. Stable context labels do not change when their display order changes.

## Release verification checkpoint (2026-11-06)

PR #238. Missing exact dates repaired: 22,339; dated Supabase rows: 25,652. Year-only records: 140, actual timestamps still null. Service metadata succeeds, anonymous access denied. Two concurrent identical DB admissions create one job, without any model invocation. Real normal searches completed in 40.46 and 76.60 seconds; the latter survived a browser reload/re-login and delivered the same saved answer with no extra job. Community view displayed 25,522 source rows, and its authenticated original-image link opened a 2911×3024 private Storage object. Real semantic search also completed in 23.52 seconds. Do not treat synthetic 90/140/240-second tests as real multi-minute worker evidence.

The real semantic job completed in 23.52 seconds with one cited video position and 11 LINE sources, preserving the original context labels (including seminar12). Marker links are handled inside the reference container so nested scroll areas reliably reveal their target, without relying on host-browser fragment navigation. The 2026-11-06 daily community workflow 42153985436 succeeded and saved 112 new attachment records (3,528 existing skipped; 2,676 untrusted-source entries excluded).

The cited member video was checked on its canonical WeStudy page after authorized login: matching title and a working Play control were present. Its bare Vimeo page returned not found, so the UI now prioritizes the member page and displays the exact reference time without promising automatic seek. Apply the year-inference migration after the exact-date repair.

## Opt-in real-time normal-search check

The default test suite skips the deliberately slow integration test. Run it explicitly when auditing timeout behavior:

```sh
QA_WALLCLOCK_TEST=1 node --experimental-strip-types --test apps/kamiooya-qa-web/tests/qaAnswerWallClock.test.mjs
```

This takes about five minutes. It connects the unchanged production gateway and adapters to a real loopback HTTP server: one normal upstream waits 190 seconds; another never responds and must be cancelled by the real processing deadline (about 285 seconds, reserving the remainder of the 300-second budget for persistence). It drops an admission response and a status response, reauthenticates during processing, verifies a single upstream invocation/job, replays the completed/failed request, and checks cross-user and logged-out access. All identities and results are synthetic. No AI/provider calls, production records, credentials, or external network are used.

This is real wall-clock HTTP evidence for the production code, not a hosted Supabase worker test. Keep it separate from the real production normal-search measurement (76.60 seconds with reload/relogin) and the virtual-clock 90/140/240-second regression tests. The hosted worker and request limits still apply: [Supabase limits](https://supabase.com/docs/guides/functions/limits), [background tasks](https://supabase.com/docs/guides/functions/background-tasks). Do not expose a public delay/testing endpoint just to extend the timing measurement.

2026-11-06 opt-in run passed with real elapsed times: successful upstream 190.260s; stalled upstream stopped with `answer_timeout` at 285.361s. Each case had exactly one upstream call and one job despite lost admission/status responses and reauthentication. Short status requests remained responsive. Cross-owner requests were denied and logged-out retrieval returned 401. No AI calls or production writes were used. The live `raimo-auth` editor source was also compared privately with the released bundle and matched exactly (300s budget plus `EdgeRuntime.waitUntil`). This does not upgrade the existing hosted production evidence beyond the observed 76.60s normal generation.

## Quality-preserving efficiency (2026-11-06)

Search limits, source text, retrieval thresholds, model, and generation prompt are unchanged. Answers/search results and membership/permission decisions are not cached. Normal search's existing keyword/answer/source-selection calls are retained rather than deleting a source-verification step without equivalent-quality evidence.

Semantic query embeddings alone are shared inside a warm worker for an exact SHA-256 key of model/task/dimensions/query. The bounded cache holds at most 64 entries, expires completed entries after 180 seconds, validates vector dimensions/finite values, and returns copies. Raw query text is not a cache key or persisted record. Concurrent identical preprocessing shares one provider call. Cancellation is per consumer; another consumer can finish, and an unfinished provider request is cancelled when all consumers leave. Failed/invalid embeddings are not reused. This cache is worker-local, so it does not promise reuse across instances or after a cold start. Every request still retrieves current source rows and generates its own answer. Existing event `meta` records `embedding_cache_hit` and `embedding_ms` for measuring real reuse; no new database/schema/service/key is needed.

History source reads overlap independent event/source/job reads and use at most four 20-key chunk requests at a time. The same maximum 500 keys, page order, exact-ID source mapping, and DTO clipping remain. Completely labelled saved citation histories do not repeat their server recovery request; current dates/source metadata are still independently refreshed. Background admission authorization reads each live member/parent-session/chat-owner once in parallel, preserving every revocation/ownership check without an authorization cache.

Tests cover immutable identical vectors, expiry/model/task/query boundaries, invalid/failing vectors, shared-consumer cancellation, bounded active requests, exact 100-key ordered retrieval, current authorization checks, and zero redundant reads for fully labelled histories. Performance or billing percentages must not be claimed from these fixture tests; measure production cache-hit frequency separately.

Search-mode UI copy describes matching methods and variable response time rather than ranking speed. Observed normal (40/77s) and semantic (24s) requests were not a controlled same-question benchmark. The UI removes the old normal 10–30s versus semantic slower comparison, keeps normal as the default, and explains that either mode may take minutes depending on query, evidence volume and load.


## 2026-11-06 仕上げの待ち合わせ点検

意味検索のLINEキーワード検索を埋込生成と並行開始し、動画タイトル/URL取得を動画chunk取得の直後に開始する。独立したコミュニティ/LINE応答を待ってから動画情報を取得していた直列区間を除去。RPC回数・検索条件・選択根拠数・回答モデル/プロンプトは維持する。`handler.test.ts` は外部通信禁止で、依存関係のゲートを使って前倒し実行と根拠/番号の維持を検証する（fixtureのmsを本番高速化率とは扱わない）。

既存イベントmetaへ `embedding_provider_calls` と `retrieval_ms` を追加し、埋込の実呼出と検索待機を区別する。回答生成の `gemini_calls` と埋込を混同しない。キャッシュ共有者は埋込呼出0で、回答は毎回最新の検索結果から生成する。

追加候補は、実測後に判断する。回答の再利用にはデータ更新版・会員権限・検索条件を含む一致確認が必要で、鮮度を保証しない回答キャッシュは導入しない。根拠削減・安価モデルへの一律変更・自動的な意味検索ONは品質に影響し得るため実施しない。通常検索の複数LLM工程の削減は同一質問/同一データで回答と引用の比較評価を先に行う。

点検でLINE RPC失敗を空配列と扱い、根拠が欠けたまま生成し得る箇所も修正。コミュニティ/動画と同様、LINEのいずれかの検索が失敗したら明示的エラーとし、回答生成AIは呼ばない。自動の無制限リトライは追加せず、復旧後に利用者が再試行できる。Deno障害試験で両経路のエラーと生成0回を検証。


## 通常検索のAI工程整理（2026-11-06）

従来はキーワード抽出→回答生成→根拠ID抽出の3段階。サーバー専用 `/internal/normal-answer-v2` は同じキーワード抽出・検索条件/件数・モデル・回答指示を維持し、従来のMarkdown本文に根拠IDタグを添えて同時生成する（成功時2段階）。公開用パッチ生成器 `scripts/kamiooya_normal_pipeline_patch.py` は現在の非公開API定義を読み、既存全エンドポイントを保存したまま1経路だけ追加する。生成されたAPI定義には既存のサーバー秘密が含まれるため、Gitやクラウド同期に保存しない。

`decodeNormalAnswer` が本文内のコメント/動画chunk IDタグを読み、既知ID・根拠欠落を検査し、安定した出典番号へ変換する。DB内部idを使ったタグは、同じ提示行のcomment_idへ一意対応できる場合だけ正規化し、衝突/不明IDは従来経路へ戻す。非対応/不正なら履歴書込み前に従来経路へ戻す。タグ欠落・不正IDによるフォールバック時には追加AI処理が発生し得るので、全リクエストで必ず2回になるとは主張しない。履歴保存失敗時は再生成へ戻らず、重複履歴・二重AI呼出を防ぐ。回答キャッシュ/通常検索のデフォルト/認証/添付権限は変更しない。

Edgeは `RAIMO_NORMAL_PIPELINE_V2=0` で従来経路へ戻せる。フラグ未設定時はV2を使用する。API側の既存 `/messages` は変更しない。Nodeは実gateway/adaptersで成功/不正形式フォールバック/履歴障害を検証し、Pythonは元APIの不変・同一検索条件・2モデル段階・追加経路の履歴書込0を検証する。


ジョブ結果の `pipeline` は normal-v2 / normal-legacy / normal-legacy-fallback / fast-legacy を区別する。成功・フォールバックの割合を実測するためであり、料金やトークン数を推測で記録するものではない。最初のJSON一括出力案は文章量・網羅性の差が出たため不採用とし、通常Markdown+IDタグへ変更した。
