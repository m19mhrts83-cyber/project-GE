import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

class Element {
  children = []; listeners = {}; className = ''; textContent = '';
  set innerHTML(value) { this.children = []; }
  get innerHTML() { return ''; }
  appendChild(child) { this.children.push(child); child.parent = this; }
  querySelector() { return this.children.find(x => (x.className || '').includes('community-attachment-links')) || null; }
  remove() { this.parent.children = this.parent.children.filter(x => x !== this); }
  addEventListener(name, fn) { this.listeners[name] = fn; }
}
function load(path) {
  const document = { getElementById:()=>null, addEventListener() {}, createElement: () => new Element(), createTextNode: text => ({ textContent: text }) };
  return vm.runInNewContext(readFileSync(path, 'utf8') + '\nApp;', { document, window: {}, console, URL, fetch: () => { throw new Error('unexpected fetch'); } });
}
const sources = [new URL('../public/raimo/app.js', import.meta.url), new URL('../../../215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/app.js', import.meta.url)];
for (const source of sources) {
  test(source.pathname + ': late login response cannot overwrite another user', async () => {
    const app = load(source); let resolve;
    app.state.currentUser = { id: 'one' }; app.state.attachmentGeneration = 1;
    app.apiClient = () => new Promise(r => { resolve = r; });
    const loading = app.initializeAttachments('old@example.com', 'not-persisted', 1);
    app.state.currentUser = { id: 'two' }; app.state.attachmentGeneration = 2; app.state.attachmentToken = 'new-session';
    resolve({ token: 'old-session' }); await loading;
    assert.equal(app.state.attachmentToken, 'new-session');
    assert.equal(JSON.stringify(app.state).includes('not-persisted'), false);
  });
  test(source.pathname + ': filenames are text and repeated renders do not duplicate links', () => {
    const app = load(source); const host = new Element();
    app.state.attachmentIndex = { '12': [{ id: 'a', original_name: '<img src=x onerror=alert(1)>.pdf' }] };
    app.appendAttachmentLinks(host, '12'); app.appendAttachmentLinks(host, '12');
    assert.equal(host.children.length, 1);
    assert.equal(host.children[0].children[1].textContent, '<img src=x onerror=alert(1)>.pdf');
    assert.equal(host.children[0].children[1].href, '#attachment-a');
    const empty = new Element(); app.appendAttachmentLinks(empty, 'none'); assert.equal(empty.children.length, 0);
  });
  test(source.pathname + ': large comment lists remain paged and exact search reaches old attachments', () => {
    const app = load(source);
    app.state.comments = Array.from({length: 250}, (_,i) => ({comment_id: String(20000+i), content: 'body', author_name: 'author'}));
    app.elements.commentTableBody = new Element(); app.elements.commentListMeta = new Element();
    app.elements.commentSearchInput = {value: ''};
    app.isLessonCommentRow = () => false; app.commentField = (row,k) => row[k] || '';
    app.hasPostedAtValue = () => true; app.parseWeStudyAuthorName = () => ({raw:'author'});
    app.renderCommentTable(); assert.equal(app.elements.commentTableBody.children.length,100);
    app.renderCommentTable({offset:200}); assert.equal(app.elements.commentTableBody.children.length,50);
    app.elements.commentSearchInput.value='20249'; app.renderCommentTable();
    assert.equal(app.elements.commentTableBody.children.length,1);
    assert.match(app.elements.commentListMeta.textContent, /検索結果 1 /);
  });

}
