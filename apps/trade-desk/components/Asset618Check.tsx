'use client';
import {useRef, useState} from 'react';
import type {DisplayRow} from '@/lib/asset618Server';
import type {NumericValue} from '@/lib/asset618Contract';
import styles from './Asset618.module.css';
export default function Asset618Check({runId, rows, unresolved, checkedAt}: {runId: string; rows: DisplayRow[]; unresolved: number; checkedAt: string | null}) {
  const table = useRef<HTMLDivElement>(null);
  const [busy,setBusy] = useState(false);
  const [message,setMessage] = useState(checkedAt ? `この実行の保存確認欄を照合済み：${new Date(checkedAt).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'})}` : '保存確認欄の照合は未確認です。');
  async function check() {
    setBusy(true);
    try {
      // Read the rendered cells, not only the original props. A changed cell must fail comparison.
      const shown: NumericValue[] = Array.from(table.current?.querySelectorAll<HTMLElement>('[data-asset-row]') || []).filter(row => row.dataset.matches === 'true').map(row => ({
        table: row.dataset.table as NumericValue['table'], account_id: row.dataset.account!,
        as_of: row.querySelector('[data-field="asof"]')?.textContent?.trim() || '',
        value: (row.querySelector('[data-field="value"]')?.textContent || '').replace(/[,円\s]/g,''),
        source: row.dataset.source || '',
      }));
      const response = await fetch('/api/portfolio/verification',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({run_id:runId,rows:shown})});
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || '照合に失敗しました');
      setMessage(`保存確認欄の照合：${body.matched}件一致・未確認${body.unresolved}件。結果を記録しました。`);
    } catch(error) { setMessage(error instanceof Error ? error.message : '照合に失敗しました'); }
    finally { setBusy(false); }
  }
  return <>
    <p className={styles.note}>DB読戻し確認済み {rows.filter(x => x.matches).length}件 / 未取得・未確認 {unresolved}件</p>
    <details><summary>今回の記録を確認する</summary>
      <div ref={table} className={styles.rows}>
        {rows.map(row => <div className={styles.row} key={`${row.table}:${row.account_id}`} data-asset-row data-table={row.table} data-account={row.account_id} data-source={row.source} data-matches={String(row.matches)}>
          <strong>{row.label}</strong>
          <span className={styles.value}><span data-field="value">{row.value.split('.').map((part,index) => index ? part : part.replace(/\B(?=(\d{3})+(?!\d))/g,',')).join('.')}</span> 円</span>
          <span>記録日 <span data-field="asof">{row.as_of}</span></span>
          <span>{row.source_as_of ? `元データ基準日 ${row.source_as_of}` : '元データ基準日：未確認'}</span>
          <span>{row.matches ? '保存結果と一致' : '保存結果との差異あり・要確認'}</span>
        </div>)}
        {!rows.length && <p>今回のDB読戻し確認済みデータはありません。</p>}
      </div>
    </details>
    <div className={styles.actions}>
      <button type="button" onClick={check} disabled={busy || !rows.length || rows.some(x => !x.matches)}>{busy ? '照合中…' : '表示を照合して記録'}</button>
      <a href="/portfolio/evidence">最新証拠を見る →</a>
    </div>
    <p className={styles.note} role="status" aria-live="polite">{message}</p>
  </>;
}
