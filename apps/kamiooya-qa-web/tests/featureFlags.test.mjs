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
  assert.deepEqual(out, { features: { answer_feedback: { members: false }, cost_saving: { members: true } }, preview: true });
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
  assert.deepEqual(await get('a'.repeat(64)), { features: { answer_feedback: { members: false } }, preview: true });
  assert.deepEqual(await get('b'.repeat(64)), { features: {}, preview: false });
  broken = true;
  assert.deepEqual(await get('a'.repeat(64)), { features: {}, preview: false });
  const anon = await handler(new Request('https://g.example/features', { method: 'GET', headers: { Origin: origin } }));
  assert.equal(anon.status, 401);
});

test('確認用の帯(preview)は名指しの人だけ。全員公開の機能しか無い会員・管理者には出さない', () => {
  const flags = [{ feature: 'cost_saving', stage: 'all', owner_ids: ['o1'] }, { feature: 'design_theme', stage: 'all', owner_ids: ['o1'] }];
  const member = featuresFor(flags, { id: 'm9', email: 'member@example.test' });
  assert.equal(member.preview, false);
  assert.deepEqual(Object.keys(member.features), ['cost_saving', 'design_theme']);
  assert.equal(featuresFor(flags, { id: 'o1', email: '' }).preview, true); // 全部 all でも名指しの本人は帯が見える
});

test('admins の段階: 管理者の役割の人には会員と同じ見え方で出し、会員・役割不明には出さない', async () => {
  const { featureAllowed, featuresFor } = await import('../lib/featureFlags.ts');
  const flag = { feature: 'change_log', stage: 'admins', owner_ids: ['owner@example.test'], reviewer_ids: [] };
  assert.equal(featureAllowed(flag, { id: '5', email: 'a@example.test', role: 'admin' }), true);
  assert.equal(featureAllowed(flag, { id: '6', email: 'm@example.test', role: 'master_admin' }), true);
  assert.equal(featureAllowed(flag, { id: '7', email: 'u@example.test', role: 'user' }), false);
  assert.equal(featureAllowed(flag, { id: '8', email: 'x@example.test' }), false);
  assert.equal(featureAllowed(flag, { id: '1', email: 'owner@example.test' }), true);
  const r = featuresFor([flag], { id: '5', email: 'a@example.test', role: 'admin' });
  assert.deepEqual(r.features.change_log, { members: true });
  assert.equal(r.preview, false);
});
