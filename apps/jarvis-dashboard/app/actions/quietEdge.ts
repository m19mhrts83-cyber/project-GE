"use server";

import { geminiReply, geminiVisionJson } from "@/lib/geminiReply";
import {
  addDaysYmd,
  SNORE_SCORE_TARGET,
  defaultMonthlyReviewYm,
  shiftMonthYm,
  ymdJst,
} from "@/lib/quietEdgeContext";
import { createClient } from "@/lib/supabase/server";
import { revalidatePath } from "next/cache";

export type SnoreEvent = "通常日" | "治療当日" | "治療直後";

export type SnoreDailyInput = {
  recorded_at: string;
  score: number;
  count?: number | null;
  event?: SnoreEvent | string;
  sleep_time?: string | null;
  memo?: string | null;
  source?: string;
  payload?: Record<string, unknown>;
};

export type QuietEdgeResult = { ok: true } | { ok: false; error: string };

export type ParsedSnoreShot = {
  screen: "score" | "count" | "unknown";
  recorded_at: string | null;
  score: number | null;
  count: number | null;
  sleep_time: string | null;
  count_vs_avg_delta: number | null;
  count_vs_avg_pct: number | null;
  raw_note: string | null;
};

export type ParseSnoreResult =
  | {
      ok: true;
      merged: SnoreDailyInput;
      parts: ParsedSnoreShot[];
    }
  | { ok: false; error: string };

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const EVENTS = new Set(["通常日", "治療当日", "治療直後"]);

function normalizeDate(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const s = String(raw).trim();
  if (DATE_RE.test(s)) return s;
  const m = s.match(/(\d{4})[\/\-年](\d{1,2})[\/\-月](\d{1,2})/);
  if (m) {
    return `${m[1]}-${m[2].padStart(2, "0")}-${m[3].padStart(2, "0")}`;
  }
  const m2 = s.match(/(\d{1,2})月\s*(\d{1,2})日/);
  if (m2) {
    const y = new Date().getFullYear();
    return `${y}-${m2[1].padStart(2, "0")}-${m2[2].padStart(2, "0")}`;
  }
  return null;
}

function revalidateQuietEdge() {
  revalidatePath("/quiet-edge");
}

export async function upsertSnoreDaily(
  input: SnoreDailyInput,
): Promise<QuietEdgeResult> {
  const recorded_at = normalizeDate(input.recorded_at);
  if (!recorded_at) return { ok: false, error: "日付が不正です" };
  const score = Number(input.score);
  if (!Number.isFinite(score)) return { ok: false, error: "スコアが不正です" };

  const event = EVENTS.has(String(input.event))
    ? String(input.event)
    : "通常日";
  const count =
    input.count == null || input.count === ("" as unknown)
      ? null
      : Number(input.count);
  if (count != null && !Number.isFinite(count)) {
    return { ok: false, error: "回数が不正です" };
  }

  const supabase = await createClient();
  const { data: existing } = await supabase
    .from("vital_snore_daily")
    .select("count,sleep_time,memo,payload,score")
    .eq("recorded_at", recorded_at)
    .maybeSingle();

  const prevPayload =
    existing?.payload && typeof existing.payload === "object"
      ? (existing.payload as Record<string, unknown>)
      : {};
  const payload = { ...prevPayload, ...(input.payload || {}) };

  const row = {
    recorded_at,
    score,
    count: count ?? existing?.count ?? null,
    event,
    sleep_time:
      (input.sleep_time && String(input.sleep_time).trim()) ||
      existing?.sleep_time ||
      null,
    memo:
      input.memo != null
        ? String(input.memo)
        : (existing?.memo as string | null) || null,
    source: input.source || "manual",
    payload,
    updated_at: new Date().toISOString(),
  };

  const { error } = await supabase
    .from("vital_snore_daily")
    .upsert(row, { onConflict: "recorded_at" });
  if (error) return { ok: false, error: error.message };

  revalidateQuietEdge();
  return { ok: true };
}

export async function deleteSnoreDaily(
  recordedAt: string,
): Promise<QuietEdgeResult> {
  const recorded_at = normalizeDate(recordedAt);
  if (!recorded_at) return { ok: false, error: "日付が不正です" };
  const supabase = await createClient();
  const { error } = await supabase
    .from("vital_snore_daily")
    .delete()
    .eq("recorded_at", recorded_at);
  if (error) return { ok: false, error: error.message };
  revalidateQuietEdge();
  return { ok: true };
}

