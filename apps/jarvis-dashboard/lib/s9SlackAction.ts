/**
 * S9 管理会社開拓 — Slack の「採用／見送り」ボタン
 *
 * ボタン →（action_id は /api/slack/consult-action／URL は /api/g/s9）→
 * Supabase `kurashift_jobs` に `re_mgmt_vendor_decision` を積む。
 * Mac の kurashift job worker が scripts/jarvis_s9_decision_apply.py を実行して
 * 台帳 YAML（config/kurashift_mgmt_vendor_list.yaml）へ反映する。
 */
import { createHmac, timingSafeEqual } from "crypto";
import { NextResponse } from "next/server";
import { createServiceClient } from "@/lib/supabase/admin";

export type S9Decision = "adopt" | "skip";

export const S9_ACTION_IDS = {
  adopt: "s9_adopt",
  skip: "s9_skip",
} as const;

export const S9_DECISION_LABEL: Record<S9Decision, string> = {
  adopt: "採用",
  skip: "見送り",
};

export const S9_DECISION_ICON: Record<S9Decision, string> = {
  adopt: "✅",
  skip: "🗑️",
};

export const S9_JOB_TYPE = "re_mgmt_vendor_decision";

export type S9Candidate = {
  n: number;
  name: string;
  area?: string;
  pref?: string;
  city?: string;
  lane?: string;
  url?: string;
  cu?: string;
  em?: string;
  tel?: string;
  ch?: string;
  memo?: string;
  src?: string;
  dt?: string;
};

function candidateSecrets(): string[] {
  const raw = [
    process.env.S9_ACTION_TOKEN,
    process.env.PROPERTY_GATE_ACTION_TOKEN,
    process.env.TODOIST_313_ACTION_TOKEN,
    process.env.TODOIST_API_TOKEN,
  ];
  const out: string[] = [];
  const seen = new Set<string>();
  for (const v of raw) {
    const s = (v || "").trim();
    if (s && !seen.has(s)) {
      seen.add(s);
      out.push(s);
    }
  }
  return out;
}

function actionSecret(): string {
  return candidateSecrets()[0] || "";
}

