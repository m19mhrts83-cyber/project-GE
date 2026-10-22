/**
 * 312 Todoist起票 — Slack ボタン／署名 URL
 * 提案ペイロード（lane/title 等）を base64url で載せ、HMAC で検証。
 * 署名候補は 313 と同系（PROPERTY_GATE 等）。
 */
import { createHmac, timingSafeEqual } from "crypto";
import { NextResponse } from "next/server";
import { createTodoistTask } from "@/lib/todoistTasks";

export type Todoist312Action = "create" | "dismiss";

export const T312_ACTION_IDS = {
  create: "todoist_312_create",
  dismiss: "todoist_312_dismiss",
} as const;

export type T312Proposal = {
  n: number;
  lane: string;
  title: string;
  summary?: string;
  origin?: string;
  project_url?: string;
  labels?: string[];
};

function candidateSecrets(): string[] {
  const raw = [
    process.env.TODOIST_312_ACTION_TOKEN,
    process.env.TODOIST_313_ACTION_TOKEN,
    process.env.PROPERTY_GATE_ACTION_TOKEN,
    process.env.MAIL_ACTION_TOKEN,
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

export function encodeT312Proposal(p: T312Proposal): string {
  const compact: T312Proposal = {
    n: Number(p.n) || 0,
    lane: String(p.lane || "ai_raimo").slice(0, 40),
    title: String(p.title || "").slice(0, 200),
  };
  if (p.summary) compact.summary = String(p.summary).slice(0, 240);
  if (p.origin) compact.origin = String(p.origin).slice(0, 40);
  if (p.project_url) compact.project_url = String(p.project_url).slice(0, 300);
  if (p.labels?.length) {
    compact.labels = p.labels.map((x) => String(x).slice(0, 40)).slice(0, 5);
  }
  return b64urlEncode(JSON.stringify(compact));
}

export function decodeT312Proposal(b64: string): T312Proposal | null {
  const raw = b64urlDecode(b64);
  if (!raw) return null;
  try {
    const j = JSON.parse(raw) as T312Proposal;
    if (!j || typeof j !== "object") return null;
    const title = String(j.title || "").trim();
    const lane = String(j.lane || "").trim() || "ai_raimo";
    if (!title || title.length < 2) return null;
    return {
      n: Number(j.n) || 0,
      lane,
      title: title.slice(0, 200),
      summary: j.summary ? String(j.summary).slice(0, 240) : undefined,
      origin: j.origin ? String(j.origin).slice(0, 40) : undefined,
      project_url: j.project_url
        ? String(j.project_url).slice(0, 300)
        : undefined,
      labels: Array.isArray(j.labels)
        ? j.labels.map((x) => String(x).slice(0, 40)).slice(0, 5)
        : undefined,
    };
  } catch {
    return null;
  }
}

function t312SigWithSecret(
  secret: string,
  action: Todoist312Action,
  payloadB64: string,
): string {
  const payload = `t312:${action}:${payloadB64}`;
  return createHmac("sha256", secret)
    .update(payload, "utf8")
    .digest("hex")
    .slice(0, 10);
}

export function parseT312Action(
  raw: string | null | undefined,
): Todoist312Action | null {
  const a = (raw || "").trim().toLowerCase();
  if (a === "create" || a === "起票") return "create";
  if (a === "dismiss" || a === "skip" || a === "見送り") return "dismiss";
  return null;
}

/** value: t312:create:{b64}:{sig} | t312:dismiss:{b64}:{sig} */
export function parseT312ButtonValue(value: string): {
  action: Todoist312Action;
  payloadB64: string;
  proposal: T312Proposal;
  sig: string;
} | null {
  const s = String(value || "").trim();
  const m = s.match(
    /^t312:(create|dismiss):([A-Za-z0-9_-]+):([a-f0-9]{10})$/i,
  );
  if (!m) return null;
  const action = m[1].toLowerCase() as Todoist312Action;
  const payloadB64 = m[2];
  const sig = m[3].toLowerCase();
  const proposal = decodeT312Proposal(payloadB64);
  if (!proposal) return null;
  if (!t312SigOk(action, payloadB64, sig)) return null;
  return { action, payloadB64, proposal, sig };
}

export function t312Sig(action: Todoist312Action, payloadB64: string): string {
  const secret = actionSecret();
  if (!secret) return "";
  return t312SigWithSecret(secret, action, payloadB64);
}

export function t312SigOk(
  action: Todoist312Action,
  payloadB64: string,
  sig: string | null | undefined,
): boolean {
  const got = (sig || "").trim().toLowerCase();
  if (!got || got.length !== 10) return false;
  const secrets = candidateSecrets();
  if (!secrets.length) return false;
  for (const secret of secrets) {
    const expected = t312SigWithSecret(secret, action, payloadB64);
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

export function t312ButtonValue(
  action: Todoist312Action,
  proposal: T312Proposal,
): string {
  const b64 = encodeT312Proposal(proposal);
  const s = t312Sig(action, b64);
  return `t312:${action}:${b64}:${s}`;
}

export function t312ActionUrl(
  action: Todoist312Action,
  proposal: T312Proposal,
): string {
  const base = (
    process.env.JARVIS_DASHBOARD_URL ||
    process.env.NEXT_PUBLIC_SITE_URL ||
    "https://jarvis-dashboard-amber.vercel.app"
  )
    .trim()
    .replace(/\/$/, "");
  const b64 = encodeT312Proposal(proposal);
  const s = t312Sig(action, b64);
  const id = `n${proposal.n || 0}`;
  return `${base}/api/g/t312/${action}/${encodeURIComponent(id)}?p=${encodeURIComponent(b64)}&s=${s}`;
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
<title>${esc(title)}</title>
<body style="font-family:system-ui;padding:2rem;max-width:40rem;color:${color}">
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

async function postTodoistComment(
  taskId: string,
  content: string,
): Promise<void> {
  const token = (process.env.TODOIST_API_TOKEN || "").trim();
  if (!token || !taskId) return;
  try {
    await fetch("https://api.todoist.com/rest/v2/comments", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        task_id: taskId,
        content: content.slice(0, 1900),
      }),
    });
  } catch {
    /* soft-fail */
  }
}

function normalizeTitle(lane: string, titleIn: string): string {
  let title = titleIn.trim();
  if (!title.startsWith("[")) title = `[${lane}] ${title}`;
  if (!title.startsWith("[312]")) title = `[312]${title}`;
  return title.replace(/[。．.]+$/u, "").slice(0, 500);
}

export async function applyT312Action(opts: {
  action: Todoist312Action;
  proposal: T312Proposal;
  source: "slack_button" | "slack_link";
}): Promise<{ ok: boolean; message: string }> {
  const p = opts.proposal;
  const markN = p.n ? String(p.n) : "";
  const author =
    (process.env.TODOIST_312_AUTHOR || "").trim() || "FRIDAY";

  if (opts.action === "dismiss") {
    return {
      ok: true,
      message:
        `見送りました` +
        (markN ? `（#${markN}）` : "") +
        `\n※ ローカル digest state の dismiss は番号返信／Jarvis CLI で反映できます`,
    };
  }

  let lane = (p.lane || "ai_raimo").trim() || "ai_raimo";
  let title = normalizeTitle(lane, p.title);
  if (lane === "properties") {
    lane = "ai_raimo";
    if (title.startsWith("[properties]")) {
      title = "[ai_raimo]" + title.slice("[properties]".length);
    }
  }
  const origin = p.origin || "312";
  const labels =
    p.labels && p.labels.length
      ? p.labels
      : origin === "sb"
        ? ["SecondBrain", "quick"]
        : ["quick"];
  const summaryParts = [
    `312 Slack${opts.source === "slack_button" ? "ボタン" : "リンク"}起票`,
    p.summary || "",
    origin ? `origin=${origin}` : "",
  ].filter(Boolean);

  const r = await createTodoistTask(lane, {
    title,
    summary: summaryParts.join(" / ").slice(0, 1500),
    labels,
  });
  if (!r.ok) return { ok: false, message: r.error };

  const comment =
    `【${author}】\n` +
    `サマリ: 312 L1了承後の①create（Slack` +
    `${opts.source === "slack_button" ? "ボタン" : "リンク"}` +
    (markN ? `・#${markN}` : "") +
    `）\n` +
    `アウトプット:\n` +
    (p.project_url
      ? `- [会議](${p.project_url})\n`
      : `- [該当タスク](${r.url})\n`);
  await postTodoistComment(r.id, comment);

  return {
    ok: true,
    message:
      `起票しました` +
      (markN ? `（#${markN}）` : "") +
      `\n${r.url}`,
  };
}
