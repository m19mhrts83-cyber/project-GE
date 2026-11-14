from playwright.sync_api import sync_playwright
import base64,json,time,os,tempfile
from pathlib import Path
import urllib.request
BASE='http://127.0.0.1:6419';OWNER='11111111-1111-4111-8111-111111111111';OTHER='22222222-2222-4222-8222-222222222222';PROOF='33333333-3333-4333-8333-333333333333'
OUT=Path(os.environ.get('ASSET618_TEST_OUT') or tempfile.mkdtemp(prefix='asset618-browser-'));OUT.mkdir(exist_ok=True)
def enc(x):return base64.urlsafe_b64encode(json.dumps(x).encode()).decode().rstrip('=')
def cookie(uid):
 token=enc({'alg':'HS256','typ':'JWT'})+'.'+enc({'sub':uid,'aud':'authenticated','role':'authenticated','exp':int(time.time())+3600})+'.'+enc('fixture')
 session={'access_token':token,'refresh_token':'fixture-refresh','expires_at':int(time.time())+3600,'expires_in':3600,'token_type':'bearer','user':{'id':uid,'email':'fixture@example.invalid','aud':'authenticated','role':'authenticated'}}
 return {'name':'sb-127-auth-token','value':'base64-'+enc(session),'domain':'127.0.0.1','path':'/'}
def mode(value):
 req=urllib.request.Request('http://127.0.0.1:6418/__fixture/mode',data=json.dumps({'mode':value}).encode(),headers={'Content-Type':'application/json'})
 urllib.request.urlopen(req).read()
results=[]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 anon=browser.new_context();page=anon.new_page();page.goto(BASE+'/portfolio/evidence');page.wait_for_url('**/login?**');results.append('unauthenticated_redirected')
 context=browser.new_context(viewport={'width':1280,'height':1000});context.add_cookies([cookie(OWNER)])
 page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
 page.goto(BASE+'/portfolio');card=page.get_by_role('region',name='618 資産記録の確認');card.wait_for(timeout=60000)
 card.get_by_text('DB読戻し確認済み 1件 / 未取得・未確認 1件').wait_for(timeout=30000)
 card.get_by_text('今回の記録を確認する').click();card.get_by_text('検証用 SBI',exact=True).wait_for();results.append('numeric_status_and_unknown_source_date_rendered')
 card.get_by_role('button',name='表示を照合して記録').click();card.get_by_role('status').filter(has_text='1件一致・未確認1件').wait_for();results.append('browser_to_api_to_db_receipt_matched_subset')
 card.screenshot(path=str(OUT/'数値の保存と画面照合.png'))
 page.locator('[data-field="value"]').first.evaluate("node => node.textContent = '999'")
 card.get_by_role('button',name='表示を照合して記録').click();card.get_by_role('status').filter(has_text='一致していません').wait_for();results.append('tampered_display_rejected')
 mode('changed_db');page.reload();card=page.get_by_role('region',name='618 資産記録の確認');card.get_by_role('button',name='表示を照合して記録').wait_for();assert card.get_by_role('button',name='表示を照合して記録').is_disabled();results.append('changed_db_disables_confirmation')
 mode('normal');page.goto(BASE+'/portfolio/evidence');page.get_by_text('今回の更新失敗・前回の正常画像を保持').wait_for(timeout=30000)
 page.get_by_text('正常画像を開く').click();img=page.get_by_alt_text('保存済み資産証拠');img.wait_for();page.wait_for_function("Array.from(document.images).some(i => i.alt === '保存済み資産証拠' && i.complete && i.naturalWidth === 1000)");results.append('previous_normal_proof_visible_after_failed_update')
 response=context.request.get(BASE+'/api/portfolio/evidence/'+PROOF);assert response.status==200;assert 'no-store' in response.headers['cache-control'];assert response.headers['content-type']=='image/png';results.append('authenticated_proxy_png_no_store')
 page.screenshot(path=str(OUT/'最新証拠_検証用データ.png'),full_page=True)
 page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(OUT/'最新証拠_iPhone幅_検証用データ.png'),full_page=True)
 assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'mobile overflow';results.append('mobile_390_no_overflow')
 mode('bad_image');page.reload();page.get_by_text('正常画像を開く').click();page.get_by_role('alert').filter(has_text='画像の取得').wait_for();results.append('bad_storage_hash_blocks_image_and_shows_error')
 mode('unavailable');page.reload();page.get_by_role('alert').filter(has_text='証拠の記録').wait_for();results.append('database_unavailability_not_shown_as_no_images')
 mode('normal');other=browser.new_context();other.add_cookies([cookie(OTHER)]);op=other.new_page();op.goto(BASE+'/portfolio/evidence');op.get_by_text('このアカウントには証拠の閲覧権限が設定されていません。').wait_for();assert other.request.get(BASE+'/api/portfolio/evidence/'+PROOF).status==403;results.append('other_authenticated_user_denied')
 assert not errors,errors
 results.append('no_browser_javascript_errors')
 browser.close()
(OUT/'検証結果.json').write_text(json.dumps({'data':'synthetic_only','checks':results,'count':len(results),'production_writes':0},ensure_ascii=False,indent=2))
print(json.dumps({'browser_checks':len(results),'checks':results},ensure_ascii=False))
