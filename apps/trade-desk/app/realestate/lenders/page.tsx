/** 融資アプローチ先（③-D 拡張） */

import Shell from "@/components/Shell";
import RealEstateLaneNav from "@/components/RealEstateLaneNav";
import { createClient } from "@/lib/supabase/server";
import Link from "next/link";

export const dynamic = "force-dynamic";

type Lender = {
  id: string;
  name: string;
  display_name: string | null;
  category: string;
  approach: string;
  case_report: boolean;
  matsuno_notes: string | null;
};

type Intel = {
  id: string;
  lender_id: string;
  summary: string;
  source_kind: string;
  source_ref: string | null;
  specialty: string | null;
  income_requirement: string | null;
};

const APPROACH_LABEL: Record<string, string> = {
  yes: "アプローチ候補",
  maybe: "検討（△）",
  deferred: "後回し",
  watch: "事例ウォッチ",
  no: "対象外",
};

export default async function LendersPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: lenders } = await supabase
    .from("kurashift_lenders")
    .select(
      "id,name,display_name,category,approach,case_report,matsuno_notes",
    )
    .eq("active", true)
    .order("approach")
    .order("category")
    .order("name");

  const { data: intel } = await supabase
    .from("kurashift_lender_intel")
    .select(
      "id,lender_id,summary,source_kind,source_ref,specialty,income_requirement",
    )
    .order("updated_at", { ascending: false })
    .limit(400);

  const byLender = new Map<string, Intel[]>();
  for (const row of (intel || []) as Intel[]) {
    const list = byLender.get(row.lender_id) || [];
    list.push(row);
    byLender.set(row.lender_id, list);
  }

  const rows = (lenders || []) as Lender[];
  const approachYes = rows.filter((r) => r.approach === "yes").length;

  return (
    <Shell active="/realestate" email={user?.email ?? null}>
      <RealEstateLaneNav active="d" />
      <p className="page-kicker">③-D · 融資</p>
      <h1>銀行アプローチ先・融資検討材料</h1>
      <p className="sub">
        Excel「★金融機関一覧」のアプローチ先を正本シード。神大家セミナー構造＋Q&A／フォルダから
        銀行別メモを投影。{" · "}
        <Link href="/realestate/finance-pack">融資提出パック →</Link>
      </p>

      <div className="card" style={{ marginBottom: "1rem" }}>
        <p style={{ margin: 0 }}>
          登録 <strong>{rows.length}</strong> 行 · アプローチ候補{" "}
          <strong>{approachYes}</strong>
          {rows.length === 0 ? (
            <>
              {" "}
              — まだ空です。Mac で{" "}
              <code>jarvis_kurashift_lenders_sync.py --apply --with-kamiooya</code>
            </>
          ) : null}
        </p>
      </div>

      <div style={{ display: "grid", gap: "0.75rem" }}>
        {rows.map((L) => {
          const notes = byLender.get(L.id) || [];
          const label = L.display_name || L.name;
          return (
            <article key={L.id} className="card">
              <header
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: "0.5rem",
                  alignItems: "baseline",
                }}
              >
                <strong>{label}</strong>
                <span className="muted">{L.category}</span>
                <span>{APPROACH_LABEL[L.approach] || L.approach}</span>
                {L.case_report ? <span>事例報告あり</span> : null}
              </header>
              {L.matsuno_notes ? (
                <p style={{ marginTop: "0.5rem" }}>{L.matsuno_notes}</p>
              ) : null}
              {notes.length > 0 ? (
                <ul style={{ marginTop: "0.5rem", paddingLeft: "1.2rem" }}>
                  {notes.slice(0, 5).map((n) => (
                    <li key={n.id} style={{ marginBottom: "0.35rem" }}>
                      <span className="muted">[{n.source_kind}]</span>{" "}
                      {n.income_requirement
                        ? `年収: ${n.income_requirement} · `
                        : ""}
                      {n.specialty ? `得意: ${n.specialty} · ` : ""}
                      {n.summary}
                      {n.source_ref ? (
                        <span className="muted"> · {n.source_ref}</span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted" style={{ marginTop: "0.5rem" }}>
                  詳細メモ未取得
                </p>
              )}
            </article>
          );
        })}
      </div>
    </Shell>
  );
}
