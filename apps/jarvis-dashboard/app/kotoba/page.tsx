import Link from "next/link";
import Shell from "@/components/Shell";
import { KotobaCardActions, KotobaShelfNote } from "@/components/KotobaCardActions";
import { createServiceClient } from "@/lib/supabase/admin";
import {
  KIND_LABEL,
  STATUS_LABEL,
  filterByStatus,
  groupByShelf,
  isShelf,
  whoWhere,
  type KotobaCard,
  type KotobaNote,
} from "@/lib/kotoba";

export const dynamic = "force-dynamic";
export const metadata = { title: "ことばの棚｜Jarvis" };

const CARD_COLS =
  "id,body,speaker,speaker_guess,where_label,occurred_on,at_label,source,source_ref,background,kind,shelves,is_summary,status,created_at";

const VIEWS: { id: string; label: string }[] = [
  { id: "", label: "いらない以外" },
  { id: "candidate", label: "未判断" },
  { id: "kept", label: "残す" },
  { id: "hesitated", label: "迷う" },
  { id: "all", label: "すべて" },
];

async function load() {
  const sb = createServiceClient();
  if (!sb) return null;
  const [cards, notes] = await Promise.all([
    sb.from("kotoba_cards").select(CARD_COLS).order("occurred_on", { ascending: false, nullsFirst: false }).limit(1000),
    sb.from("kotoba_notes").select("id,card_id,shelf,kind,body,created_at").order("created_at", { ascending: false }).limit(1000),
  ]);
  return {
    error: cards.error?.message || notes.error?.message || null,
    cards: (cards.data || []) as KotobaCard[],
    notes: (notes.data || []) as KotobaNote[],
  };
}

function md(iso: string): string {
  const d = new Date(Date.parse(iso) + 9 * 3600_000);
  return `${d.getUTCMonth() + 1}/${d.getUTCDate()}`;
}

function viewHref(view: string, shelf?: string): string {
  const q = new URLSearchParams();
  if (view) q.set("view", view);
  if (shelf) q.set("shelf", shelf);
  const s = q.toString();
  return s ? `/kotoba?${s}` : "/kotoba";
}

