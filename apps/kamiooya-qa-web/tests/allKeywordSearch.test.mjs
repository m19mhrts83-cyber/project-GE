import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

// まとめてキーワード検索（keyword_all）: 4つのデータソースを1つの入力欄からキーワードで探す（AIは使わない）
function load() {
  const els = {};
  const document = { getElementById: id => els[id] || null, addEventListener() {}, createElement: () => ({}), querySelectorAll: () => [] };
  const app = vm.runInNewContext(readFileSync(new URL('../public/raimo/app.js', import.meta.url), 'utf8') + '\nApp;', { document, window: {}, console, URL });
  app.showToast = () => {};
  return { app, els };
}

test('語は空白（全角も）で区切り、全角英数や大文字もそろえる', () => {
  const { app } = load();
  assert.deepEqual(Array.from(app.allSearchTerms('  原状回復　費用 ＲＣ rc ')), ['原状回復', '費用', 'rc']);
  assert.deepEqual(Array.from(app.allSearchTerms('   ')), []);
});

test('すべての語を含むものだけ当たる（AND）', () => {
  const { app } = load();
  const terms = app.allSearchTerms('原状回復 費用');
  assert.equal(app.allSearchMatches(['退去時の原状回復の費用について', '山田'], terms), true);
  assert.equal(app.allSearchMatches(['原状回復だけ', '費用は別の欄'], terms), true);
  assert.equal(app.allSearchMatches(['原状回復だけ'], terms), false);
  assert.equal(app.allSearchMatches(['何でも'], []), false);
});

test('抜粋は当たった語のまわりを切り出し、印を付け、HTML はエスケープする', () => {
  const { app } = load();
  const long = 'あ'.repeat(100) + '<b>原状回復</b>の費用';
  const html = app.allSearchSnippetHtml(long, app.allSearchTerms('原状回復'));
  assert.match(html, /^…/);
  assert.match(html, /<mark[^>]*>原状回復<\/mark>/);
  assert.match(html, /&lt;b&gt;/);
  assert.doesNotMatch(html, /<b>/);
});

test('4つのデータソースごとに当たりを分ける（講座ページはコミュニティと混ぜない）', () => {
  const { app } = load();
  app.state.comments = [
    { comment_id: '100001', content: '火災保険の見直しで保険料が下がった', author_name: '1234 山田', forum_category: '保険' },
    { comment_id: '100002', content: '別の話', author_name: '2345 佐藤' },
    { comment_id: 'lesson_desc_1', source_system: 'lesson', content: '火災保険の基礎と保険料', course_tab: '基礎', lesson_title: '保険' }
  ];
  app.state.knowledgeSources = { s1: { source_key: 's1', title: '保険セミナー' } };
  app.state.knowledgeChunks = [
    { chunk_key: 'c1', source_key: 's1', content: '火災保険は保険料だけで選ばない', start_sec: 65 },
    { chunk_key: 'c2', source_key: 's1', content: '地震保険の話' }
  ];
  const g = app.allSearchLocalGroups(app.allSearchTerms('火災保険 保険料'));
  assert.deepEqual(Array.from(g.comments.rows, r => r.comment_id), ['100001']);
  assert.deepEqual(Array.from(g.lessons.rows, r => r.comment_id), ['lesson_desc_1']);
  assert.deepEqual(Array.from(g.knowledge.rows, r => r.chunk_key), ['c1']);
});

test('スイッチが見えない人は検索しない・タブも出さない前提（featureOn が false）', async () => {
  const { app, els } = load();
  app.state.features = {}; app.state.featureViewNew = true;
  assert.equal(app.featureOn('keyword_all'), false);
  els.allSearchInput = { value: '保険' };
  els.allSearchResults = { innerHTML: 'そのまま' };
  app.elements.allSearchInput = els.allSearchInput; app.elements.allSearchResults = els.allSearchResults;
  await app.runAllSearch();
  assert.equal(els.allSearchResults.innerHTML, 'そのまま');
  app.state.features = { keyword_all: { members: false } };
  assert.equal(app.featureOn('keyword_all'), true);
});
