# フロー確認→実装指示：Claude共通手順

2026-11-15。本人依頼でClaude Codeにもルール化。618以外にも使う手順。

## 根拠と確認範囲

618で対話しながら合意したフローをFlowForgeへ登録し、出力された実装用プロンプトと対応づけた2026-11-14の成果を再利用する。
観測した変換は「業務の入力→番号付きノード/接続/主体/説明→人の確認→同じフローを文章の実装指示へ展開」。
逆解析したのは利用者に見えるフローと出力の対応。FlowForgeの非公開プロンプト、モデル、内部コード、API契約全体を解明したとは主張しない。
2026-11-15、接続済みFlowForge読取MCPはshare_not_found_for_flowを返した。最新のFlowForge内容を読めたとはせず、11/14の保存済みフロー・生成原文・合意済み実装指示を使用。FlowForgeのMCP接続不調は、既に合意済みの手順の再利用を止める理由にしない。
生成原文にはNode CLI/Supabase MCPなどUIカテゴリ由来の文言もあったが、実装は既存PythonとSupabase SDK/APIを再利用した。UIの分類名から実在未確認の接続や新ランタイムを指示しない。

## 手順

1. 資産棚卸し：既存の文書・コード・ジョブ・ログ・画面・対象一覧を必要範囲で確認。確定/提案/未確認と参照日を明記。
2. フロー設計：各工程に安定ID、番号、主体、実行者/道具、入力、処理、保存、画面、報告、成功条件、失敗時処理を置く。
3. 判断とループ：判断する対象・おすすめ・理由・保留条件を示す。今回の取り直しと次回の改善を別の戻り矢印で描く。判断の保存だけでなく次回の取得と適用ID追跡まで入れる。
4. 人と確認：図を表示し、修正した箇所と影響する接続・工程だけを照合。曖昧な権限や接続を確定扱いにしない。図の確認は後追いでもよい（2026-11-15 松野さん）。判断事項の了承があれば実装へ進み、図のリンクと「確認は後追い」を報告し、直しが出たら同じ工程IDで戻す。
5. 指示生成：`prompt-template.md`へ確定フローを展開。同じ工程IDと接続一覧を残す。生成と実装の開始を混同しない。
6. 段階実装：取得/表示確認→最小実装→部分失敗/権限等の検証→了承範囲の本番反映。既存スクリプトと定額枠優先。
7. 実行確認：現在工程ID、実行者、run/根拠、成功/部分成功/失敗/保留/未検証、次のノードを短く更新する。フロー図を維持し、文章だけで別のフローにしない。

## Claudeでフローを見ながら進める

Claudeチャット：添付のフローHTMLをArtifactとして表示（必要機能が利用可能な場合）。HTMLはノード選択/状態メモ/JSON出力だけで、金融サイト・DB・Slackへ接続しない。図を更新しただけで実処理が終わったとは報告しない。
図が表示できない場合は同梱のMermaidを含むMDまたは工程一覧をチャットに表示して続行する。図を出せるかだけを理由に作業を止めない。
Claude Code：同じフローJSON/MDを読み、番号を宣言して実行・検証。ローカルHTMLをブラウザで開いて参照できる。実行状態はTASK.md/実run記録が正本、Artifactの手動状態は補助。
Claudeの文脈だけでDB保存/対外送信が可能とは限らない。利用可能ツールと権限を確認し、接続がなければ実装TASKへ渡す。

## ノードと状態の契約

`flow.json`のnodes/edgesを図とプロンプトの共通入力にする。nodesにはid、source_id、number、title、actor、executor、input/output、success/failure、implementation。edgesにはfrom/to、condition、kind（normal/branch/retry/next_run）。
確認した状態は、フローの実装状態（既存/実装済/手動/未接続）と今回の実行状態（未実行/処理中/確認済/一部/保留/未検証）を別に持つ。証拠なしに確認済へしない。
外部の実行結果を自動受信する配線は今回追加していない。Claudeが実際のツール結果を見てArtifactと作業記録を更新するか、JSONの作業メモを手動で引き継ぐ。

## ルールの配置

Git正本 `.claude/rules/matsuno-workflow-review.md`。本人Macにも同内容の実ファイルを `~/.claude/rules/matsuno-workflow-review.md` へ配置。本文の適用条件で業務フロー依頼に限定する。ホームの既存CLAUDE.mdは上書きしない。
Claudeチャット用は出力パッケージの01_Claudeプロジェクト指示.mdをProject指示へ貼り付ける。チャット側の保存/Artifact描画は本人のClaude内での最初の操作が必要で、Codexから設定済みとはしない。
新しいClaude Codeセッションでルールの読込を確認。既に開いているClaudeの会話の再読込・実行は未確認。

## 参考（公式）

- https://code.claude.com/docs/en/memory （.claude/rules とユーザーの ~/.claude/rules）
- https://support.claude.com/en/articles/9519177-how-can-i-create-and-manage-projects （Project指示/知識）
- https://support.claude.com/en/articles/17153992-what-are-artifacts-and-how-do-i-use-them （Artifact）

Codexの既存skill `workflow-to-agent-prompt`と内容を照合。案件固有の618・29対象・財務DB・18工程は共通ルールへ固定しない。
