import Link from "next/link";

export default function HubPage() {
  return (
    <main>
      <nav className="nav">
        <strong>ループウェア</strong>
      </nav>
      <h1>社員ループウェア</h1>
      <p className="sub">
        判断は Slack またはここ（iPhone は Chrome）。ログは Supabase。改善はツール外のプロンプト／プログラムへ。
      </p>
      <div className="card-grid">
        <Link className="card" href="/312">
          <h3>312 入口・何を拾うか</h3>
          <p className="meta">
            重複・扱いを S05 で決める。追記／別作成／登録しない。
          </p>
        </Link>
        <Link className="card" href="/313">
          <h3>313 出口・片付ける</h3>
          <p className="meta">
            済んだ／いつ・優先／やめる。外作業済みの消し込み。
          </p>
        </Link>
      </div>
      <p className="meta" style={{ marginTop: 24 }}>
        Jarvisダッシュからは外部リンクのみ。購入比較はダッシュに残置。
      </p>
    </main>
  );
}