export async function importSnoreRecords(
  records: SnoreDailyInput[],
): Promise<QuietEdgeResult & { imported?: number }> {
  if (!Array.isArray(records) || records.length === 0) {
    return { ok: false, error: "レコードが空です" };
  }
  let n = 0;
  for (const r of records) {
    const res = await upsertSnoreDaily({ ...r, source: r.source || "import" });
    if (!res.ok) return { ok: false, error: res.error };
    n += 1;
  }
  return { ok: true, imported: n };
}

const OCR_PROMPT = `あなたは AutoSnore（いびき計測アプリ）のスクリーンショット解析器です。
画像は次のいずれかです:
1) screen=score: 「イビガースコア」画面。大きな数値スコア(0-100)、日付（例: 8月7日）、睡眠時間帯（例: 22:45:29 - 6:02:19）
2) screen=count: 「検出」回数画面。円の中の大きな整数回数、「N月N日〜N月N日の間」「平均より±N回」「±N%」など

厳守:
- 診断や治療助言は書かない
- JSON のみ返す（解説文禁止）
- 記録日 recorded_at は起床側の暦日（回数画面が「木〜金」なら金の日付）を YYYY-MM-DD にする。年が無い場合は画像の文脈または 2026 年を仮定
- sleep_time は "HH:MM - HH:MM" 形式に正規化（秒は落とす）

出力スキーマ:
{
  "screen": "score" | "count" | "unknown",
  "recorded_at": "YYYY-MM-DD" | null,
  "score": number | null,
  "count": number | null,
  "sleep_time": string | null,
  "count_vs_avg_delta": number | null,
  "count_vs_avg_pct": number | null,
  "raw_note": string | null
}`;

function asNum(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = typeof v === "number" ? v : Number(String(v).replace(/,/g, ""));
  return Number.isFinite(n) ? n : null;
}

function parseShot(obj: Record<string, unknown>): ParsedSnoreShot {
  const screenRaw = String(obj.screen || "unknown");
  const screen =
    screenRaw === "score" || screenRaw === "count" ? screenRaw : "unknown";
  return {
    screen,
    recorded_at: normalizeDate(
      obj.recorded_at != null ? String(obj.recorded_at) : null,
    ),
    score: asNum(obj.score),
    count: asNum(obj.count),
    sleep_time: obj.sleep_time != null ? String(obj.sleep_time) : null,
    count_vs_avg_delta: asNum(obj.count_vs_avg_delta),
    count_vs_avg_pct: asNum(obj.count_vs_avg_pct),
    raw_note: obj.raw_note != null ? String(obj.raw_note) : null,
  };
}

export async function parseSnoreScreenshots(
  formData: FormData,
): Promise<ParseSnoreResult> {
  const files = formData.getAll("images").filter((f): f is File => f instanceof File);
  if (files.length === 0) {
    return { ok: false, error: "画像がありません" };
  }
  const toProcess = files.slice(0, 2);
  const parts: ParsedSnoreShot[] = [];

  for (const file of toProcess) {
    const buf = Buffer.from(await file.arrayBuffer());
    const mime = file.type || "image/jpeg";
    const b64 = buf.toString("base64");
    const vision = await geminiVisionJson(
      [{ mimeType: mime, base64: b64 }],
      OCR_PROMPT,
    );
    if (!vision.ok) return { ok: false, error: vision.error };
    parts.push(parseShot(vision.json));
  }

  let recorded_at: string | null = null;
  let score: number | null = null;
  let count: number | null = null;
  let sleep_time: string | null = null;
  const payload: Record<string, unknown> = {};
  const notes: string[] = [];

  for (const p of parts) {
    if (p.recorded_at) recorded_at = p.recorded_at;
    if (p.score != null) score = p.score;
    if (p.count != null) count = p.count;
    if (p.sleep_time) sleep_time = p.sleep_time;
    if (p.count_vs_avg_delta != null) {
      payload.count_vs_avg_delta = p.count_vs_avg_delta;
    }
    if (p.count_vs_avg_pct != null) {
      payload.count_vs_avg_pct = p.count_vs_avg_pct;
    }
    if (p.raw_note) notes.push(p.raw_note);
  }

  if (score == null) {
    return {
      ok: false,
      error:
        "イビガースコアを読み取れませんでした。スコア画面のスクショを含めてください。",
    };
  }
  if (!recorded_at) {
    return { ok: false, error: "日付を読み取れませんでした" };
  }

  return {
    ok: true,
    parts,
    merged: {
      recorded_at,
      score,
      count,
      event: "通常日",
      sleep_time,
      memo: notes.length ? `AI読取: ${notes.join(" / ")}` : "",
      source: "autosnore_ocr",
      payload,
    },
  };
}

