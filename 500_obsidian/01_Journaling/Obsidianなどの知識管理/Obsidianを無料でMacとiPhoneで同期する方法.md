# Obsidian を無料で Mac と iPhone で同期する方法

Obsidian Sync は月額約5ドルのサブスクで買い切りではありません。ここでは**無料**で Mac と iPhone を同期できる主な方法をまとめます。

---

## 方法の比較（結論）

| 方法 | 費用 | 手軽さ | おすすめ度 |
|------|------|--------|------------|
| **A. Remotely Save + OneDrive** | 無料 | プラグイン設定のみ | ★★★ 今の OneDrive 環境を活かせる |
| **B. iCloud Drive** | 無料（iCloud 容量次第） | ボルトの場所を変えるだけ | ★★★ Mac + iPhone だけならいちばん簡単 |
| **C. Syncthing + Mobius Sync** | 無料 | やや手間 | ★★ 自分で管理したい人向け |

---

## A. Remotely Save + OneDrive（おすすめ）— 詳細手順

**今使っている OneDrive のまま**、プラグイン「Remotely Save」で Mac と iPhone を同期する方法です。追加費用はかかりません。

### 仕組み（イメージ）

- **Mac**：OneDrive フォルダ内のボルトを開く → Remotely Save がその内容を OneDrive 上の専用フォルダ（`/Apps/remotely-save/ボルト名`）と同期する。
- **iPhone**：空のボルトを作り、同じ設定で「リモートから取得」すると、同じ OneDrive の内容が落ちてくる。編集後は「同期」で OneDrive に戻す。

**注意**：Remotely Save が対応しているのは **「OneDrive for personal」（個人用）」** のみです。OneDrive for Business（仕事用・学校用）は現状未対応です。

---

### 準備：確認しておくこと

- **OneDrive の個人用アカウント**（Microsoft アカウント）でログインできること。
- **Mac で開いているボルトの名前**（フォルダ名）。iPhone で作るボルトは**同じ名前**にすると、同じリモートフォルダを参照できます。

---

### ステップ 1：Mac で Remotely Save をインストールする

1. Mac で Obsidian を開き、**OneDrive 内のボルト**（例：`500_Obsidian`）を開く。
2. 左下の **歯車アイコン（設定）** をクリック。
3. 左サイドバーで **「コミュニティプラグイン」** をクリック。
4. まだオフなら **「制限モードをオフにする」** をオンにする。
5. **「閲覧」** をクリックし、検索欄に **「Remotely Save」** と入力。
6. **「Remotely Save」** の **「インストール」** をクリック。
7. インストール後、**「有効にする」** をクリック。

---

### ステップ 2：Mac で OneDrive に接続する（認証）

1. 設定の左サイドバーで **「Remotely Save」** をクリック（プラグイン名が表示される）。
2. **「Choose service」**（サービスを選択）のドロップダウンで **「OneDrive for personal」** を選ぶ。
   - 英語の場合は "OneDrive for personal (alpha)" などと表示されていることがあります。
3. **「Auth」**（認証）ボタンをクリックする。
4. 画面に **青いリンク（URL）** が表示されるので、それを **クリック** する。
   - ブラウザ（Safari など）が開きます。
5. ブラウザで **Microsoft アカウント** でログインする（まだログインしていない場合）。
6. 「このアプリにアクセスを許可しますか」のような画面になったら **「承諾」や「Continue」** をクリック。
7. 「Obsidian で開く」のようなポップアップが出たら **「開く」** を選ぶ。
8. Obsidian に戻ると、Remotely Save が OneDrive に接続するための小窓が表示されます。**そのまま待つ**と、接続が完了すると自動で閉じます。
9. 設定画面に戻り、接続情報（リモートのパスなど）が表示されていれば **設定完了** です。
   - オプションで **「Check」** ボタンを押して接続テストができます（「接続できない」と出ても、実際の同期ができれば問題ない場合があります）。

この時点で、OneDrive 上に **`/Apps/remotely-save/（あなたのボルト名）`** というフォルダが作成されます。

