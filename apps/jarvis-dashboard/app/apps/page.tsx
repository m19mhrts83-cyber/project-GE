import Shell from "@/components/Shell";
import catalog from "@/data/apps_prompts_catalog.json";

type CatalogItem = {
  id: string;
  kind: "app" | "prompt" | "notebook" | string;
  title: string;
  url: string;
  note?: string;
  tags?: string[];
  raimo_miniapp_url?: string;
  raimo_edit_url?: string;
  admin_url?: string;
  internal?: boolean;
};

const KIND_LABEL: Record<string, string> = {
  app: "アプリ",
  prompt: "プロンプト",
  notebook: "NotebookLM",
};

const KIND_ORDER = ["app", "prompt", "notebook"];

function ItemCard({ item }: { item: CatalogItem }) {
  const external = item.url.startsWith("http");
  const openHref = item.raimo_miniapp_url || item.url;
  const openExternal = openHref.startsWith("http");

  return (
    <article className="card">
      <header>
        <span className="lvl">{KIND_LABEL[item.kind] || item.kind}</span>
        <strong>{item.title}</strong>
      </header>
      {item.note ? <p className="sum">{item.note}</p> : null}
      {item.tags?.length ? (
        <p className="meta">{item.tags.join(" · ")}</p>
      ) : null}
      <p className="meta" style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 10 }}>
        <a
          className="btn"
          href={openHref}
          {...(openExternal
            ? { target: "_blank", rel: "noopener noreferrer" }
            : {})}
        >
          {item.raimo_miniapp_url ? "マイミニアプリで開く" : "開く"}
          {openExternal ? " ↗" : ""}
        </a>
        {item.raimo_miniapp_url && item.url !== item.raimo_miniapp_url ? (
          <a href={item.url} target="_blank" rel="noopener noreferrer">
            Pages直リンク ↗
          </a>
        ) : null}
        {item.raimo_edit_url ? (
          <a href={item.raimo_edit_url} target="_blank" rel="noopener noreferrer">
            Raimo編集 ↗
          </a>
        ) : null}
        {item.admin_url ? (
          <a href={item.admin_url} target="_blank" rel="noopener noreferrer">
            管理画面 ↗
          </a>
        ) : null}
        {!item.raimo_miniapp_url && !item.admin_url && item.kind === "app" && external ? (
          <span className="meta">※ マイミニアプリ未登録（Pages直）</span>
        ) : null}
      </p>
    </article>
  );
}

export default function AppsCatalogPage() {
  const items = (catalog.items as CatalogItem[]).slice();
  const groups = KIND_ORDER.map((kind) => ({
    kind,
    label: KIND_LABEL[kind] || kind,
    list: items.filter((i) => i.kind === kind),
  })).filter((g) => g.list.length > 0);

  return (
    <Shell active="/apps">
      <h1>アプリ・プロンプト集</h1>
      <p className="sub">
        自分で作ったアプリ・MyPrompt・NotebookLM ノートの入口一覧です。正本は{" "}
        <code>config/apps_prompts_catalog.yaml</code>（表示用 JSON と同期）。
      </p>
      <p className="meta" style={{ marginBottom: 20 }}>
        更新: {catalog.updated} · {items.length} 件
      </p>

      {groups.map((g) => (
        <section key={g.kind} style={{ marginBottom: 28 }}>
          <h2 style={{ fontSize: 18, margin: "0 0 12px" }}>{g.label}</h2>
          <div style={{ display: "grid", gap: 12 }}>
            {g.list.map((item) => (
              <ItemCard key={item.id} item={item} />
            ))}
          </div>
        </section>
      ))}
    </Shell>
  );
}
