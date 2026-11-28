import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

// 確認用の帯には、会員全員に公開済みの機能を並べない（2026-11-18 松野さん「上がごちゃごちゃしてきた」）
function load() {
  const cls = () => { const s = new Set(['hidden']); return { toggle: (c, on) => (on ? s.add(c) : s.delete(c)), contains: c => s.has(c) }; };
  const els = {
    featurePreviewBar: { classList: cls(), dataset: {} },
    featureViewNewToggle: { checked: false, addEventListener() {} },
    featureAsMemberToggle: { checked: false, addEventListener() {} },
    featurePreviewList: { textContent: '' },
  };
  const document = { getElementById: id => els[id] || null, addEventListener() {}, createElement: () => ({}) };
  const app = vm.runInNewContext(readFileSync(new URL('../../../215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/app.js', import.meta.url), 'utf8') + '\nApp;', { document, window: {}, console, URL });
  return { app, els };
}

test('公開済みは帯に出さず、未公開だけを並べる', () => {
  const { app, els } = load();
  app.state.featurePreview = true; app.state.featureViewNew = true;
  app.state.features = { cost_saving: { members: true }, keyword_all: { members: true }, openchat_ranking: { members: false }, mobile_layout: { members: false } };
  app.renderFeaturePreviewBar();
  assert.equal(els.featurePreviewBar.classList.contains('hidden'), false);
  const t = els.featurePreviewList.textContent;
  assert.match(t, /オープンチャットの質問ランキング/);
  assert.match(t, /スマホ縦の表示/);
  assert.doesNotMatch(t, /使用量の削減|キーワード検索|公開中/);
});

test('未公開が無ければ帯ごと出さない', () => {
  const { app, els } = load();
  app.state.featurePreview = true;
  app.state.features = { cost_saving: { members: true } };
  app.renderFeaturePreviewBar();
  assert.equal(els.featurePreviewBar.classList.contains('hidden'), true);
});

test('「新しい版で見る」を外しても、公開済みの機能は会員と同じく出る', () => {
  const { app } = load();
  app.state.features = { cost_saving: { members: true }, openchat_ranking: { members: false } };
  app.state.featureViewNew = false;
  assert.equal(app.featureOn('cost_saving'), true);
  assert.equal(app.featureOn('openchat_ranking'), false);
  app.state.featureViewNew = true;
  assert.equal(app.featureOn('openchat_ranking'), true);
});
