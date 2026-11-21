# 315-A 確定工程との実装照合（2026-11-22）

## 根拠と実装計画

本番read proxy `resolve?agentId=315&view=full` を読み、flow `flow_S5g_i7CCiE0P6RKIp2_MkMTA`、9ノード・6接続、更新日2026-11-21を確認した。編集URLは開いていない。元の専用worktreeはclean、origin/mainと一致。抽出プロンプトの共通テンプレートより今回依頼を優先する。

- start（一致）: 日曜21:00 JST GHA、手動dispatch、WeStudy Fail通知を受けて手動または次回定時。別経路のMac日曜21:45補完を維持する。起動条件は変更しない。
- sub_collect／node_fetch_gha（ずれ→修正）: 従来はWeStudyのみ。315自身のmainブランチの直近完了履歴を追加し、実行中の自分を成功履歴として扱わない。
- node_fetch_westudy（Square probe、未実装→修正）: 従来のwatch点検では取得していなかった保存済みSquare stateを参照。live probeは呼ばない。
- node_fetch_line（CHRLINE health、未実装→修正）: 既存health APIをbaseline保存なしで呼ぶ。資料未マウント・直近decode標本なし・例外は確認不能。個別フォルダ名・本文は追加レポートへ載せない。
- sub_diagnose／node_ai_analyze（ずれ→修正）: GHA→Square→CHRLINEの収集順を守り、既存WeStudy／watch／Gmail点検と合わせてプログラムで突合。新たなAI呼出・自動復旧・Backlog起票なし。
- node_ai_summarize（ずれ→修正）: 健全性と「点検実行: 成功／部分成功／失敗」を分離する。異常が取得できた場合は収集成功でも健全性は要フォロー。未取得を含めば部分成功、全対象が確認不能なら失敗。cloudのMac委譲は部分成功として明示。
- end（ずれ→修正）: 確定説明「通常・異常ともSlack #ops」に合わせ、315-Aからquiet-green抑止指定を外す。専用Webhookが無ければエラーとし、共有投稿ツールの#report fallbackを使わない。

## #consult と安全境界

人の確認／#consult通知の独立ノードはないが、start説明に「Mac補完は…未解決事項を#consultへ通知」、ドラフト説明にも「要判断事項はSlack #consultへの通知対象」と残っており、維持指示との食い違いはない。途中承認を追加せず、未解決／確認不能を#consultへ渡す。GHAにもconsult専用Secretを渡し、欠落時に別チャンネルへ出さない。

Macの既存health push→recover_worker／必要時watch resumeの1回だけを維持。Square/CHRLINE異常だけでは新しい復旧を起動しない。Gmail再同意・QR・WeStudy再実行は人判断。dry-runではSlack・既存復旧・mark-checked・mark-promptedを行わない（検証ログ作成は行う）。

Squareライブ点検は既存のログイン内部で失効tokenの削除・更新を伴うため不使用。保存済みstate参照は調整担当へ確認して了承済みで、参照専用の設計どおりの実装。鮮度の既存専用値はなかったため174時間（週次168時間＋スケジュール／収集遅延余裕6時間）を採用。GHA前回完了履歴にも同じ上限を使う。将来日時・不正日時・上限超過は確認不能。315-Bの鮮度設定とは独立した315-A収集時の検証である。

## 検証

- `python3 -m unittest discover -s scripts/tests -p 'test_ops_health_315.py' -v`: 12件成功。
- `python3 -m unittest discover -s scripts/tests -p 'test_openchat_health_recovery.py' -v`: 既存4件成功。
- 収集順、cloudのローカル点検スキップ、Square欠落／古さ／不正／異常／正常、CHRLINE既存APIへのbaseline保存禁止、GHA完了main履歴、正常報告、未解決consult、専用Webhook欠落時の転送禁止、dry-run mark／投稿／復旧なしをモックと一時ファイルで確認。
- セルフレビューでGmail不正JSONが正常扱いされる既存経路と、専用Webhook欠落時の#report転送を発見し修正。GmailネストJSON・不正JSONのテストを追加。
- `python3 scripts/public_repo_guard.py --staged`: 9ファイル成功。`git diff --check`・Python構文チェック成功。
- Slack実送信、live probe、GHA手動実行、launchd再起動、デプロイ、マージは行わない。

## 残存リスクと承認事項

- 保存済みSquare stateの更新が途絶えると確認不能が続く。安全なlive点検の設計は別途判断が必要。
- CHRLINEはローカル依存・資料・decodeログが必要。本番ファイルでの実行とSlack到達は未検証。
- GHAのCONSULT Secret未設定時は通知エラーが返る。値の有無は本番運用担当が確認する。
- マージは本人承認後。Macはマージ後のmain追従で既存runnerが新コードを読むため、plist変更・再登録は不要。GHAも既存定時を待つ。
- 315-B、registry、運用status、FlowForge内容は変更していない。