---

### ステップ 3：Mac で初回同期を実行する

1. 設定を閉じ、Obsidian のメイン画面に戻る。
2. **Cmd + P** でコマンドパレットを開く。
3. **「Remotely Save: Start sync」** と入力して、表示されたコマンドを実行する。
4. 右上などに同期の進捗が表示され、**「x/x Remotely Save finish」** のように表示されたら **初回アップロード完了** です。

**別のやり方**：左端のリボン（アイコン列）に Remotely Save のアイコンが追加されていることがあります。それをクリックしても同期できます。

---

### ステップ 4：Mac で自動同期を設定する（任意）

1. **設定 → Remotely Save** を開く。
2. **「Scheduled auto sync」**（スケジュール自動同期）や **「Sync on load」**（起動時に同期）などのオプションがあるので、必要に応じてオンにする。
   - 例：「何分ごとに自動同期する」を有効にする、など。
3. **設定フォルダ（.obsidian）も同期したい場合**は、**「Sync config dir」** や **「Vault configuration sync」** のような項目をオンにすると、テーマやプラグイン設定も OneDrive に同期されます（iPhone 側でも同じ見た目にしやすいです）。

---

### ステップ 5：iPhone で新しいボルトを作る

1. iPhone で **Obsidian** アプリを起動する。
2. **「新規作成」** または **「Create new vault」** をタップする。
3. **ボルト名** を入力する。**Mac のボルト名とまったく同じ名前にする**（例：`500_Obsidian`）。
   - 同じ名前にすることで、OneDrive 上の同じフォルダ（`/Apps/remotely-save/500_Obsidian`）を参照します。
4. 保存場所は **「On my iPhone」**（iPhone 上）でよいです。**「作成」** をタップする。

---

### ステップ 6：iPhone で Remotely Save をインストール・設定する

1. iPhone の Obsidian で、今作ったボルトを開いた状態で、左下の **歯車アイコン** から **設定** を開く。
2. **「コミュニティプラグイン」** → **「閲覧」** で **「Remotely Save」** を検索し、**インストール** → **有効にする**。
3. 設定の左サイドバーで **「Remotely Save」** を開く。
4. **「Choose service」** で **「OneDrive for personal」** を選択。
5. **「Auth」** をタップし、表示された **リンクをタップ** してブラウザを開く。
6. **Microsoft アカウント** でログインし、**許可** する。
7. 「Obsidian で開く」と出たら **「開く」** をタップし、Obsidian に戻って接続完了を待つ。

---

### ステップ 7：iPhone で OneDrive から内容を取得する（初回）

1. Remotely Save の設定画面で、**「Download」** や **「Download and apply」** のようなボタンがあればタップする。
   - または、コマンドパレット（画面を下に引っ張るか、メニューから開く）で **「Remotely Save: Start sync」** を実行する。初回はリモートからダウンロードされます。
2. 同期が終わるまで待つ（ノート数が多いと時間がかかることがあります）。
3. 完了すると、Mac で入れたノートが iPhone のボルトに表示されます。

---

### ステップ 8：日常の使い方（同期のタイミング）

- **Mac で編集したあと**：**Cmd + P** → **「Remotely Save: Start sync」** でアップロード。自動同期をオンにしていれば、一定時間ごとや起動時に同期されます。
- **iPhone で編集する前**：念のため **「Remotely Save: Start sync」** を実行して、最新を取得してから編集すると安全です。
- **iPhone で編集したあと**：**「Remotely Save: Start sync」** を実行して、変更を OneDrive にアップロードする。

iPhone では、コマンドパレット（画面を下にスワイプするか、メニューから「コマンドパレット」を開く）で **「Remotely Save: Start sync」** と入力して実行できます。リボンに Remotely Save のアイコンがあれば、それをタップしても同期できます。

---

### 補足・注意点