export function b64urlEncode(raw: string): string {
  return Buffer.from(raw, "utf8")
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

export function b64urlDecode(s: string): string | null {
  try {
    let b64 = s.replace(/-/g, "+").replace(/_/g, "/");
    while (b64.length % 4) b64 += "=";
    return Buffer.from(b64, "base64").toString("utf8");
  } catch {
    return null;
  }
}

export function encodeS9Candidate(c: S9Candidate): string {
  const compact = {
    n: Number(c.n) || 0,
    name: String(c.name || "").slice(0, 120),
    area: String(c.area || "").slice(0, 40),
    pref: String(c.pref || "愛知県").slice(0, 20),
    city: String(c.city || "").slice(0, 20),
    lane: String(c.lane || "midori_caramel").slice(0, 40),
    url: String(c.url || "").slice(0, 300),
    cu: String(c.cu || "").slice(0, 300),
    em: String(c.em || "").slice(0, 120),
    tel: String(c.tel || "").slice(0, 30),
    ch: String(c.ch || "").slice(0, 20),
    memo: String(c.memo || "").slice(0, 200),
    src: String(c.src || "").slice(0, 80),
    dt: String(c.dt || "").slice(0, 10),
  };
  return b64urlEncode(JSON.stringify(compact));
}

export function decodeS9Candidate(b64: string): S9Candidate | null {
  const raw = b64urlDecode(b64);
  if (!raw) return null;
  try {
    const j = JSON.parse(raw) as S9Candidate;
    if (!j || typeof j !== "object") return null;
    const name = String(j.name || "").trim();
    if (name.length < 2) return null;
    return {
      n: Number(j.n) || 0,
      name: name.slice(0, 120),
      area: String(j.area || "").slice(0, 40),
      pref: String(j.pref || "愛知県").slice(0, 20),
      city: String(j.city || "").slice(0, 20),
      lane: String(j.lane || "midori_caramel").slice(0, 40),
      url: String(j.url || "").slice(0, 300),
      cu: String(j.cu || "").slice(0, 300),
      em: String(j.em || "").slice(0, 120),
      tel: String(j.tel || "").slice(0, 30),
      ch: String(j.ch || "").slice(0, 20),
      memo: String(j.memo || "").slice(0, 200),
      src: String(j.src || "").slice(0, 80),
      dt: String(j.dt || "").slice(0, 10),
    };
  } catch {
    return null;
  }
}

function s9SigWithSecret(
  secret: string,
  decision: S9Decision,
  payloadB64: string,
): string {
  return createHmac("sha256", secret)
    .update(`s9:${decision}:${payloadB64}`, "utf8")
    .digest("hex")
    .slice(0, 10);
}

export function parseS9Action(
  raw: string | null | undefined,
): S9Decision | null {
  const a = (raw || "").trim().toLowerCase();
  if (a === "adopt" || a === "採用" || a === "approve") return "adopt";
  if (a === "skip" || a === "見送り" || a === "dismiss") return "skip";
  return null;
}

export function s9Sig(decision: S9Decision, payloadB64: string): string {
  const secret = actionSecret();
  if (!secret) return "";
  return s9SigWithSecret(secret, decision, payloadB64);
}

export function s9SigOk(
  decision: S9Decision,
  payloadB64: string,
  sig: string | null | undefined,
): boolean {
  const got = (sig || "").trim().toLowerCase();
  if (!got || got.length !== 10) return false;
  const secrets = candidateSecrets();
  if (!secrets.length) return false;
  for (const secret of secrets) {
    const expected = s9SigWithSecret(secret, decision, payloadB64);
    if (got.length !== expected.length) continue;
    try {
      if (timingSafeEqual(Buffer.from(got), Buffer.from(expected))) {
        return true;
      }
    } catch {
      /* next */
    }
  }
  return false;
}

/** value: s9:adopt|skip:{b64}:{sig} */
export function parseS9ButtonValue(value: string): {
  decision: S9Decision;
  payloadB64: string;
  candidate: S9Candidate;
  sig: string;
} | null {
  const s = String(value || "").trim();
  const m = s.match(/^s9:(adopt|skip):([A-Za-z0-9_-]+):([a-f0-9]{10})$/i);
  if (!m) return null;
  const decision = m[1].toLowerCase() as S9Decision;
  const payloadB64 = m[2];
  const sig = m[3].toLowerCase();
  const candidate = decodeS9Candidate(payloadB64);
  if (!candidate) return null;
  if (!s9SigOk(decision, payloadB64, sig)) return null;
  return { decision, payloadB64, candidate, sig };
}

export function s9ActionUrl(
  decision: S9Decision,
  candidate: S9Candidate,
): string {
  const base = (
    process.env.JARVIS_DASHBOARD_URL ||
    process.env.NEXT_PUBLIC_SITE_URL ||
    "https://jarvis-dashboard-amber.vercel.app"
  )
    .trim()
    .replace(/\/$/, "");
  const b64 = encodeS9Candidate(candidate);
  const sig = s9Sig(decision, b64);
  return `${base}/api/g/s9/${decision}/n${candidate.n || 0}?p=${encodeURIComponent(b64)}&s=${sig}`;
}

export function htmlPage(title: string, body: string, ok: boolean) {
  const color = ok ? "#065f46" : "#991b1b";
  const esc = (x: string) =>
    String(x || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  return new NextResponse(
    `<!doctype html><html lang="ja"><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>${esc(title)}</title>
<body style="font-family:system-ui;padding:1.5rem;max-width:38rem;color:${color}">
<h1 style="font-size:1.25rem">${esc(title)}</h1>
<pre style="white-space:pre-wrap;background:#f3f4f6;padding:1rem;border-radius:8px;color:#111">${esc(body)}</pre>
<p style="color:#6b7280;font-size:0.875rem">このタブは閉じて大丈夫です。Slack に戻ってください。</p>
</body></html>`,
    {
      status: ok ? 200 : 400,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "private, no-store",
      },
    },
  );
}

export function confirmHtml(opts: {
  decision: S9Decision;
  candidate: S9Candidate;
  payloadB64: string;
  sig: string;
}) {
  const { decision, candidate, payloadB64, sig } = opts;
  const label = S9_DECISION_LABEL[decision];
  const icon = S9_DECISION_ICON[decision];
  const esc = (x: string) =>
    String(x || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  const color = decision === "adopt" ? "#047857" : "#b91c1c";
  const body = `<!doctype html><html lang="ja"><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>${esc(label)}: ${esc(candidate.name)}</title>
<body style="font-family:system-ui;padding:1.5rem;max-width:34rem">
<p style="color:#6b7280;font-size:.875rem;margin:0 0 .25rem">S9 管理会社開拓</p>
<h1 style="font-size:1.3rem;margin:.25rem 0 .5rem">${esc(candidate.name)}</h1>
<p style="margin:.25rem 0;color:#374151">${esc(candidate.area || "")}</p>
${
  candidate.url
    ? `<p style="margin:.25rem 0"><a href="${esc(candidate.url)}" style="color:#2563eb">サイトを見る</a></p>`
    : ""
}
<form method="post" style="margin-top:1.5rem">
  <input type="hidden" name="p" value="${esc(payloadB64)}"/>
  <input type="hidden" name="s" value="${esc(sig)}"/>
  <input type="hidden" name="intent" value="confirm"/>
  <button type="submit" style="width:100%;padding:1rem;font-size:1.125rem;border:0;border-radius:12px;background:${color};color:#fff;font-weight:700">
    ${esc(icon)} ${esc(label)}する
  </button>
</form>
<form method="get" style="margin-top:.75rem">
  <input type="hidden" name="cancel" value="1"/>
  <button type="submit" style="width:100%;padding:.875rem;font-size:1rem;border:1px solid #d1d5db;border-radius:12px;background:#fff">
    やめる
  </button>
</form>
<p style="color:#6b7280;font-size:.8rem;margin-top:1.5rem">${esc(label)}後、台帳へ数秒で反映されます。このタブは閉じて大丈夫です。</p>
</body></html>`;
  return new NextResponse(body, {
    status: 200,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "private, no-store",
    },
  });
}

export type S9ApplyResult = { ok: boolean; message: string; jobId?: string };

/** kurashift_jobs へ判断を積む（Mac worker が拾って台帳へ反映）。 */
export async function applyS9Action(opts: {
  decision: S9Decision;
  candidate: S9Candidate;
  source: "slack_button" | "slack_link";
  channelId?: string;
  messageTs?: string;
  userId?: string;
}): Promise<S9ApplyResult> {
  const c = opts.candidate;
  const label = S9_DECISION_LABEL[opts.decision];
  const supabase = createServiceClient();
  if (!supabase) {
    return {
      ok: false,
      message:
        "Supabase が未設定です（JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY）",
    };
  }

  try {
    const { data: recent } = await supabase
      .from("kurashift_jobs")
      .select("id,status,payload,created_at")
      .eq("job_type", S9_JOB_TYPE)
      .order("created_at", { ascending: false })
      .limit(20);
    const dup = (recent || []).find((r) => {
      const p = (r.payload || {}) as Record<string, unknown>;
      return (
        String(p.name || "") === c.name &&
        String(p.decision || "") === opts.decision &&
        ["queued", "running", "succeeded"].includes(String(r.status || ""))
      );
    });
    if (dup) {
      return {
        ok: true,
        message: `${c.name} はすでに「${label}」で受付済みです（job ${String(dup.id).slice(0, 8)}）`,
        jobId: String(dup.id),
      };
    }

    const payload = {
      decision: opts.decision,
      ...c,
      source: opts.source,
      channel: opts.channelId || "",
      message_ts: opts.messageTs || "",
      pressed_by: opts.userId || "",
    };
    const { data, error } = await supabase
      .from("kurashift_jobs")
      .insert({
        job_type: S9_JOB_TYPE,
        title: `[S9] ${label}: ${c.name}`,
        payload,
        status: "queued",
        created_by: "slack:s9",
      })
      .select("id")
      .single();
    if (error) {
      return { ok: false, message: `ジョブ登録に失敗: ${error.message}` };
    }
    return {
      ok: true,
      message:
        `${c.name} を「${label}」で受け付けました。\n` +
        "台帳へは数秒で反映されます（Mac worker）。",
      jobId: String(data?.id || ""),
    };
  } catch (e) {
    return {
      ok: false,
      message: `エラー: ${e instanceof Error ? e.message : String(e)}`,
    };
  }
}
