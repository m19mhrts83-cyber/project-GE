import {createClient} from '@/lib/supabase/server';
import {loadNumericStatus} from '@/lib/asset618Server';
import Asset618Check from './Asset618Check';
export default async function Asset618Status({userId}: {userId: string | null}) {
  if (!userId) return null;
  const status = await loadNumericStatus(await createClient(),userId);
  if (status.state === 'not_owner') return null;
  return <section className="card" aria-label="618 資産記録の確認">
    <header><span className="lvl">618 資産記録</span><strong>保存・表示・最新証拠</strong></header>
    {status.state === 'ready' && <p className="meta">更新処理の開始：{status.context.started_at && Number.isFinite(Date.parse(status.context.started_at)) ? new Date(status.context.started_at).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'}) : '日時未確認'}</p>}
    {status.state === 'ready' ? <Asset618Check runId={status.context.run_id} rows={status.rows} unresolved={status.unresolved}
      checkedAt={status.receipt?.numeric_digest === status.numeric_digest && status.rows.every(x => x.matches) ? status.receipt.checked_at : null}/>
      : <p className="meta">{status.state === 'no_run' ? '照合できる実行記録はまだありません。' : '確認用の記録を取得できません。保存・画面反映は未確認です。'} <a href="/portfolio/evidence">最新証拠を見る →</a></p>}
    <p className="meta">数値保存・画像更新・画面照合は別々に確認します。取り直しは音声・チャットで依頼してください。</p>
  </section>;
}
