# Slack返信 → Todoist起票をクラウドで繋ぐ（推奨案）

## 現在地（2026-10-21 夜）

- Slackアプリに `channels:history` 追加・再インストール **済**（`conversations.history` 実測OK、トークン値は不変）
- GAS プロジェクト作成 **済**（無題のプロジェクト: `1TullLjEJ6p3SfsGGWM1OpZ2g4Lp6AiEp_PGaigrorsoq5XD0a9gPl6bE`）
- コード正本: `scripts/gas_todoist_312_slack_ingest.gs`（このGASに貼る）
- 未完: 貼り付け／スクリプト プロパティ4つ／`poll` 承認／5分トリガー／313ハンドラ
- GitHub Actions は新規ワークフローが登録されず（24件のまま）断念

## 結論

**Google Apps Script（GAS）で #consult を5分おきに読み、番号返信を Todoist に起票**する。
PCを起動していなくても動く・無料・既存の「2」「起票して 1,3」UXをそのまま使える。

```
人: #consult に「2」と返信
   ↓（GAS が最大5分で検知）
GAS: 直近ダイジェストの 2番 を取り出す
   ↓（Todoist API）
Todoist: [312][ai_raimo] 集まりを録画する を作成（コメント付き）
   ↓
GAS: #consult に「✅ 2 を起票しました（id）」と返信
```

## なぜ Zapier / Make ではなく GAS か

| 方式 | 番号返信 | 費用 | PC不要 | 設定の重さ |
|---|---|---|---|---|
| **GAS ポーリング（推奨）** | ○（既存UX） | 無料 | ○ | 中（貼り付け1回） |
| Zapier 無料 | ×（件名をそのまま返信） | 100タスク/月・2ステップ | ○ | 軽い |
| Make 無料 | △（要 Data store） | 1,000 ops/月 | ○ | 中 |
| Slack Events + Cloud Run | ○ | 従量（ほぼ無料） | ○ | 重い（公開URL・署名検証） |

Zapier 無料は「トリガー＋アクション」の2ステップ制限があり、フィルタや番号照合を挟めない。
番号UXを残すなら GAS が最短。

## 前提（これが無いと動かない）

Bot トークンに `channels:history` が無い（実測 `missing_scope`）。
→ 先に [`setup-slack-scope.md`](./setup-slack-scope.md) を実施。

## 設置手順（15分）

1. https://script.google.com → **新しいプロジェクト**
2. 下のコードを `Code.gs` に貼り付け（既存の内容は消してよい）
3. 左の **プロジェクトの設定** → **スクリプト プロパティ** に4つ登録
   - `SLACK_TOKEN` = `xoxb-…`（Bot トークン）
   - `TODOIST_TOKEN` = Todoist API トークン
   - `CHANNEL_ID` = `C0C7R0UF3MM`（#consult）
   - `STATE` = `{}`（空のJSON。自動で更新される）
4. 関数 `poll` を選んで **実行** → 初回は権限の承認（自分のGoogleアカウント）
5. 左の **トリガー**（時計アイコン）→ **トリガーを追加**
   - 実行する関数: `poll`
   - イベントのソース: **時間主導型**
   - 間隔: **5分おき**
6. テスト: #consult に `起票して 9`（存在しない番号）→ 5分以内に「番号が見つかりません」と返れば稼働

## 動きのルール

- ダイジェスト投稿（`起票してよければ番号で返信` を含む）を検知 → 番号→件名の表を保存
- 返信の解釈: `2` / `起票して 1,3` / `全部見送り`
- 作成タイトル: `[312][ai_raimo] 件名`・ラベル `SecondBrain, quick`・コメント `【FRIDAY】`＋会議リンク
- 同じ返信を二重処理しない（処理済み ts を state に保存）
- 失敗時は #consult に「❌ 起票できません（理由）」を返す（#ops ではなくスレッド返信で十分）

## 注意

- 5分おき＝最大5分の遅延。即時性が要るなら Slack Events（Cloud Run）へ格上げ
- 番号は「直近のダイジェスト」に対して有効。古い番号を返すと別件になるので、返信は最新投稿に対して行う
- レーンは現状 `ai_raimo` 固定（SB由来のため）。物件ものが混ざるならダイジェスト側にレーン情報を足す

## コード

