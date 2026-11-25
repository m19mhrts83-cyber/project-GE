import Shell from "@/components/Shell";
import GrokDecideButtons from "@/components/GrokDecideButtons";
import { createClient } from "@/lib/supabase/server";
import { createServiceClient } from "@/lib/supabase/admin";
import { formatJstYmdHm } from "@/lib/formatJst";
import {
  STATE_LABEL,
  STATE_ORDER,
  buildViews,
  countByState,
  parseSnapshot,
  type GrokState,
  type LedgerRow,
  type PendingJob,
} from "@/lib/grokCandidates";

export const dynamic = "force-dynamic";

const CHANNEL_LABEL: Record<string, string> = { email: "メール", web_form: "フォーム", phone: "電話" };
const TONE: Record<GrokState, string> = {
  decide: "attention",
  queued: "info",
  pending: "warn",
  sent: "ok",
  dup: "info",
  skipped: "info",
  drop: "info",
};

export default async function GrokCandidatesPage() {
  const supabase = await createClient();
  const [{ data: meta }, { data: ledger }] = await Promise.all([
    supabase.from("sync_meta").select("value,updated_at").eq("key", "grok_candidates_snapshot").maybeSingle(),
    supabase
      .from("kurashift_re_mgmt_vendors")
      .select("id,name,status,source,discovered_at,contacted_at,area,channel")
      .limit(2000),
  ]);

  // 受付済みの採用／見送り（Mac worker が台帳へ反映する前）。読めなくても画面は出す。
  let jobs: PendingJob[] = [];
  const sb = createServiceClient();
  if (sb) {
    const { data } = await sb
      .from("kurashift_jobs")
      .select("payload,status")
      .eq("job_type", "re_mgmt_vendor_decision")
      .in("status", ["queued", "running"])
      .limit(50);
    jobs = (data || [])
      .map((r) => r.payload as { name?: string; decision?: string })
      .filter((p) => p?.name && (p.decision === "adopt" || p.decision === "skip"))
      .map((p) => ({ name: String(p.name), decision: p.decision as "adopt" | "skip" }));
  }

  const snap = parseSnapshot(meta?.value);
  const views = buildViews(snap?.items ?? [], (ledger || []) as LedgerRow[], jobs);
  const counts = countByState(views);

  return (
    <Shell active="/grok-candidates">
      <h1>Grok の候補</h1>
      <p className="sub">
        Grok が見つけた管理会社の候補が、台帳でいまどうなっているか。読むだけの画面です（送信はしません）。
        {snap?.generatedAt ? ` 取り込みの最終更新 ${formatJstYmdHm(snap.generatedAt)}` : ""}
      </p>

      <section className="card">
        <p className="meta" style={{ margin: 0 }}>
          {STATE_ORDER.map((s) => `${STATE_LABEL[s]} ${counts[s]}`).join(" ／ ")}
        </p>
      </section>

      {!snap ? (
        <p className="meta">
          取り込み結果の写しはまだありません。台帳の出どころ印（S9 取り込み）から分かる分だけ出しています。
          次の取り込みから、重複や判断待ちも出ます。
        </p>
      ) : null}
      {views.length === 0 ? <p className="meta">いまは候補がありません。</p> : null}

      {STATE_ORDER.map((s) => {
        const list = views.filter((v) => v.state === s);
        if (!list.length) return null;
        return (
          <div key={s}>
            <h2>
              {STATE_LABEL[s]}（{list.length}）
            </h2>
            {list.map((v) => (
              <section key={v.key} className={`card ${s === "decide" ? "level-attention" : ""}`.trim()}>
                <header className="cursor-usage-head">
                  <p className="cursor-usage-plan">{v.name}</p>
                  <span className={`cursor-usage-badge tone-${TONE[s]}`}>{STATE_LABEL[s]}</span>
                </header>
                <p className="meta" style={{ margin: "4px 0" }}>
                  {[v.area, CHANNEL_LABEL[v.channel] || v.channel, v.date].filter(Boolean).join(" · ")}
                </p>
                {v.reason ? <p style={{ margin: "4px 0" }}>{v.reason}</p> : null}
                {v.existingName && v.existingName !== v.name ? (
                  <p className="meta" style={{ margin: "4px 0" }}>台帳の名前: {v.existingName}</p>
                ) : null}
                {v.canDecide ? <GrokDecideButtons name={v.name} /> : null}
              </section>
            ))}
          </div>
        );
      })}

      <p className="meta" style={{ marginTop: 16 }}>
        採用すると、Slack の［採用］と同じ道で台帳に入り（送信待ち）、送信は従来どおり 311 のゲートと本人了承のあとです。
        判断は判断ログ（owner_decisions）に残ります。
      </p>
    </Shell>
  );
}
