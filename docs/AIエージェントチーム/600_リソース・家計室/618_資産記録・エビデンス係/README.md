# 【設計中】618 資産記録・エビデンス係

数値の週次履歴を財務Supabaseに残し、必要時に最新の資産証拠画像を確認できるようにする。

- 起動: 数値は毎日09:10起動・週単位収集。画像は必要時依頼。取り直しは報告確認後に音声・チャットで依頼。
- 保存: 数値=既存DB履歴。画像=同じSupabaseの非公開Storageに最新1組（新設案）。社員フォルダに画像を置かない。
- 反映・確認: KURASHIFTの数値・基準日・未取得状況。最新証拠閲覧をKURASHIFTに追加案。JARVISは更新状況と閲覧先の補助入口。
- 報告の出口: Slack #report / #consult / #ops。Slackからの起動は行わない。
- 正本: [CLAUDE.md](./CLAUDE.md)、[flow.md](./flow.md)、[output_spec.md](./output_spec.md)。
- 月次の画像アーカイブは基本案から除外。本番実装・Storage新設は未実施。

- 判断ループ: 実行前に有効な採用基準をDBから取得 → 実行・結果確認 → 本人の判断と理由をDBへ追記 → 次回へ。共通owner_decisionsの618向け接続は未実装。詳細output_spec.md。

- FlowForge: https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_fQRxeChymx2NZAzi70ppxMtb
- 次の具体化: [エージェント指示_618具体化.md](./エージェント指示_618具体化.md)（Codex/ミスレモン/GenCode向け）。
