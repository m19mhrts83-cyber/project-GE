import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

// (1) 使用量の削減が見える人は、意味検索がふだんの検索で、ボタンは「より詳しく調べる」になる
function load() {
  const els = { semanticModeHint: { textContent: '通常検索はキーワード一致を優先し…' } };
  const document = { getElementById: id => els[id] || null, addEventListener() {}, createElement: () => ({}) };
  const app = vm.runInNewContext(readFileSync(new URL('../public/raimo/app.js', import.meta.url), 'utf8') + '\nApp;', { document, window: {}, console, URL });
  app.authGatewayBase = 'https://g.example';
  // 2026-11-19 ボタンはスイッチの形（中身は innerHTML、状態は aria-label / aria-pressed）
  app.elements.semanticModeToggle = { innerHTML: '', className: '', title: '', attrs: {}, setAttribute(k, v) { this.attrs[k] = v; } };
  app.showToast = () => {};
  return { app, els };
}

test('スイッチが見える人: 意味検索がふだん、ボタンで「より詳しく調べる」(deep) に切り替わる', () => {
  const { app, els } = load();
  app.state.features = { cost_saving: { members: false } }; app.state.featureViewNew = true;
  app.applySearchModeUi();
  assert.equal(app.currentAnswerMode(false), 'semantic');
  assert.equal(app.elements.semanticModeToggle.attrs['aria-label'], 'より詳しく調べる：OFF');
  assert.match(els.semanticModeHint.textContent, /より詳しく調べる/);
  app.handleSemanticModeToggle();
  assert.equal(app.currentAnswerMode(false), 'deep');
  assert.equal(app.currentAnswerMode(true), 'fast');
  assert.equal(app.elements.semanticModeToggle.attrs['aria-label'], 'より詳しく調べる：ON');
  assert.equal(app.elements.semanticModeToggle.attrs['aria-pressed'], 'true');
  assert.match(app.elements.semanticModeToggle.className, /is-on/);
  // 「会員として見る」などでスイッチが外れたら、前の表示（意味検索モード: OFF・通常検索）に戻る
  app.state.featureViewNew = false;
  app.applySearchModeUi();
  assert.equal(app.currentAnswerMode(false), 'normal');
  assert.equal(app.elements.semanticModeToggle.attrs['aria-label'], '意味検索モード：OFF');
  assert.match(els.semanticModeHint.textContent, /通常検索/);
});

test('スイッチが見えない人は今までどおり', () => {
  const { app } = load();
  app.state.features = {}; app.applySearchModeUi();
  assert.equal(app.currentAnswerMode(false), 'normal');
  assert.equal(app.elements.semanticModeToggle.attrs['aria-label'], '意味検索モード：OFF');
});
