const P = PropertiesService.getScriptProperties();
const DIGEST_MARKER = '起票してよければ番号で返信';
const LOOKBACK_H = 48;

function poll() {
  const st = getState_();
  const channel = P.getProperty('CHANNEL_ID');
  const slack = P.getProperty('SLACK_TOKEN');
  const oldest = st.lastTs || String(Math.floor(Date.now() / 1000) - LOOKBACK_H * 3600);

  const hist = slackGet_('conversations.history', { channel: channel, oldest: oldest, limit: '100' });
  if (!hist.ok) { Logger.log('history error: ' + hist.error); return; }
  const msgs = (hist.messages || []).slice().sort(function (a, b) { return Number(a.ts) - Number(b.ts); });

  let digest = null;
  for (let i = msgs.length - 1; i >= 0; i--) {
    if ((msgs[i].text || '').indexOf(DIGEST_MARKER) >= 0) { digest = msgs[i]; break; }
  }
  if (!digest) { Logger.log('no digest'); st.lastTs = nowTs_(); saveState_(st); return; }

  const items = parseDigest_(digest.text || '');
  const thread = slackGet_('conversations.replies', { channel: channel, ts: digest.ts, limit: '200' });
  const replies = thread.ok ? (thread.messages || []) : [];
  const handled = handledNums_(replies);

  for (let i = 0; i < replies.length; i++) {
    const m = replies[i];
    if (m.bot_id || m.subtype) continue;
    if (Number(m.ts) <= Number(digest.ts)) continue;
    const cmd = parseReply_(m.text || '');
    if (!cmd) continue;

    if (cmd.skip) {
      if (handled.skip) continue;
      postThread_(digest.ts, '見送りで了解（登録しません）');
      handled.skip = true;
      continue;
    }
    const lines = [];
    for (let j = 0; j < cmd.nums.length; j++) {
      const n = cmd.nums[j];
      if (handled.nums[n]) { lines.push('#' + n + ' は処理済み'); continue; }
      const item = items[n];
      if (!item) { lines.push('#' + n + ' は番号が見つかりません'); continue; }
      const r = createTask_(item);
      lines.push(r.ok ? '#' + n + ' ✅ ' + r.title : '#' + n + ' ❌ ' + (r.error || ''));
      handled.nums[n] = true;
    }
    postThread_(digest.ts, lines.join('\n') + '\n`312 cloud chain`');
  }

  st.lastTs = nowTs_();
  saveState_(st);
}

function nowTs_() { return String(Math.floor(Date.now() / 1000)); }

function getState_() {
  try { return JSON.parse(P.getProperty('STATE') || '{}'); } catch (e) { return {}; }
}
function saveState_(st) { P.setProperty('STATE', JSON.stringify(st)); }

function parseDigest_(text) {
  const items = {};
  const lines = text.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(/^\*(\d+)\.\*\s+(.+?)(?:\s+·\s+<([^|>]+)\|[^>]*>)?\s*$/);
    if (m) items[Number(m[1])] = { title: clean_(m[2]), url: m[3] || '' };
  }
  return items;
}

function clean_(t) {
  return String(t || '').replace(/\s+/g, ' ').replace(/\s*[—–-]\s*状況[:：].*$/, '').replace(/[（(]状況[:：][^）)]*[）)]/g, '').trim().replace(/[。．.]$/, '');
}

function parseReply_(text) {
  const t = String(text || '').trim();
  if (!t) return null;
  if (/全部見送り|見送りで/.test(t)) return { skip: true };
  const m = t.match(/^(?:起票して\s*)?([0-9]+(?:\s*[,、]\s*[0-9]+)*)$/);
  if (!m) return null;
  return { nums: m[1].split(/[,、]/).map(function (s) { return Number(s.trim()); }) };
}

function handledNums_(replies) {
  const out = { nums: {}, skip: false };
  for (let i = 0; i < replies.length; i++) {
    if (!replies[i].bot_id) continue;
    const text = replies[i].text || '';
    const re = /#(\d+)\s*(?:✅|済)/g;
    let m;
    while ((m = re.exec(text)) !== null) out.nums[Number(m[1])] = true;
    if (text.indexOf('見送りで了解') >= 0) out.skip = true;
  }
  return out;
}

function createTask_(item) {
  const title = '[312][ai_raimo] ' + item.title;
  const body = {
    content: title,
    labels: ['SecondBrain', 'quick'],
    description: '312 Slack返信トリガーの①create' + (item.url ? '\n出典: ' + item.url : ''),
  };
  const res = todoist_('tasks', 'post', body);
  if (!res || !res.id) return { ok: false, error: JSON.stringify(res).slice(0, 120) };
  try {
    todoist_('comments', 'post', {
      task_id: res.id,
      content: '【FRIDAY】\nサマリ: 312 Slack返信トリガーの①create\nアウトプット:\n- [会議](' + (item.url || 'https://app.todoist.com') + ')',
    });
  } catch (e) { Logger.log('comment failed: ' + e); }
  return { ok: true, id: res.id, title: title };
}

function todoist_(path, method, body) {
  const res = UrlFetchApp.fetch('https://api.todoist.com/api/v1/' + path, {
    method: method,
    contentType: 'application/json',
    headers: { Authorization: 'Bearer ' + P.getProperty('TODOIST_TOKEN') },
    payload: JSON.stringify(body),
    muteHttpExceptions: true,
  });
  try { return JSON.parse(res.getContentText()); } catch (e) { return null; }
}

function slackGet_(method, params) {
  const q = Object.keys(params).map(function (k) { return k + '=' + encodeURIComponent(params[k]); }).join('&');
  const res = UrlFetchApp.fetch('https://slack.com/api/' + method + '?' + q, {
    headers: { Authorization: 'Bearer ' + P.getProperty('SLACK_TOKEN') },
    muteHttpExceptions: true,
  });
  return JSON.parse(res.getContentText());
}

function postThread_(ts, text) {
  const res = UrlFetchApp.fetch('https://slack.com/api/chat.postMessage', {
    method: 'post',
    contentType: 'application/json',
    headers: { Authorization: 'Bearer ' + P.getProperty('SLACK_TOKEN') },
    payload: JSON.stringify({ channel: P.getProperty('CHANNEL_ID'), thread_ts: ts, text: text }),
    muteHttpExceptions: true,
  });
  return JSON.parse(res.getContentText());
}