export type ContextNoteInput = {
  recorded_at: string;
  trigger: string;
  prompt: string;
  answer: string;
};

export async function saveContextNote(
  input: ContextNoteInput,
): Promise<QuietEdgeResult> {
  const recorded_at = normalizeDate(input.recorded_at);
  if (!recorded_at) return { ok: false, error: "日付が不正です" };
  const answer = String(input.answer || "").trim();
  if (!answer) return { ok: false, error: "回答が空です" };
  const trigger = String(input.trigger || "manual").trim() || "manual";
  const prompt = String(input.prompt || "").trim();

  const supabase = await createClient();
  const { error } = await supabase.from("vital_context_notes").insert({
    recorded_at,
    trigger,
    prompt,
    answer,
    source: "user_reply",
    payload: {},
  });
  if (error) return { ok: false, error: error.message };
  revalidateQuietEdge();
  return { ok: true };
}

export type QuietEdgeReviewResult =
  | { ok: true; text: string; created_at?: string }
  | { ok: false; error: string };

/** Journal・補完・いびき・Health を横断した観察整理（診断禁止） */
export async function generateQuietEdgeReview(): Promise<QuietEdgeReviewResult> {
  const supabase = await createClient();
  const sinceYmd = addDaysYmd(ymdJst(), -20);

  const [snore, health, journal, notes, treatments] = await Promise.all([
    supabase
      .from("vital_snore_daily")
      .select("recorded_at,score,count,event,sleep_time,memo")
      .gte("recorded_at", sinceYmd)
      .order("recorded_at", { ascending: true }),
    supabase
      .from("vital_daily")
      .select("recorded_at,metric,value,unit,source")
      .gte("recorded_at", sinceYmd)
      .order("recorded_at", { ascending: true }),
    supabase
      .from("vital_journal_daily")
      .select("recorded_at,excerpt,char_count,sleep_signal,sleep_tags")
      .gte("recorded_at", sinceYmd)
      .order("recorded_at", { ascending: true }),
    supabase
      .from("vital_context_notes")
      .select("recorded_at,trigger,prompt,answer,created_at")
      .gte("recorded_at", sinceYmd)
      .order("created_at", { ascending: false })
      .limit(30),
    supabase
      .from("vital_treatment_events")
      .select("session_no,scheduled_at,label,status")
      .order("session_no", { ascending: true }),
  ]);

  const bundle = {
    window: { since: sinceYmd, days: 21 },
    snore: snore.data || [],
    health: health.data || [],
    journal: (journal.data || []).map((j) => ({
      recorded_at: j.recorded_at,
      char_count: j.char_count,
      sleep_signal: j.sleep_signal || "",
      sleep_tags: j.sleep_tags || [],
      excerpt: String(j.excerpt || "").slice(0, 400),
    })),
    context_notes: notes.data || [],
    treatments: treatments.data || [],
  };

  const prompt = `あなたは Quiet Edge（いびきレーザー治療の経過観察アプリ）の観察アシスタントです。
診断・病名断定・治療指示は禁止。医師に見せるための観察整理のみ。

データ（JSON）:
${JSON.stringify(bundle, null, 2)}

出力（日本語・箇条書き中心）:
1. 直近の傾向（いびきスコア／回数、分かる範囲の睡眠・呼吸）
2. Journal の sleep_signal / sleep_tags を必ず使い、いびき悪化・改善日と生活要因（就寝遅れ・飲酒・遅夜作業など）の重なりを具体日で書く
3. 治療スケジュールとの時系列の重なり（ある場合）
4. 欠測・確認したい点（データが薄い日）
5. 次回診察で見せるとよい観察ポイント（質問リスト形式可）

厳守: 「診断」「睡眠時無呼吸確定」などの断定をしない。短く（目安 400〜700 字）。`;

  const res = await geminiReply(prompt);
  if (!res.ok) return { ok: false, error: res.error };
  return { ok: true, text: res.text };
}

