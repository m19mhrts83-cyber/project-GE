# Gmail APIとCursor拡張機能：初回の補足

> 2026/11/04改訂：このファイルは初回をメール実習とした時点の資料です。最新の初回は08・09（全体像→インプット）。本資料は後続回の教材・履歴として残します。

確認日：2026年11月3日／講師用の根拠・操作手順／公開してよい範囲で独自に整理

## 初回に伝える範囲

Gmail APIは4分で仕組みを説明。OAuthの登録作業を初回に完了することは目標にしない。Cursorは10分で拡張機能を探す→発行元を確認→導入→Markdown・Excelの見本を開く、を体験する。

## Gmail API

### 伝える流れ

本人がGoogleの画面で許可する→Gmail API経由で対象メールを取得する→AIが要点・未確認事項・返信案を整理する→人が確認する。

APIキーだけで個人の受信箱を読めると説明しない。Googleの公式クイックスタートにはGoogle Cloudプロジェクト、Gmail APIの有効化、OAuthの同意・認証情報、ライブラリ、実行の準備がある。試験用の手順を、そのまま複数のメンバー向け本番サービスの完成形とみなさない。

### 許可と対象を区別する

- 初学者の連携案は `gmail.readonly` で閲覧から始める。Googleの定義ではメールと設定の閲覧に使う。
- 検索・ラベルで取得するメールを絞っても、許可の範囲そのものがそのメール1通だけになるわけではない。
- 返信案をチャットやローカルMDに表示することと、Gmailへ下書きを保存することは別。
- `gmail.compose` は下書き管理と送信を含む。下書き専用の権限と説明しない。
- 実メール本文をAIへ渡す前に、どのサービスへどの内容を渡すかを本人と確認する。授業の投影では練習アカウントや架空メールを使う。

### 第3回前の講師準備

1. 個人GmailかGoogle Workspaceかを確認し、その組織の管理者設定や利用条件に合う方法を選ぶ。
2. Google Cloud、API有効化、OAuth同意画面・クライアントを準備する。個人GmailにWorkspace専用のInternal設定を一律に案内しない。
3. テスト利用者・公開状態・必要な審査の条件を公式資料で確認する。警告画面を一律に無視する手順にはしない。
4. 本人が許可範囲を確認できるようにする。アクセストークンやクライアント秘密情報はMarkdown・Git・公開資料・クラウド同期に載せない。
5. 取得対象・利用するAIへの受け渡し・停止と許可解除の手順を確認する。
6. 未準備の方は実演と計画に切り替え、当日の接続成功を保証しない。

### 根拠

- [Google Gmail API：Python quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python)
- [Google Gmail API：Choose scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)

## Cursorの導入例

初回の導入例は **Office Viewer／発行元cweijan／ID cweijan.vscode-office**。作者の説明ではExcelとMarkdownを扱う。松野さんのローカル拡張機能フォルダで4.2.3の存在を確認した。これは参加者PCの動作確認とは区別する。

### 初回の手順

1. Cursor本体は事前に導入・起動確認を済ませる。
2. エディター画面の拡張機能パネルを開く。チャットだけの画面で見つからなければ、講師とエディター表示を確認する。
3. `cweijan.vscode-office` を検索する。名前だけでなく発行元と説明元を確認する。
4. インストールし、必要な再読み込みなどが表示されたらその場の画面で確認する。
5. `受信確認メモ.md` を開く。Office ViewerはMarkdownの表示・編集方法も変えるので、標準のテキスト編集へ戻したい場合は『Reopen Editor With』等で選び直す。
6. `受信メール一覧_練習.xlsx` を開き、件名・依頼・確認事項を表で見る。
7. うまく開かない場合は開くエディターを選び直す。合わない拡張機能はパネルから無効化できる。

最初は見本の閲覧まで。Excelの再計算・マクロ・重要な原本の編集は別の回の検討事項とし、Office ViewerをExcel本体と同じ機能だと説明しない。

Markdownは標準のプレビューも使える。追加の表示機能を試す場合は **Markdown Preview Enhanced／shd101wyy.markdown-preview-enhanced** を候補にし、初回の必須導入にはしない。

Cursor公式は第三者拡張機能にOpen VSXを使用すると説明しており、VS Code Marketplace上の全拡張が同じように利用できるわけではない。検索で見つからない場合、別の似た拡張を無条件で入れず、講師の確認か標準プレビューへ切り替える。

GrapeCityの旧Spreadsheet Viewerは公開ページに『積極的な保守は終了』とあるため、新規導入の中心にはしない。既存の拡張機能を今回削除・変更していない。

### 根拠

- [Cursor：Extensions](https://cursor.com/help/customization/extensions)
- [Office Viewer：作者README](https://github.com/cweijan/vscode-office)
- [Office Viewer：Open VSX](https://open-vsx.org/extension/cweijan/vscode-office)
- [VS Code：Markdown](https://code.visualstudio.com/docs/languages/markdown)
- [Markdown Preview Enhanced：作者](https://github.com/shd101wyy/vscode-markdown-preview-enhanced)
- [旧Spreadsheet Viewerの保守状況](https://marketplace.visualstudio.com/items?itemName=GrapeCity.gc-excelviewer)

## 実施状態

今回作成したのは教育プラン・原稿・架空の見本。実メールの取得、OAuth登録、参加者PCへのインストール、送信は実施していない。Office Viewerそのものの実機操作も今回の検証対象ではない。公開用ページと配布ファイルの参照先を確認する。