- **企業用 OneDrive（OneDrive for Business）** は Remotely Save では使えません。個人用アカウントで設定してください。
- **ボルト名** は Mac と iPhone で必ず同じにしてください。違うと別のリモートフォルダになり、内容が一致しません。
- デフォルトでは **「.」や「_」で始まるファイル・フォルダ**（一部の設定ファイルなど）は同期されません。**「Sync config dir」** をオンにすると `.obsidian` が同期され、プラグインやテーマの設定を共有できます。
- Check ボタンで「接続できない」と出ても、実際に Start sync が成功していれば問題ないことがあります。まずは同期を試してみてください。

---

### 2つ目のボルト（例：215_神・大家さん倶楽部）を同期する

すでに 1 つ目のボルト（例：500_Obsidian）で Remotely Save を設定済みなら、**2つ目以降のボルトも同じ手順**で追加できます。OneDrive の認証はボルトごとに行いますが、同じ Microsoft アカウントでよいです。

**Mac でやること**

1. Obsidian で **2つ目のボルト**（例：`215_神・大家さん倶楽部`）を開く。
2. **コミュニティプラグイン** から **Remotely Save** をインストールして有効化（このボルトにはまだ入っていないため）。
3. **設定 → Remotely Save** で **OneDrive for personal** を選択し、**Auth** で同じ Microsoft アカウントで認証。
4. **Cmd + P** → **「Remotely Save: Start sync」** で初回アップロード。

**iPhone でやること**

5. Obsidian で **「新規作成」** から新しいボルトを作る。**名前は Mac のボルト名と完全に同じ**にする（例：`215_神・大家さん倶楽部`）。
6. そのボルトで **Remotely Save** をインストール・有効化し、**OneDrive for personal** で **Auth**（同じ Microsoft アカウント）。
7. **「Remotely Save: Start sync」** を実行して、OneDrive から内容を取得。

これで、Mac と iPhone の両方で「215_神・大家さん倶楽部」も開けるようになります。ボルトの切り替えは、Obsidian のホーム画面やボルト一覧から行えます。

---

## B. iCloud Drive（Mac + iPhone だけならいちばん簡単）

**Apple 製品だけ**で使うなら、ボルトを **iCloud Drive** に置くだけで、Mac と iPhone の両方で同じフォルダを開けます。プラグイン不要です。

### 手順の流れ

1. **Mac**：Obsidian で **「Create new vault」** → 保存場所に **iCloud Drive** を選ぶ（例：iCloud Drive → Obsidian → フォルダ名）。既存のボルトを iCloud に移す場合は、フォルダごと iCloud Drive にコピーし、Obsidian でそのフォルダを開く。
2. **iPhone**：Obsidian を開く → **「Open folder as vault」** などで **iCloud Drive → Obsidian → 同じフォルダ** を選ぶ。

これで、iCloud が自動で同期するため、Mac で編集すれば iPhone に、iPhone で編集すれば Mac に反映されます。

### 注意点

- **Mac と iPhone だけ**のときに向いている。Windows や Android は iCloud を扱いにくい。
- iCloud の容量（5GB 無料など）に注意。ノートが増えたら容量プランが必要になることがある。
- 今のボルトが OneDrive にある場合は、「iCloud に移す」か「OneDrive はバックアップ用にして、メインを iCloud にする」などの判断が必要。

---

## C. Syncthing + Mobius Sync（上級者向け）

- **Syncthing** で Mac のフォルダとクラウド／別デバイスを P2P 同期する。
- iPhone には Syncthing 公式アプリがないため、**Mobius Sync** や **SyncTrain** などのサードパーティアプリで Syncthing と連携する必要がある。
- 無料で自分で管理できるが、設定と運用の手間はほかの方法より多め。

---

## まとめ

- **今の OneDrive を続けたい** → **Remotely Save + OneDrive** が無料でそのまま使える。
- **Mac と iPhone だけで、とにかく簡単にしたい** → ボルトを **iCloud Drive** に置くだけの方法が一番シンプル。
- Obsidian Sync の「買い切り5ドル」は存在せず、月額課金のみです。上記のどれかで無料運用できます。