function fallbackIngestReview(input: {
  recorded_at: string;
  score: number;
  count: number | null;
  prevScore: number | null;
  avg7: number | null;
  bestScore: number | null;
  hasJournal: boolean;
  sleepSignal: string;
  sleepTags: string[];
  healthBits: string[];
  nearTreatment: string | null;
}): string {
  const lines: string[] = [];
  lines.push(`📅 ${input.recorded_at} の取込レビュー（観察メモ）`);
  lines.push(
    `いびきスコア ${input.score.toFixed(1)}` +
      (input.count != null
        ? `／いびき回数 ${input.count.toLocaleString("ja-JP")}回`
        : ""),
  );
  if (input.prevScore != null) {
    const d = input.score - input.prevScore;
    if (d <= -3) {
      lines.push(`前回よりスコアが ${Math.abs(d).toFixed(1)} 改善。良い流れです。`);
    } else if (d >= 3) {
      lines.push(
        `前回よりスコアが +${d.toFixed(1)}。生活要因（飲酒・鼻・残業など）を Journal で振り返ると次に活かせます。`,
      );
    } else {
      lines.push("前回とほぼ同水準。記録を続けていること自体が強みです。");
    }
  }
  if (input.avg7 != null) {
    const vs = input.score - input.avg7;
    lines.push(
      vs <= -2
        ? `直近7日平均（${input.avg7.toFixed(1)}）より良い夜でした。`
        : `直近7日平均は ${input.avg7.toFixed(1)}。平均との差を見て傾向を掴みましょう。`,
    );
  }
  const gap = input.score - SNORE_SCORE_TARGET;
  if (gap <= 0) {
    lines.push(
      `改善目標（スコア≤${SNORE_SCORE_TARGET}）到達圏です。この水準を定着させる観察を続けましょう。`,
    );
  } else {
    lines.push(
      `改善目標まであとスコア約 ${gap.toFixed(1)}（目安≤${SNORE_SCORE_TARGET}・観察用）。一歩ずつで十分です。`,
    );
  }
  if (input.bestScore != null && input.score <= input.bestScore + 0.2) {
    lines.push("これまでの最良スコアに近い／並ぶ夜です。");
  }
  if (input.healthBits.length) {
    lines.push(`Health: ${input.healthBits.join("、")}`);
  }
  if (input.sleepSignal) {
    lines.push(`Journal睡眠シグナル: ${input.sleepSignal}`);
    if (input.sleepTags.includes("bedtime_late") && input.score >= 30) {
      lines.push("就寝遅れといびき高めが同日です。因果の断定はせず、傾向のメモとして残しましょう。");
    }
    if (input.sleepTags.includes("bedtime_ok") && input.score <= 25) {
      lines.push("就寝達成の夜とスコアが噛み合っています。良いパターンです。");
    }
  } else if (input.hasJournal) {
    lines.push("同日 Journal はあるが睡眠シグナルが薄いです。防衛線の一行があると照合しやすいです。");
  } else {
    lines.push("同日 Journal が薄い／なし。短くでも夜のメモがあると次のレビューが厚くなります。");
  }
  if (input.nearTreatment) {
    lines.push(`治療予定: ${input.nearTreatment}`);
  }
  lines.push("※診断ではありません。励ましと観察の整理です。");
  return lines.join("\n");
}

