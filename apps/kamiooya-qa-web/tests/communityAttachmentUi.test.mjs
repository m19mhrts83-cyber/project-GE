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
function load(path,transport) {
  const document = { getElementById:()=>null, addEventListener() {}, createElement: () => new Element(), createTextNode: text => ({ textContent: text }) };
  const window={};
  const app=vm.runInNewContext(readFileSync(path, 'utf8') + '\nApp;', { document, window, console, URL, fetch: transport || (() => { throw new Error('unexpected fetch'); }) });
  app.testWindow=window;return app;
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
  test(source.pathname + ': LINE citations and file links use the exact source and reject another bucket',async()=>{
    const app=load(source),host=new Element(),id='a'.repeat(64),sid='oc_'+id;
    app.state.attachmentIndex={['openchat:'+sid]:[{id,original_name:'見積.pdf'}]};
    app.appendAttachmentLinks(host,sid,'添付：','openchat');
    assert.equal(host.children[0].children[1].textContent,'見積.pdf');
    const targets=[],requests=[],errors=[];
    app.testWindow.open=()=>{const t={opener:{},location:{replace:url=>{t.url=url;}},close(){t.closed=true;}};targets.push(t);return t;};
    app.showToast=message=>errors.push(message);
    let wrong=false;
    app.attachmentRequest=async(body)=>{requests.push(body);return {url:'https://mwubzgefkkjjbingrmqu.supabase.co/storage/v1/object/sign/'+(wrong?'community-attachments':'openchat-attachments')+'/objects/'+id+'?token=fixture'};};
    await host.children[0].children[1].listeners.click({preventDefault(){}});
    assert.equal(requests[0].source,'openchat');assert.equal(requests[0].attachment_id,id);
    assert.match(targets[0].url,/\/openchat-attachments\/objects\//);assert.equal(targets[0].opener,null);
    wrong=true;await host.children[0].children[1].listeners.click({preventDefault(){}});
    assert.equal(targets[1].closed,true);assert.equal(errors.length,1);
    const html=app.renderCitationsPanel([{kind:'openchat',openchatId:sid,chatTitle:'修繕',snippet:'見積.pdf',citationLabel:'LINEオプチャ1'}],'m','LINEオプチャ1');
    assert.ok(html.includes('data-openchat-source-id="'+sid+'"'));assert.ok(html.includes('本文で引用した根拠'));
  });
  test(source.pathname + ': LINE source table renders its own attachment and filename search preserves source identity',async()=>{
    const id='a'.repeat(64),sid='oc_'+id,requests=[];
    const row={id:sid,chat_title:'修繕',content:'【LINE添付・内容未解析】見積.pdf'};
    const app=load(source,async(url,opts)=>{requests.push(JSON.parse(opts.body));return {ok:true,text:async()=>JSON.stringify({relatedOpenchat:[row]})};});
    const slot=new Element();slot.getAttribute=()=>sid;
    const tbody={innerHTML:'',querySelectorAll:()=>[slot]};
    app.elements.openchatTableBody=tbody;app.elements.openchatSearchInput={value:'見積.pdf'};
    app.elements.openchatAttachmentsOnly={checked:true};app.elements.openchatTitleFilter={value:''};
    app.renderOpenchatTitleFilterOptions=()=>{};
    app.resolveSemanticConfig=async()=>({url:'https://gateway.example',secret:'fixture'});
    app.state.attachmentIndex={['openchat:'+sid]:[{id,original_name:'見積.pdf'}]};
    await app.loadOpenchatLogs();
    assert.equal(requests[0].only_attachments,true);assert.equal(requests[0].query,'見積.pdf');
    assert.ok(tbody.innerHTML.includes(sid));assert.equal(slot.children[0].children[1].textContent,'見積.pdf');
  });
  test(source.pathname + ': a LINE source read finishing after logout cannot restore its data',async()=>{
    let resolve,started;
    const reached=new Promise(r=>{started=r;});
    const app=load(source,()=>new Promise(r=>{resolve=r;started();}));
    app.resolveSemanticConfig=async()=>({url:'https://gateway.example',secret:'fixture'});
    app.state.currentUser={id:'one'};app.state.attachmentGeneration=1;
    const pending=app.loadOpenchatLogs();await reached;
    app.state.currentUser=null;app.state.attachmentGeneration=2;
    resolve({ok:true,text:async()=>JSON.stringify({relatedOpenchat:[{id:'old-user-data'}]})});
    await pending;assert.equal(app.state.openchatLogs.length,0);
  });
  test(source.pathname + ': changing LINE search ignores an older response arriving last',async()=>{
    const pending=[],starts=[];
    const app=load(source,()=>new Promise(resolve=>{pending.push(resolve);if(starts[pending.length-1])starts[pending.length-1]();}));
    app.resolveSemanticConfig=async()=>({url:'https://gateway.example',secret:'fixture'});
    app.elements.openchatSearchInput={value:'old.pdf'};
    app.renderOpenchatTitleFilterOptions=()=>{};
    const rendered=[];app.renderOpenchatTable=()=>rendered.push(app.state.openchatLogs[0].id);
    const firstStarted=new Promise(r=>{starts[0]=r;});
    const older=app.loadOpenchatLogs();await firstStarted;
    app.elements.openchatSearchInput.value='new.pdf';
    const secondStarted=new Promise(r=>{starts[1]=r;});
    const newer=app.loadOpenchatLogs();await secondStarted;
    const result=id=>({ok:true,text:async()=>JSON.stringify({relatedOpenchat:[{id}]})});
    pending[1](result('new'));await newer;
    pending[0](result('old'));await older;
    assert.equal(app.state.openchatLogs[0].id,'new');assert.deepEqual(rendered,['new']);
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
