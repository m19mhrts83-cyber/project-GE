import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

// いいね＝理由は聞かない／超いいね＝良かった理由／悪いね＝何が悪かったか（2026-11-10）
function load(path) {
  const document = { getElementById: () => null, addEventListener() {}, createElement: () => ({}), createTextNode: t => ({ textContent: t }) };
  return vm.runInNewContext(readFileSync(path, 'utf8') + '\nApp;', { document, window: {}, console, URL, fetch: () => { throw new Error('unexpected fetch'); } });
}
class El {
  constructor(attrs = {}) { this.attrs = attrs; this.listeners = {}; this.hidden = true; this.value = ''; this.textContent = ''; this.className = ''; }
  getAttribute(k) { return this.attrs[k] ?? null; }
  setAttribute(k, v) { this.attrs[k] = v; }
  addEventListener(n, fn) { this.listeners[n] = fn; }
  get classList() { const el = this; return { toggle(c, on) { if (c === 'hidden') el.hidden = !!on; }, remove(c) { if (c === 'hidden') el.hidden = false; } }; }
}
function fakeBox() {
  const btns = ['great', 'good', 'bad'].map(r => new El({ 'data-rating': r }));
  const input = new El(), question = new El(), send = new El(), status = new El();
  const wrap = new El(); wrap.querySelector = s => s === 'input' ? input : s === '.answer-feedback-question' ? question : null;
  const box = new El({ 'data-message-id': 'm2' });
  box.querySelector = s => ({ '.answer-feedback-status': status, '.answer-feedback-comment': wrap, '.answer-feedback-comment input': input, '.answer-feedback-send': send })[s] || null;
  box.querySelectorAll = s => s === '.answer-feedback-btn' ? btns : [];
  return { box, btns, input, question, wrap, send, status };
}
const tick = () => new Promise(r => setTimeout(r, 0));
const sources = [new URL('../public/raimo/app.js', import.meta.url), new URL('../../../215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/app.js', import.meta.url)];
for (const source of sources) {
  test(source.pathname + ': 評価ごとに聞くことを変える', async () => {
    const app = load(source); const sent = [];
    app.state.currentSessionId = 'c1';
    app.apiClient = async (_m, _p, body) => { sent.push({ rating: body.rating, comment: body.comment }); return { ok: true }; };
    const f = fakeBox(); app.bindFeedbackBox(f.box);
    const [great, good, bad] = f.btns;

    good.listeners.click(); await tick();
    assert.deepEqual(sent.at(-1), { rating: 'good', comment: '' });
    assert.equal(f.wrap.hidden, true); // いいねは理由を聞かない

    great.listeners.click(); await tick();
    assert.deepEqual(sent.at(-1), { rating: 'great', comment: '' }); // 評価は先に保存
    assert.equal(f.wrap.hidden, false);
    assert.equal(f.question.textContent, 'どこが特に良かったですか？');
    f.input.value = ' 具体例が良い '; f.send.listeners.click(); await tick();
    assert.deepEqual(sent.at(-1), { rating: 'great', comment: '具体例が良い' });

    bad.listeners.click(); await tick();
    assert.deepEqual(sent.at(-1), { rating: 'bad', comment: '' }); // 超いいねの理由を悪いねに持ち越さない
    assert.equal(f.question.textContent, '何が良くなかったですか？');

    f.input.value = '古い'; good.listeners.click(); await tick();
    assert.deepEqual(sent.at(-1), { rating: 'good', comment: '' }); // いいねに変えたら意見は消す
    assert.equal(f.wrap.hidden, true);
  });

  test(source.pathname + ': 保存済みの評価で再描画しても同じ聞き方', () => {
    const app = load(source);
    app.state.feedbackByMessage = { a: { rating: 'good', sent: true }, b: { rating: 'great', comment: 'x', sent: true }, c: { rating: 'bad', sent: true } };
    assert.match(app.renderFeedbackBox('a'), /answer-feedback-comment hidden/);
    assert.match(app.renderFeedbackBox('b'), /どこが特に良かったですか？/);
    assert.match(app.renderFeedbackBox('c'), /何が良くなかったですか？/);
    assert.doesNotMatch(app.renderFeedbackBox('c'), /answer-feedback-comment hidden/);
  });
}