export default async function KotobaPage({
  searchParams,
}: {
  searchParams: Promise<{ view?: string; shelf?: string }>;
}) {
  const sp = await searchParams;
  const view = sp.view || "";
  const d = await load();
  if (!d) {
    return (
      <Shell active="/kotoba">
        <h1>ことばの棚</h1>
        <p className="empty">Supabase が未設定のため読めません。</p>
      </Shell>
    );
  }

  const shown = filterByStatus(d.cards, view || undefined);
  const groups = groupByShelf(shown);
  const focus = sp.shelf && groups.some((g) => g.shelf === sp.shelf) ? sp.shelf : null;
  const visible = focus ? groups.filter((g) => g.shelf === focus) : groups;
  const notesByCard = new Map<string, KotobaNote[]>();
  const notesByShelf = new Map<string, KotobaNote[]>();
  for (const n of d.notes) {
    if (n.card_id) {
      if (!notesByCard.has(n.card_id)) notesByCard.set(n.card_id, []);
      notesByCard.get(n.card_id)!.push(n);
    } else if (n.shelf) {
      if (!notesByShelf.has(n.shelf)) notesByShelf.set(n.shelf, []);
      notesByShelf.get(n.shelf)!.push(n);
    }
  }
  const total = { candidate: 0, kept: 0, dropped: 0, hesitated: 0 } as Record<string, number>;
  for (const c of d.cards) total[c.status] = (total[c.status] || 0) + 1;

  return (
    <Shell active="/kotoba">
      <h1>ことばの棚</h1>
      <p className="sub">
        録音・議事録・Journal から拾った「あとで効く言葉」です。タスクにはしません。残す／いらない／迷うを押すと判断ログにも残り、
        どんな言葉を残すかを覚えて拾い方が良くなります。迷うは「いらない」に数えません。
      </p>
      {d.error ? <p className="empty">読み込みに失敗: {d.error}</p> : null}

      <div className="stats">
        <div className="stat">
          未判断 <strong>{total.candidate}</strong>
        </div>
        <div className="stat">
          残す <strong>{total.kept}</strong>
        </div>
        <div className="stat">
          迷う <strong>{total.hesitated}</strong>
        </div>
        <div className="stat">
          いらない <strong>{total.dropped}</strong>
        </div>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, margin: "14px 0 6px" }}>
        {VIEWS.map((v) => (
          <Link key={v.id || "default"} href={viewHref(v.id, focus || undefined)} className={v.id === view ? "btn primary" : "btn ghost"}>
            {v.label}
          </Link>
        ))}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, margin: "0 0 18px" }}>
        <Link href={viewHref(view)} className={focus ? "btn ghost" : "btn primary"}>
          すべての棚
        </Link>
        {groups.map((g) => (
          <Link key={g.shelf} href={viewHref(view, g.shelf)} className={focus === g.shelf ? "btn primary" : "btn ghost"}>
            {g.shelf}（{g.cards.length}）
          </Link>
        ))}
      </div>

      {d.cards.length === 0 ? (
        <p className="empty">
          まだカードがありません。試し拾いのカードは、表を作ったあとに初期データの SQL を貼ると入ります（PR の説明を参照）。
        </p>
      ) : null}
      {d.cards.length > 0 && visible.length === 0 ? <p className="empty">この絞り込みに当てはまるカードはありません。</p> : null}

      {visible.map((g) => {
        const shelfNotes = notesByShelf.get(g.shelf) || [];
        return (
          <section key={g.shelf} style={{ marginBottom: 28 }}>
            <h2 style={{ marginBottom: 4 }}>
              {g.shelf}
              <small className="sub" style={{ marginLeft: 8, fontWeight: 400 }}>
                {g.cards.length}枚（残す {g.counts.kept}・未判断 {g.counts.candidate}・迷う {g.counts.hesitated}）
              </small>
            </h2>
            {g.cards.map((c) => {
              const cn = notesByCard.get(c.id) || [];
              const ref = c.source_ref || {};
              const url = typeof ref.url === "string" ? ref.url : null;
              return (
                <article key={`${g.shelf}:${c.id}`} className="card" style={{ marginBottom: 10 }}>
                  <header style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
                    <span className="lvl">{KIND_LABEL[c.kind] || c.kind}</span>
                    {c.status !== "candidate" ? <span className="sub">{STATUS_LABEL[c.status]}</span> : null}
                  </header>
                  <blockquote style={{ margin: "8px 0", fontSize: 16, lineHeight: 1.7 }}>
                    「{c.body}」{c.is_summary ? <span className="sub">（要約）</span> : null}
                  </blockquote>
                  <p className="sub" style={{ margin: "2px 0" }}>
                    {whoWhere(c)}
                    {url ? (
                      <>
                        {" "}
                        <a href={url} target="_blank" rel="noreferrer">
                          元の記録
                        </a>
                      </>
                    ) : null}
                  </p>
                  {c.background ? (
                    <p className="sub" style={{ margin: "2px 0" }}>
                      背景: {c.background}
                    </p>
                  ) : null}
                  {c.shelves.length > 1 ? (
                    <p className="sub" style={{ margin: "2px 0" }}>
                      ほかの棚: {c.shelves.filter((s) => s !== g.shelf).join("・")}
                    </p>
                  ) : null}
                  {cn.length ? (
                    <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                      {cn.slice(0, 5).map((n) => (
                        <li key={n.id} className="sub">
                          {md(n.created_at)} {n.body}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  <KotobaCardActions cardId={c.id} status={c.status} />
                </article>
              );
            })}
            {isShelf(g.shelf) ? (
              <details style={{ marginTop: 8 }}>
                <summary className="sub">この棚のまとめ（{shelfNotes.length} 件）</summary>
                {shelfNotes.length ? (
                  <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                    {shelfNotes.slice(0, 10).map((n) => (
                      <li key={n.id} className="sub" style={{ whiteSpace: "pre-wrap" }}>
                        {md(n.created_at)} {n.body}
                      </li>
                    ))}
                  </ul>
                ) : null}
                <KotobaShelfNote shelf={g.shelf} />
              </details>
            ) : null}
          </section>
        );
      })}
    </Shell>
  );
}