/** 取込直後の短い励ましレビュー（いびき＋Health＋Journal＋治療） */
export async function generateQuietEdgeIngestReview(
  recordedAt: string,
): Promise<QuietEdgeReviewResult> {
  const recorded_at = normalizeDate(recordedAt);
  if (!recorded_at) return { ok: false, error: "日付が不正です" };

  const supabase = await createClient();
  const sinceYmd = addDaysYmd(recorded_at, -14);

  const [snore, health, journal, notes, treatments] = await Promise.all([
    supabase
      .from("vital_snore_daily")
      .select("recorded_at,score,count,event,sleep_time,memo")
      .gte("recorded_at", sinceYmd)
      .lte("recorded_at", recorded_at)
      .order("recorded_at", { ascending: true }),
    supabase
      .from("vital_daily")
      .select("recorded_at,metric,value,unit,source")
      .eq("recorded_at", recorded_at),
    supabase
      .from("vital_journal_daily")
      .select("recorded_at,excerpt,char_count,sleep_signal,sleep_tags")
      .eq("recorded_at", recorded_at)
      .maybeSingle(),
    supabase
      .from("vital_context_notes")
      .select("recorded_at,trigger,answer")
      .eq("recorded_at", recorded_at)
      .order("created_at", { ascending: false })
      .limit(5),
    supabase
      .from("vital_treatment_events")
      .select("session_no,scheduled_at,label,status")
      .order("session_no", { ascending: true }),
  ]);

  const snoreRows = snore.data || [];
  const today = snoreRows.find((r) => r.recorded_at === recorded_at);
  if (!today) {
    return { ok: false, error: "取込データが見つかりません。保存後に再試行してください。" };
  }

  const prev = [...snoreRows]
    .filter((r) => r.recorded_at < recorded_at)
    .sort((a, b) => b.recorded_at.localeCompare(a.recorded_at))[0];
  const last7 = snoreRows.filter((r) => r.recorded_at <= recorded_at).slice(-7);
  const avg7 =
    last7.length > 0
      ? last7.reduce((s, r) => s + Number(r.score), 0) / last7.length
      : null;
  const bestScore =
    snoreRows.length > 0
      ? Math.min(...snoreRows.map((r) => Number(r.score)))
      : null;

  const healthBits: string[] = [];
  const prefer = new Map<string, { value: number; unit: string | null; source: string }>();
  for (const h of health.data || []) {
    const rank = h.source === "oramemo" ? 0 : h.source === "watch" ? 1 : 2;
    const prevH = prefer.get(h.metric);
    const prevRank = prevH
      ? prevH.source === "oramemo"
        ? 0
        : prevH.source === "watch"
          ? 1
          : 2
      : 99;
    if (!prevH || rank < prevRank) {
      prefer.set(h.metric, {
        value: Number(h.value),
        unit: h.unit,
        source: h.source,
      });
    }
  }
  const labels: Record<string, (v: number) => string> = {
    sleep_hours: (v) => `睡眠 ${v.toFixed(1)}時間`,
    spo2: (v) => `SpO2 ${Math.round(v)}%`,
    respiratory_rate: (v) => `呼吸 ${v.toFixed(1)}回/分`,
    hrv: (v) => `HRV ${Math.round(v)}ms`,
    resting_hr: (v) => `安静時心拍 ${Math.round(v)}bpm`,
  };
  for (const [k, fmt] of Object.entries(labels)) {
    const row = prefer.get(k);
    if (row) healthBits.push(fmt(row.value));
  }

  const nextTreat = (treatments.data || []).find((t) => t.status === "scheduled");
  let nearTreatment: string | null = null;
  if (nextTreat?.scheduled_at) {
    const days = Math.ceil(
      (new Date(nextTreat.scheduled_at).getTime() - Date.now()) /
        (1000 * 60 * 60 * 24),
    );
    nearTreatment = `${nextTreat.label}（あと約${days}日）`;
  }

  const journalExcerpt = journal.data?.excerpt
    ? String(journal.data.excerpt).slice(0, 280)
    : "";
  const sleepSignal = String(journal.data?.sleep_signal || "").trim();
  const sleepTags = (journal.data?.sleep_tags as string[] | null) || [];
  const hasJournal = Boolean(
    (sleepSignal || journalExcerpt) && (journal.data?.char_count || 0) >= 40,
  );

  const fallback = fallbackIngestReview({
    recorded_at,
    score: Number(today.score),
    count: today.count,
    prevScore: prev ? Number(prev.score) : null,
    avg7,
    bestScore,
    hasJournal,
    sleepSignal,
    sleepTags,
    healthBits,
    nearTreatment,
  });

  const bundle = {
    focus_date: recorded_at,
    score_target: SNORE_SCORE_TARGET,
    today,
    previous: prev || null,
    avg7_score: avg7,
    best_score_in_window: bestScore,
    health_today: [...prefer.entries()].map(([metric, v]) => ({
      metric,
      ...v,
    })),
    journal_today: hasJournal
      ? {
          char_count: journal.data?.char_count,
          sleep_signal: sleepSignal,
          sleep_tags: sleepTags,
          excerpt: journalExcerpt,
        }
      : null,
    context_notes_today: notes.data || [],
    next_treatment: nextTreat || null,
    recent_snore: snoreRows.slice(-10),
  };

  const prompt = `あなたは Quiet Edge の励ましコーチです。いまユーザーが AutoSnore データを取り込みました。
診断・病名断定・治療指示は禁止。観察と励ましのみ。短く温かく。

参照データ（JSON）:
${JSON.stringify(bundle, null, 2)}

必ず含める（箇条書き・日本語・目安 180〜320 字）:
1. 今日のいびきスコア／回数を一言で認める
2. 前回または直近平均との比較（分かる範囲）
3. 改善目標（スコア≤${SNORE_SCORE_TARGET}）までの距離か到達の喜び
4. journal_today.sleep_signal / sleep_tags があれば必ず触れ、いびきとの重なりを観察として書く（無いときは Health / 補完 / 治療のどれか）
5. 明日も続けたくなる一文

禁止: 医療診断、恐怖訴求、長文。業務タスク（会議・資料）の要約は不要。睡眠・生活要因だけ。`;

  const res = await geminiReply(prompt);
  const text = res.ok ? res.text.trim() || fallback : fallback;
  const title = `取込レビュー ${recorded_at}`;
  const { data: saved } = await supabase
    .from("vital_quiet_reviews")
    .insert({
      kind: "ingest",
      period_key: recorded_at,
      title,
      body: text,
      payload: {
        score: today.score,
        count: today.count,
        sleep_signal: sleepSignal,
        sleep_tags: sleepTags,
      },
    })
    .select("created_at")
    .maybeSingle();
  revalidateQuietEdge();
  return {
    ok: true,
    text,
    created_at: saved?.created_at || new Date().toISOString(),
  };
}

