import Shell from "@/components/Shell";
import catalog from "@/data/materials_catalog.json";

type Lane = {
  id: string;
  title: string;
  hub_url: string;
  note?: string;
};

type Item = {
  id: string;
  lane: string;
  title: string;
  url: string;
  note?: string;
  filename?: string;
};

const LANE_ORDER = ["self", "dx", "kamiooya"];

export default function MaterialsPage() {
  const lanes = (catalog.lanes as Lane[]).slice().sort((a, b) => {
    const ia = LANE_ORDER.indexOf(a.id);
    const ib = LANE_ORDER.indexOf(b.id);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });
  const items = catalog.items as Item[];

  return (
    <Shell active="/materials">
      <h1>資料</h1>
      <p className="sub">
        自分用・DX互助会・神大家運営の入口です。NotebookLM で確認 → Downloads
        保存 →{" "}
        <code>jarvis_materials_ingest_downloads.py</code> → git push で Pages
        反映。
      </p>

      <div className="watch-grid" style={{ marginBottom: 28 }}>
        {lanes.map((lane) => (
          <a
            key={lane.id}
            href={lane.hub_url}
            target="_blank"
            rel="noopener noreferrer"
            className="card watch-card"
          >
            <header>
              <span className="lvl">ハブ</span>
              <strong>{lane.title}</strong>
            </header>
            {lane.note ? <p className="sum">{lane.note}</p> : null}
            <p className="meta">GitHub Pages で開く ↗</p>
          </a>
        ))}
      </div>

      {lanes.map((lane) => {
        const list = items.filter((i) => i.lane === lane.id);
        if (!list.length) return null;
        return (
          <section key={lane.id} className="home-section">
            <div className="home-section-head">
              <h2 style={{ fontSize: "1.08rem", margin: 0 }}>{lane.title}</h2>
              <a
                href={lane.hub_url}
                className="home-more"
                target="_blank"
                rel="noopener noreferrer"
              >
                ハブ ↗
              </a>
            </div>
            <ul className="mail-skim">
              {list.map((it) => (
                <li key={it.id}>
                  <a
                    href={it.url}
                    className="mail-row"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <span className="mail-row-main">
                      <span className="mail-subject">{it.title}</span>
                      {it.note ? (
                        <span className="mail-preview">{it.note}</span>
                      ) : null}
                    </span>
                    <span className="mail-chevron" aria-hidden>
                      ↗
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          </section>
        );
      })}

      <p className="meta" style={{ marginTop: 24 }}>
        関連: <a href="/notebooklm">NotebookLM</a>
        {" · "}
        <a href="/apps">アプリ・プロンプト集</a>
      </p>
    </Shell>
  );
}
