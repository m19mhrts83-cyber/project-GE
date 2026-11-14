import Shell from '@/components/Shell';
import Asset618Preview from '@/components/Asset618Preview';
import {createClient} from '@/lib/supabase/server';
import {assetOwner} from '@/lib/asset618Server';
import {evidenceState, UUID} from '@/lib/asset618Contract';
import {redirect} from 'next/navigation';
export const dynamic = 'force-dynamic';
const time = (value: string | null) => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'}) : 'なし';
export default async function EvidencePage() {
  const client = await createClient();
  const {data:{user}} = await client.auth.getUser();
  if (!user) redirect('/login?next=/portfolio/evidence');
  const owner = await assetOwner(client,user.id);
  const [proofs, portfolio, liquidity] = owner ? await Promise.all([
    client.from('asset_evidence_latest').select('id,account_scope,account_id,contract_key,view_key,storage_path,captured_at,source_as_of,last_attempt_at,last_attempt_status').eq('owner_id',user.id).order('account_id').limit(500),
    client.from('portfolio_accounts').select('id,name').eq('active',true),
    client.from('liquidity_accounts').select('id,name').eq('active',true),
  ]) : [{data:null,error:null},{data:null},{data:null}];
  const {data,error} = proofs;
  const names = new Map<string,string>();
  for (const row of portfolio.data || []) names.set(`portfolio|${row.id}`,row.name);
  for (const row of liquidity.data || []) names.set(`liquidity|${row.id}`,row.name);
  const unavailable = owner === null || Boolean(error);
  return <Shell active="/portfolio" email={user.email || null}>
    <h1>最新の資産証拠</h1>
    <p className="sub">契約・基準日を確認した正常画像を表示します。画像の月別履歴は作りません。</p>
    <p><a href="/portfolio">← 数値と保存状況に戻る</a></p>
    {unavailable ? <div className="card" role="alert">証拠の記録を取得できません。画像の保存・更新は未確認です。</div>
      : !owner ? <div className="card">このアカウントには証拠の閲覧権限が設定されていません。</div>
      : !data?.length ? <div className="card"><strong>正常画像はまだ登録されていません。</strong><p>画像がなくても数値履歴はDBに残ります。必要な対象を音声・チャットで依頼してください。</p></div>
      : data.map(row => <article className="card" key={row.id}>
        <header><span className="lvl">{row.account_scope === 'liquidity' ? '銀行等' : '資産'}</span><strong>{names.get(`${row.account_scope}|${row.account_id}`) || row.account_id}</strong></header>
        <p>{evidenceState(row)}</p>
        <dl><dt>契約 / 画面</dt><dd>{row.contract_key} / {row.view_key}</dd><dt>正常画像の撮影日時</dt><dd>{time(row.captured_at)}</dd>
          <dt>元データ基準日</dt><dd>{row.source_as_of || 'なし'}</dd><dt>今回の更新試行</dt><dd>{time(row.last_attempt_at)}</dd></dl>
        {row.storage_path && UUID.test(row.id) ? <Asset618Preview id={row.id}/> : <p>前回の正常画像はありません。</p>}
      </article>)}
    <p className="meta">公開URLの発行・外部送信は行いません。未取得分の取り直しは音声・チャットで依頼してください。</p>
  </Shell>;
}