function prevMonthKey(ym: string): string {
  return shiftMonthYm(ym, -1);
}

function monthRange(ym: string): { start: string; end: string } {
  const [y, m] = ym.split("-").map(Number);
  const start = `${ym}-01`;
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const end = `${ym}-${String(last).padStart(2, "0")}`;
  return { start, end };
}

function summarizeMonth(
  snore: Array<{
    recorded_at: string;
    score: number;
    count: number | null;
  }>,
  journals: Array<{
    recorded_at: string;
    sleep_signal: string | null;
    sleep_tags: string[] | null;
  }>,
) {
  const scores = snore.map((r) => Number(r.score)).filter(Number.isFinite);
  const counts = snore
    .map((r) => r.count)
    .filter((c): c is number => c != null && Number.isFinite(c));
  const tagCount: Record<string, number> = {};
  for (const j of journals) {
    for (const t of j.sleep_tags || []) {
      tagCount[t] = (tagCount[t] || 0) + 1;
    }
  }
  const avg = (xs: number[]) =>
    xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
  return {
    days: snore.length,
    avg_score: avg(scores),
    min_score: scores.length ? Math.min(...scores) : null,
    max_score: scores.length ? Math.max(...scores) : null,
    avg_count: avg(counts),
    target_hit_days: scores.filter((s) => s <= SNORE_SCORE_TARGET).length,
    journal_days: journals.length,
    sleep_tag_counts: tagCount,
    bedtime_ok_days: tagCount.bedtime_ok || 0,
    bedtime_late_days: tagCount.bedtime_late || 0,
  };
}

