import Link from "next/link";
import Shell from "@/components/Shell";
import StatusToggle from "@/components/StatusToggle";
import TriageStatusActions from "@/components/TriageStatusActions";
import { LEVEL_LABEL, HomeLevel } from "@/lib/homeLevels";
import { CLOSED_STATUSES, STATUS_LABEL, type TriageStatus } from "@/lib/triageStatus";
import { createClient } from "@/lib/supabase/server";

const LANE_LABEL: Record<string, string> = {
  partner: "パートナー",
  openchat: "オプチャ",
  general: "それ以外",
  kamiooya: "神大家運営",
  properties: "所有物件",
  kodate: "戸建て",
  "ai-raimo": "AI・Raimo",
};

function fmtAt(v: string | null | undefined) {
  if (!v) return "";
  const m = String(v).match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  if (m) return `${m[1]}/${m[2]}/${m[3]} ${m[4]}:${m[5]}`;
  return String(v).slice(0, 16);
}

export default async function ArchivePage() {
  const supabase = await createClient();

  const [{ data: watches }, { data: cards }, { data: closedMails }] =
    await Promise.all([
      supabase
        .from("watch_status")
        .select("*")
        .eq("status", "archived")
        .order("archived_at", { ascending: false })
        .limit(80),
      supabase
        .from("cards")
        .select("*")
        .eq("status", "archived")
        .order("archived_at", { ascending: false })
        .limit(80),
      supabase
        .from("triage_items")
        .select(
          "id,lane,partner,folder,subject,status,summary,updated_at,from_email"
        )
        .in("status", CLOSED_STATUSES)
        .neq("kind", "activity")
        .order("updated_at", { ascending: false })
        .limit(60),
    ]);

  const watchList = watches || [];
  const cardList = cards || [];
  const mailList = closedMails || [];

  return (
    <Shell active="/archive">
      <h1>アーカイブ</h1>
      <p className="sub">
        隠した状況ウォッチ・レーンカードの復元、およびメールのスキップ／後で／送信済みを確認できます。
      </p>

      <div className="stats">
        <div className="stat">
          ウォッチ <strong>{watchList.length}</strong>
        </div>
        <div className="stat">
          カード <strong>{cardList.length}</strong>
        </div>
        <div className="stat">
          メール処理済 <strong>{mailList.length}</strong>
        </div>
      </div>

      <section className="archive-group">
        <h2>
          状況ウォッチ
          <span className="meta">{watchList.length}件</span>
        </h2>
        {watchList.length === 0 ? (
          <p className="empty">アーカイブなし</p>
        ) : (
          watchList.map((it) => {
            const level = (
              ["attention", "warn", "info", "ok"].includes(it.level)
                ? it.level
                : "info"
            ) as HomeLevel | "ok";
            const label =
              level === "ok" ? "OK" : LEVEL_LABEL[level as HomeLevel] || it.level;
            return (
              <article key={it.id} className="card archived">
                <header>
                  <span className="lvl">{label}</span>
                  <strong>{it.title}</strong>
                  <span className="meta">
                    {fmtAt(it.archived_at || it.updated_at)}
                  </span>
                  <StatusToggle
                    table="watch_status"
                    id={it.id}
                    status={it.status}
                    path="/archive"
                  />
                </header>
                <p className="sum">{it.summary}</p>
                {it.source ? <p className="meta">{it.source}</p> : null}
              </article>
            );
          })
        )}
      </section>

      <section className="archive-group">
        <h2>
          レーンカード
          <span className="meta">{cardList.length}件</span>
        </h2>
        {cardList.length === 0 ? (
          <p className="empty">アーカイブなし</p>
        ) : (
          cardList.map((c) => (
            <article key={c.id} className="card archived">
              <header>
                <span className="lvl">
                  {LANE_LABEL[c.lane] || c.lane} · {c.kind}
                </span>
                <strong>{c.title}</strong>
                <span className="meta">
                  {fmtAt(c.archived_at || c.updated_at)}
                </span>
                <StatusToggle
                  table="cards"
                  id={c.id}
                  status={c.status}
                  path="/archive"
                />
              </header>
              <p className="sum">{c.summary}</p>
            </article>
          ))
        )}
      </section>

      <section className="archive-group">
        <h2>
          メール（処理済み）
          <span className="meta">直近 {mailList.length}件</span>
        </h2>
        <p className="sub" style={{ marginTop: -8 }}>
          スキップ・後で・送信済み。「未読に戻す」でパートナー等の未読に戻せます。
        </p>
        {mailList.length === 0 ? (
          <p className="empty">なし</p>
        ) : (
          mailList.map((it) => {
            const who = it.partner || it.from_email || "—";
            const laneHref =
              it.lane === "partner"
                ? "/partner"
                : it.lane === "openchat"
                  ? "/openchat"
                  : "/general";
            return (
              <article key={it.id} className="card archived">
                <header>
                  <span className={`status-badge status-${it.status}`}>
                    {STATUS_LABEL[it.status as TriageStatus] || it.status}
                  </span>
                  <strong>{who}</strong>
                  <span className="meta">
                    {LANE_LABEL[it.lane] || it.lane}
                    {it.updated_at ? ` · ${fmtAt(it.updated_at)}` : ""}
                  </span>
                  <TriageStatusActions
                    id={it.id}
                    status={it.status}
                    path="/archive"
                    mode="closed"
                  />
                </header>
                <p className="sum">{it.subject || "（件名なし）"}</p>
                <p className="meta">
                  <Link href={`/mail/${encodeURIComponent(it.id)}`}>詳細</Link>
                  {" · "}
                  <Link href={laneHref}>レーンへ</Link>
                </p>
              </article>
            );
          })
        )}
      </section>
    </Shell>
  );
}
