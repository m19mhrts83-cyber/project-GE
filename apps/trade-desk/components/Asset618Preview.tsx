'use client';
import {useState} from 'react';
import styles from './Asset618.module.css';
export default function Asset618Preview({id}: {id: string}) {
  const [failed,setFailed] = useState(false);
  return <details><summary>正常画像を開く</summary>{failed ? <p role="alert">画像の取得・整合性確認に失敗しました。証拠の閲覧は未確認です。</p>
    // The authenticated proxy verifies bytes before returning them. Do not use a public or signed URL.
    : <img className={styles.image} src={`/api/portfolio/evidence/${id}`} alt="保存済み資産証拠" loading="lazy" onError={() => setFailed(true)}/>}</details>;
}
