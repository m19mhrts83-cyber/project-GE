# Obsidian Sync で OneDrive のボルトを iPhone と連携する手順

OneDrive 上に置いた Obsidian のボルト（フォルダ）を起点に、Obsidian Sync を使って iPhone で閲覧・編集できるようにする手順です。

---

## 前提：OneDrive と Obsidian Sync の関係

- **Obsidian Sync** は、Obsidian 公式の有料同期サービスです。データは Obsidian のクラウドに暗号化されて保存され、iPhone はここ経由で同期します。
- **OneDrive** は「PC 上のボルトの置き場所」として使います。iPhone は **OneDrive アプリではなく、Obsidian アプリ + Obsidian Sync** で同じノートを開きます。

---

### 「どちらでつなぐか」の整理（PC と iPhone の役割）

**結論：PC も iPhone も、両方とも Obsidian Sync でつながります。**  
違いは「ボルトのファイルがどこに置いてあるか」だけです。

```
【PC】
  ボルトの実体 ＝ OneDrive フォルダ内
       ↓ このフォルダを Obsidian が開く
  Obsidian（PC） ←―― Obsidian Sync ――→ Obsidian のクラウド

【iPhone】
  ボルトの実体 ＝ iPhone 内（Obsidian が Sync で取得したコピー）
       ↓
  Obsidian（iPhone） ←―― Obsidian Sync ――→ 同じクラウド
```

- **PC**：OneDrive にあるフォルダをそのままボルトとして開き、**さらに** Obsidian Sync でクラウドと同期しています。つまり **OneDrive（保管場所）＋ Obsidian Sync（同期）の両方**を使っています。
- **iPhone**：OneDrive にはつながりません。**Obsidian Sync だけ**でクラウドから同じボルトをダウンロードし、iPhone 内にコピーを置いて編集します。編集は Sync でクラウドに送られ、PC にも反映されます。

「同時にいじらなければ大丈夫」というより、**「同じノートを、PC と iPhone のどちらで編集しても、Obsidian Sync が 1 本でやり取りするので大丈夫」**です。  
気をつけるのは、**同じボルトを「OneDrive の同期」で別の PC でも開いて編集する**こと。そうすると「OneDrive の同期」と「Obsidian Sync」の**二つの同期**が同じファイルを触ることになり、競合しやすくなります。  
→ **このボルトを OneDrive で開くのは今の PC 1 台だけにし、iPhone は Obsidian Sync だけで使う**、という形にすると安全です。

---

### 重要な注意（公式ヘルプより）

Obsidian の公式ヘルプでは、**ボルトが iCloud / OneDrive / Dropbox などの「同期フォルダ」内にある場合**は、Obsidian Sync を有効にする前に次を読むよう案内されています。