/** 月次レビュー（対象月 vs その前月。既定の対象は「先月」） */
export async function generateQuietEdgeMonthlyReview(
  monthYm?: string,
): Promise<QuietEdgeReviewResult & { period?: string }> {
  const ym =
    monthYm && /^\d{4}-\d{2}$/.test(monthYm)
      ? monthYm
      : defaultMonthlyReviewYm();
  const prevYm = prevMonthKey(ym);
  const cur = monthRange(ym);
  const prev = monthRange(prevYm);
  const supabase = await createClient();

  const [snoreCur, snorePrev, journalCur, journalPrev, treatments, healthCur] =
    await Promise.all([
      supabase
        .from("vital_snore_daily")
        .select("recorded_at,score,count,event")
        .gte("recorded_at", cur.start)
        .lte("recorded_at", cur.end)
        .order("recorded_at", { ascending: true }),
      supabase
        .from("vital_snore_daily")
        .select("recorded_at,score,count,event")
        .gte("recorded_at", prev.start)
        .lte("recorded_at", prev.end)
        .order("recorded_at", { ascending: true }),
      supabase
        .from("vital_journal_daily")
        .select("recorded_at,sleep_signal,sleep_tags,excerpt,char_count")
        .gte("recorded_at", cur.start)
        .lte("recorded_at", cur.end),
      supabase
        .from("vital_journal_daily")
        .select("recorded_at,sleep_signal,sleep_tags,excerpt,char_count")
        .gte("recorded_at", prev.start)
        .lte("recorded_at", prev.end),
      supabase
        .from("vital_treatment_events")
        .select("session_no,scheduled_at,label,status")
        .order("session_no", { ascending: true }),
      supabase
        .from("vital_daily")
        .select("recorded_at,metric,value,source")
        .gte("recorded_at", cur.start)
        .lte("recorded_at", cur.end),
    ]);

  const curSum = summarizeMonth(snoreCur.data || [], journalCur.data || []);
  const prevSum = summarizeMonth(snorePrev.data || [], journalPrev.data || []);

  const journalSignals = (journalCur.data || [])
    .filter((j) => j.sleep_signal)
    .map((j) => ({
      recorded_at: j.recorded_at,
      sleep_signal: j.sleep_signal,
      sleep_tags: j.sleep_tags,
    }))
    .slice(0, 20);

  const bundle = {
    month: ym,
    previous_month: prevYm,
    score_target: SNORE_SCORE_TARGET,
    current: curSum,
    previous: prevSum,
    journal_sleep_signals: journalSignals,
    treatments: treatments.data || [],
    health_rows_current_month: (healthCur.data || []).length,
  };

  const fallbackLines = [
    `📊 ${ym} の月次レビュー（観察）`,
    `記録日数: ${curSum.days}日（前月 ${prevSum.days}日）`,
    curSum.avg_score != null
      ? `平均いびきスコア: ${curSum.avg_score.toFixed(1)}` +
        (prevSum.avg_score != null
          ? `（前月 ${prevSum.avg_score.toFixed(1)} / 差 ${(curSum.avg_score - prevSum.avg_score).toFixed(1)}）`
          : "")
      : "平均いびきスコア: データ不足",
    `改善目標≤${SNORE_SCORE_TARGET} 到達: ${curSum.target_hit_days}日`,
    `Journal 就寝達成 ${curSum.bedtime_ok_days}日 / 就寝遅れ ${curSum.bedtime_late_days}日`,
    "※診断ではありません。翌月の観察ポイントとして使ってください。",
  ];
  const fallback = fallbackLines.join("\n");

  const prompt = `あなたは Quiet Edge の月次観察コーチです。
診断・病名断定・治療指示は禁止。前月比較と「今月／来月気をつける点」を出す。

データ（JSON）:
${JSON.stringify(bundle, null, 2)}

出力（日本語・見出し付き・目安 450〜750 字）:
1. ${ym} の総括（いびきスコア／回数の傾向）
2. 前月（${prevYm}）との比較（良くなった点・悪化した点）
3. Journal 睡眠シグナル（就寝達成／遅れ／飲酒／遅夜作業）といびきの重なり
4. 来月気をつけるポイント（2〜4個・実行しやすい観察行動）
5. 励ましの一文

禁止: 業務タスクの列挙、医療診断、恐怖訴求。`;

  const res = await geminiReply(prompt);
  const text = res.ok ? res.text.trim() || fallback : fallback;
  const title = `${ym} の分析レビュー`;
  const { data: saved } = await supabase
    .from("vital_quiet_reviews")
    .insert({
      kind: "monthly",
      period_key: ym,
      title,
      body: text,
      payload: bundle,
    })
    .select("created_at")
    .maybeSingle();
  revalidateQuietEdge();
  return {
    ok: true,
    text,
    period: ym,
    created_at: saved?.created_at || new Date().toISOString(),
  };
}

export type QuietReviewRow = {
  id: number;
  kind: "ingest" | "monthly";
  period_key: string;
  title: string;
  body: string;
  created_at: string;
};

/** 直近の取込レビュー1件 */
export async function loadLatestIngestReview(): Promise<QuietReviewRow | null> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("vital_quiet_reviews")
    .select("id,kind,period_key,title,body,created_at")
    .eq("kind", "ingest")
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  return (data as QuietReviewRow | null) || null;
}

/** 指定年月（YYYY-MM）の最新月次レビュー。未指定時は先月（JST） */
export async function loadLatestMonthlyReview(
  monthYm?: string,
): Promise<QuietReviewRow | null> {
  const ym =
    monthYm && /^\d{4}-\d{2}$/.test(monthYm)
      ? monthYm
      : defaultMonthlyReviewYm();
  const supabase = await createClient();
  const { data } = await supabase
    .from("vital_quiet_reviews")
    .select("id,kind,period_key,title,body,created_at")
    .eq("kind", "monthly")
    .eq("period_key", ym)
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  return (data as QuietReviewRow | null) || null;
}
