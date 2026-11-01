import test from 'node:test';
import assert from 'node:assert/strict';
import { createHandler, issueSession, sessionUser } from '../supabase/functions/community-attachments/index.ts';

const cfg = { projectUrl: 'https://example.supabase.co', serviceKey: 'server-only-key',
  proxySecret: 'proxy-secret-'.repeat(4), sessionSecret: 'session-secret-'.repeat(4),
  raimoOrigin: 'https://app.example', statusUrl: 'https://app.example/status' };
const now = 1800000000000;
const id = 'a'.repeat(64);
const row = { id, bucket: 'community-attachments', storage_path: 'comments/12/' + 'b'.repeat(64) + '.pdf' };
const response = (obj, status = 200) => new Response(JSON.stringify(obj), { status });
const request = (body, token = '', origin = cfg.raimoOrigin) => new Request('https://edge.example', {
  method: 'POST', headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json', ...(origin ? { Origin: origin } : {}) },
  body: JSON.stringify(body),
});

test('session rejects forgery, expiry and altered user id', async () => {
  const token = await issueSession('12', cfg.sessionSecret, now);
  assert.equal(await sessionUser(token, cfg.sessionSecret, now), '12');
  assert.equal(await sessionUser(token + 'x', cfg.sessionSecret, now), null);
  assert.equal(await sessionUser(token, cfg.sessionSecret, now + 28800001), null);
  assert.equal(await sessionUser(await issueSession('13', 'wrong-key', now), cfg.sessionSecret, now), null);
});

test('only Raimo backend may mint a session', async () => {
  const handler = createHandler(cfg, async () => assert.fail('must not fetch'), () => now);
  assert.equal((await handler(request({ operation: 'session', user_id: '12' }, 'browser'))).status, 401);
  const res = await handler(request({ operation: 'session', user_id: '12' }, cfg.proxySecret, null));
  assert.equal(res.status, 200);
  assert.equal(await sessionUser((await res.json()).token, cfg.sessionSecret, now), '12');
});

test('current membership is rechecked and browser user id is ignored', async () => {
  let status = 'approved'; const users = [];
  const handler = createHandler(cfg, async (url, options) => {
    if (url === cfg.statusUrl) { users.push(JSON.parse(options.body).user_id); return response({ user_id: '12', status, role: 'user' }); }
    if (url.includes('/rest/v1/')) return response([row]);
    assert.ok(url.endsWith(row.storage_path));
    return response({ signedURL: '/object/sign/community-attachments/' + row.storage_path + '?token=temporary' });
  }, () => now);
  const token = await issueSession('12', cfg.sessionSecret, now);
  assert.equal((await handler(request({ operation: 'open', attachment_id: id, user_id: 'another-member' }, token))).status, 200);
  status = 'withdrawn';
  assert.equal((await handler(request({ operation: 'open', attachment_id: id }, token))).status, 403);
  assert.deepEqual(users, ['12', '12']);
});

test('unapproved, missing and unknown-role members cannot read metadata', async () => {
  for (const member of [ { user_id: '12', status: 'pending', role: 'user' }, { user_id: '12', status: 'approved', role: 'unknown' }, { user_id: 'different', status: 'approved', role: 'admin' } ]) {
    const handler = createHandler(cfg, async url => {
      assert.equal(url, cfg.statusUrl); return response(member);
    }, () => now);
    assert.equal((await handler(request({ operation: 'index' }, await issueSession('12', cfg.sessionSecret, now)))).status, 403);
  }
});

test('signed URL is generated only from validated metadata and is never cached', async () => {
  let stored = row;
  const handler = createHandler(cfg, async url => {
    if (url === cfg.statusUrl) return response({ user_id: '12', status: 'approved', role: 'master_admin' });
    if (url.includes('/rest/v1/')) return response([stored]);
    return response({ signedURL: '/object/sign/community-attachments/' + row.storage_path + '?token=temporary' });
  }, () => now);
  const token = await issueSession('12', cfg.sessionSecret, now);
  const res = await handler(request({ operation: 'open', attachment_id: id, storage_path: '../private' }, token));
  assert.equal(res.headers.get('cache-control'), 'no-store');
  assert.ok((await res.json()).url.startsWith(cfg.projectUrl + '/storage/v1/object/sign/community-attachments/comments/12/'));
  stored = { ...row, bucket: 'private-other-bucket' };
  assert.equal((await handler(request({ operation: 'open', attachment_id: id }, token))).status, 500);
});

test('10 simultaneous users remain isolated', async () => {
  const checked = [];
  const handler = createHandler(cfg, async (url, options) => {
    if (url === cfg.statusUrl) {
      const uid = JSON.parse(options.body).user_id; checked.push(uid);
      await new Promise(resolve => setTimeout(resolve, Number(uid) % 3));
      return response({ user_id: uid, status: 'approved', role: 'user' });
    }
    return response([]);
  }, () => now);
  const results = await Promise.all(Array.from({ length: 10 }, async (_, i) => {
    const uid = String(i + 1);
    return handler(request({ operation: 'index', user_id: 'spoof' }, await issueSession(uid, cfg.sessionSecret, now)));
  }));
  assert.ok(results.every(r => r.status === 200));
  assert.deepEqual(checked.sort(), Array.from({ length: 10 }, (_, i) => String(i + 1)).sort());
});

test('wrong origins and unauthenticated requests cannot call upstream', async () => {
  const handler = createHandler(cfg, async () => assert.fail('must not call upstream'), () => now);
  assert.equal((await handler(request({ operation: 'index' }, '', 'https://attacker.example'))).status, 403);
  assert.equal((await handler(request({ operation: 'index' }))).status, 401);
});