```javascript
const P = PropertiesService.getScriptProperties();

function poll() {
  const st = JSON.parse(P.getProperty('STATE') || '{}');
  st.proc = st.proc || [];
  const oldest = st.lastTs || String(Math.floor(Date.now() / 1000) - 86400);

  const hist = slack('conversations.history', {
    channel: P.getProperty('CHANNEL_ID'),
    oldest: oldest,
    limit: '50',
  });
  if (!hist.ok) { console.error(hist.error); return; }
  const msgs = (hist.messages || []).slice().reverse();

  msgs.forEach(function (m) {
    if (st.proc.indexOf(m.ts) >= 0) return;

    // 1) ダイジェスト検知
    if (m.text && m.text.indexOf('起票してよければ番号で返信') >= 0) {
      st.map = parseDigest(m.text);
      st.digestTs = m.ts;
      st.proc.push(m.ts);
      return;
    }

    // 2) 人の返信（Bot以外）
    if (m.bot_id || m.subtype) return;
    if (!st.digestTs || Number(m.ts) < Number(st.digestTs)) return;

    const cmd = parseReply(m.text || '');
    if (!cmd) return;
    st.proc.push(m.ts);

    if (cmd.skip) {
      reply(st.digestTs, '見送りで了解（登録しません）');
      return;
    }
    const done = [];
    cmd.nums.forEach(function (n) {
      const title = (st.map || {})[n];
      if (!title) { done.push('#' + n + ' は番号が見つかりません'); return; }
      const r = createTask(title);
      done.push(r.ok ? '#' + n + ' ✅ ' + r.id : '#' + n + ' ❌ ' + r.error);
    });
    reply(st.digestTs, done.join('\n') + '\n`312 cloud chain`');
  });

  st.lastTs = String(Math.floor(Date.now() / 1000));
  st.proc = st.proc.slice(-200);
  P.setProperty('STATE', JSON.stringify(st));
}

function parseDigest(text) {
  const map = {};
  text.split('\n').forEach(function (line) {
    const m = line.match(/^\*(\d+)\.\*\s+(.+?)(?:\s+·\s+<([^|>]+)\|)?$/);
    if (m) map[m[1]] = { title: m[2].replace(/\s+·\s*$/, '').trim(), url: m[3] || '' };
  });
  return map;
}

function parseReply(text) {
  const t = text.trim();
  if (/全部見送り|見送り/.test(t)) return { skip: true };
  const m = t.match(/^(?:起票して\s*)?([0-9]+(?:\s*[,、]\s*[0-9]+)*)$/);
  if (!m) return null;
  return { nums: m[1].split(/[,、]/).map(function (s) { return Number(s.trim()); }) };
}

function createTask(item) {
  const title = '[312][ai_raimo] ' + item.title.replace(/[。．.]$/, '');
  const body = {
    content: title,
    labels: ['SecondBrain', 'quick'],
    description: '312 Slack返信から起票' + (item.url ? '\n出典: ' + item.url : ''),
  };
  const r = todoist('tasks', 'post', body);
  if (!r || !r.id) return { ok: false, error: JSON.stringify(r).slice(0, 120) };
  todoist('comments', 'post', {
    task_id: r.id,
    content: '【FRIDAY】\nサマリ: 312 Slack返信トリガーの①create\nアウトプット:\n- [会議](' + (item.url || 'https://app.todoist.com') + ')',
  });
  return { ok: true, id: r.id };
}

function todoist(path, method, body) {
  const res = UrlFetchApp.fetch('https://api.todoist.com/api/v1/' + path, {
    method: method,
    contentType: 'application/json',
    headers: { Authorization: 'Bearer ' + P.getProperty('TODOIST_TOKEN') },
    payload: JSON.stringify(body),
    muteHttpExceptions: true,
  });
  try { return JSON.parse(res.getContentText()); } catch (e) { return null; }
}

function slack(method, params) {
  const q = Object.keys(params).map(function (k) {
    return k + '=' + encodeURIComponent(params[k]);
  }).join('&');
  const res = UrlFetchApp.fetch('https://slack.com/api/' + method + '?' + q, {
    headers: { Authorization: 'Bearer ' + P.getProperty('SLACK_TOKEN') },
    muteHttpExceptions: true,
  });
  return JSON.parse(res.getContentText());
}

function reply(threadTs, text) {
  const res = UrlFetchApp.fetch('https://slack.com/api/chat.postMessage', {
    method: 'post',
    contentType: 'application/json',
    headers: { Authorization: 'Bearer ' + P.getProperty('SLACK_TOKEN') },
    payload: JSON.stringify({ channel: P.getProperty('CHANNEL_ID'), thread_ts: threadTs, text: text }),
    muteHttpExceptions: true,
  });
  return JSON.parse(res.getContentText());
}
```

## 停止・戻し

- 止める: GAS のトリガーを「削除」または無効化（それだけで起票は止まる）
- 誤起票: Todoist 側で該当タスクを削除（コメントに `cloud chain` の印あり）
- 権限を戻す: Slack アプリの Scope から `channels:history` を外して再インストール
