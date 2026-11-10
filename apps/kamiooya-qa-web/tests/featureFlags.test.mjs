import test from 'node:test';
import assert from 'node:assert/strict';
import { featureAllowed, featuresFor, requireFeature } from '../lib/featureFlags.ts';
import { createRaimoAuthGateway } from '../lib/raimoAuthGateway.ts';

const owner = { id: 'o1', email: 'Owner@Example.test' };
const reviewer = { id: 'r1', email: 'rev@example.test' };
const admin = { id: 'a1', email: 'admin@example.test' }; // 管理者でも名指しが無ければ見えない
const flag = stage => ({ feature: 'answer_feedback', stage, owner_ids: ['owner@example.test'], reviewer_ids: ['r1'] });

test('段階ごとに見える人が広がり、管理者というだけでは見えない', () => {
  assert.deepEqual([owner, reviewer, admin].map(u => featureAllowed(flag('off'), u)), [false, false, false]);
  assert.deepEqual([owner, reviewer, admin].map(u => featureAllowed(flag('owner'), u)), [true, false, false]);
  assert.deepEqual([owner, reviewer, admin].map(u => featureAllowed(flag('reviewers'), u)), [true, true, false]);
  assert.deepEqual([owner, reviewer, admin].map(u => featureAllowed(flag('all'), u)), [true, true, true]);
});

test('壊れた行・知らない段階・行なしはオフ', () => {
  assert.equal(featureAllowed(undefined, owner), false);
  assert.equal(featureAllowed({ feature: 'x', stage: 'everyone', owner_ids: ['o1'] }, owner), false);
  assert.equal(featureAllowed({ feature: 'x', stage: 'owner', owner_ids: 'o1' }, owner), false);
});

test('一覧には見えている機能と会員公開の有無だけを返し、名簿は返さない', () => {
  const out = featuresFor([flag('reviewers'), { feature: 'cost_saving', stage: 'all' }, { feature: 'auto_approval', stage: 'off' }], reviewer);
  assert.deepEqual(out, { features: { answer_feedback: { members: false }, cost_saving: { members: true } } });
  assert.equal(JSON.stringify(out).includes('owner@example.test'), false);
});

test('requireFeature は見えない人を 404 で止める', () => {
  assert.doesNotThrow(() => requireFeature([flag('owner')], 'answer_feedback', owner));
  assert.throws(() => requireFeature([flag('owner')], 'answer_feedback', admin), e => e.status === 404 && e.code === 'feature_not_available');
});

test('/features はログインした本人で判定し、読めなければ全部オフ', async () => {
  const origin = 'https://offline.example';
  const members = { o1: { id: 'o1', email: 'owner@example.test', role: 'master_admin', status: 'approved', authVersion: '1' },
    a1: { id: 'a1', email: 'admin@example.test', role: 'admin', status: 'approved', authVersion: '1' } };
  let broken = false;
  const sessions = new Map([['a'.repeat(64), { uid: 'o1', authVersion: '1', expires: Date.now() + 60000 }], ['b'.repeat(64), { uid: 'a1', authVersion: '1', expires: Date.now() + 60000 }]]);
  const handler = createRaimoAuthGateway({ origin, member: async id => members[id] || null,
    sessions: { get: async t => sessions.get(t) || null, put: async () => {}, delete: async () => {} },
    authenticate: async () => null, allowLogin: async () => true, chatOwner: async () => null,
    forward: async () => { throw new Error('should not forward'); }, attachmentSession: async () => ({}),
    featureFlags: async () => { if (broken) throw new Error('db down'); return [flag('owner')]; } });
  const get = async t => (await handler(new Request('https://g.example/features', { method: 'GET', headers: { Origin: origin, Authorization: 'Bearer ' + t } }))).json();
  assert.deepEqual(await get('a'.repeat(64)), { features: { answer_feedback: { members: false } } });
  assert.deepEqual(await get('b'.repeat(64)), { features: {} });
  broken = true;
  assert.deepEqual(await get('a'.repeat(64)), { features: {} });
  const anon = await handler(new Request('https://g.example/features', { method: 'GET', headers: { Origin: origin } }));
  assert.equal(anon.status, 401);
});
