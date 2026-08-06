import Link from "next/link";

export function BandSkeleton({ label }: { label: string }) {
  return (
    <div className="home-band home-band-skeleton" aria-busy="true" aria-label={`${label}を読込中`}>
      <div className="home-band-head">
        <h2 className="home-band-title">{label}</h2>
        <p className="home-band-sub">読込中…</p>
      </div>
      <div className="skel-grid">
        <div className="skel-card" />
        <div className="skel-card" />
        <div className="skel-card" />
      </div>
    </div>
  );
}

export function PageSkeleton({ title }: { title?: string }) {
  return (
    <div className="page-skel" aria-busy="true">
      {title ? <h1>{title}</h1> : <div className="skel-line skel-title" />}
      <div className="skel-line" />
      <div className="skel-grid">
        <div className="skel-card" />
        <div className="skel-card" />
      </div>
    </div>
  );
}

export function TodayQueueSkeleton() {
  return (
    <div className="today-queue is-loading" aria-busy="true">
      <div className="skel-line skel-title" style={{ maxWidth: 180 }} />
      <div className="skel-line" style={{ maxWidth: 320 }} />
    </div>
  );
}

/** loading.tsx 用の簡易シェル（サイドバー外形だけ） */
export function RouteLoadingFallback({ title }: { title: string }) {
  return (
    <div className="layout">
      <aside className="sidebar" aria-hidden>
        <div className="side-brand">Jarvis</div>
        <Link href="/" className="side-link side-link-home">
          ホーム
        </Link>
      </aside>
      <main>
        <PageSkeleton title={title} />
      </main>
    </div>
  );
}