- [Can I use a third-party sync with Obsidian Sync?](https://help.obsidian.md/sync/faq#Can%20I%20use%20a%20third-party%20sync%20with%20Obsidian%20Sync?)
- [Switch to Obsidian Sync](https://help.obsidian.md/sync/switch)

理由は、**同じフォルダを「OneDrive の同期」と「Obsidian Sync」の両方で扱うと、競合や不整合が起きる可能性がある**ためです。

- **OneDrive を「保管場所」として使い続けたい場合**  
  → このまま OneDrive 上のボルトで Obsidian Sync を有効にすることは可能ですが、**その PC 以外では、同じボルトを OneDrive で開かず、iPhone などは Obsidian Sync のみで使う**ようにすると安全です。
- **公式の推奨に沿いたい場合**  
  → ボルトを OneDrive 外のフォルダに移し、同期は Obsidian Sync のみにし、バックアップ用に別途 OneDrive などにコピーする方法があります。

以下は、**今の OneDrive 上のボルトをそのまま使い、Obsidian Sync で iPhone と連携する**手順です。

---

## 準備するもの

- Obsidian アカウント（未作成の場合は [obsidian.md](https://obsidian.md) でサインアップ）
- **Obsidian Sync の契約**（[アカウントダッシュボード](https://obsidian.md/account/sync) から月額または年額で申し込み）
- PC：OneDrive 内のボルトを開いている環境
- iPhone：Obsidian アプリをインストール済み

---

## ステップ 1：PC（OneDrive のボルト）で Obsidian にログインする

1. PC で Obsidian を開き、**OneDrive 内のボルト**を開く。
2. 左下の **歯車アイコン（設定）** をクリック。
3. 左サイドバーで **「General」** を選択。
4. **「Account」** の **「Log in」** をクリック。
5. メールアドレスとパスワードを入力して **「Login」**。

---

## ステップ 2：コアプラグイン「Sync」を有効にする

1. 設定画面の左サイドバーで **「Core plugins」** を開く。
2. **「Sync」** のトグルを **オン** にする。
3. 左サイドバーに **「Sync」** が増えるので、それをクリック。

---

## ステップ 3：リモート保管庫（リモートボルト）を作成する

1. Sync の設定画面で **「Sign in」** をクリック（まだの場合）。ログイン済みなら次の項目へ。
2. **「Set up Sync」** または **「リモート保管庫の選択」** のあたりで、
   - **「Create new remote vault」**（新しいリモート保管庫を作成）を選択。
3. リモート保管庫の**名前**を入力（例：`My Vault` や現在のボルト名）。
4. **「Create」** をクリック。
5. 続いて、この **OneDrive のボルト** と、今作ったリモート保管庫を **接続** するため、**「Connect」**（接続）をクリック。

これで、**OneDrive 上のボルトの内容が Obsidian のクラウドにアップロードされ、同期が始まります**。初回はノート数によって時間がかかることがあります。

---

## ステップ 4：iPhone で Obsidian を開き、同じアカウントでログインする

1. iPhone で **Obsidian** アプリを起動。
2. 左下の **歯車アイコン** から **設定** を開く。
3. **「General」** → **「Account」** の **「Log in」** で、PC と同じ Obsidian アカウントでログイン。

---

## ステップ 5：iPhone で「Sync」を有効にする

1. 設定の **「Core plugins」** を開く。
2. **「Sync」** を **オン** にする。
3. 左サイドバーの **「Sync」** を開く。

---

## ステップ 6：iPhone で「既存のリモート保管庫」に接続する

1. Sync の設定で **「Choose existing vault」**（既存の保管庫を選択）を選ぶ。
2. ステップ 3 で作成した **リモート保管庫の名前** を選択。
3. **「Connect」** をタップ。
4. 初回は、クラウドの内容が iPhone にダウンロードされます。ノート数が多いと時間がかかることがあります。

これで、**OneDrive のボルト（PC）と iPhone が、Obsidian Sync 経由で同じノートを共有**できます。PC で編集すれば iPhone に反映され、iPhone で編集すれば PC（OneDrive のボルト）に反映されます。

---

## ステップ 7：日常の使い方

- **PC**：これまで通り、OneDrive フォルダ内のボルトを Obsidian で開いて編集。保存すると Obsidian Sync が自動でクラウドに反映します（設定で自動同期がオンなら）。
- **iPhone**：Obsidian を開き、接続したリモート保管庫のボルトを開いて閲覧・編集。同様に Sync が自動で同期します。
- 同期の状態は、設定の **「Sync」** 画面で確認できます。手動で同期したい場合は、Sync 設定内の **「Sync now」** を使います。

---

## うまくいかないときの確認ポイント

1. **PC と iPhone で同じ Obsidian アカウントでログインしているか**
2. **両方で「Sync」がオンか**
3. **iPhone で「既存のリモート保管庫」を選び、「Connect」まで完了しているか**
4. **通信環境**：初回同期は Wi‑Fi 推奨。クラウド側の混雑で遅くなることもあります。
5. **OneDrive の同期**：同じボルトを、別の PC で OneDrive 経由で開きながら編集すると、Obsidian Sync と OneDrive の二重同期になり競合しやすいです。**iPhone と連携する PC は OneDrive 上のそのボルトを開く 1 台にしておく**と安全です。

---

## まとめ

| 順番 | 作業内容 |
|------|----------|
| 1 | Obsidian アカウント作成・Obsidian Sync 契約 |
| 2 | PC：OneDrive のボルトを開き、設定でログイン |
| 3 | PC：Core plugins で「Sync」をオン → リモート保管庫を「作成」→ 現在のボルトを「接続」 |
| 4 | iPhone：Obsidian で同じアカウントにログイン |
| 5 | iPhone：Sync をオン → 「既存の保管庫を選択」→ 同じリモート保管庫に「Connect」 |

この流れで、**OneDrive のフォルダを起点にしたまま、iPhone でも Obsidian Sync で閲覧・編集**できるようになります。
