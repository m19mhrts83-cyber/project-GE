/**
 * Slack Interactivity — メール要対応（返信／見送り／Todoist）
 */
import {
  applyMailActionSlack,
  deleteSlackMaMessage,
  fetchMailActionTriage,
  isMailActionTriageId,
  guessMailReplyTo,
  MAIL_SEND_ACCOUNTS,
  maActionUrl,
  normalizeMailAccount,
  parseMaAction,
  type MailActionSlackAction,
} from "@/lib/mailActionSlackAction";
import { proofreadDraft, reviseDraft } from "@/lib/mailDraftCheck";
import { searchMaterialFiles } from "@/lib/materialFiles";
import {
  candidateValue,
  humanSize,
  parseCandidateValue,
  searchTermsFromItems,
  type MaterialCandidate,
} from "@/lib/materialFileSearch";
import { extractMaterialRequests } from "@/lib/materialRequest";

export const MA_ACTION_IDS = {
  reply: "mail_action_reply",
  skip: "mail_action_skip",
  todoist: "mail_action_todoist",
  done: "mail_action_done",
} as const;

export const MA_MODAL_CALLBACK = "mail_action_reply_modal";

export type MaModalMeta = {
  id: string;
  channel?: string;
  message_ts?: string;
};

/** value: ma:reply|skip|todoist|done:{triage_id} */
export function parseMaButtonValue(
  value: string,
): { action: MailActionSlackAction; id: string } | null {
  const m = String(value || "")
    .trim()
    .match(/^ma:(reply|skip|todoist|done):([a-zA-Z0-9_.:-]{6,80})$/i);
  if (!m) return null;
  const action = parseMaAction(m[1]);
  const id = m[2];
  if (!action || !isMailActionTriageId(id)) return null;
  return { action, id };
}

export function parseMaModalMeta(raw: string): MaModalMeta | null {
  const s = String(raw || "").trim();
  if (!s) return null;
  if (isMailActionTriageId(s)) return { id: s };
  try {
    const j = JSON.parse(s) as Record<string, unknown>;
    const id = String(j.id || "").trim();
    if (!isMailActionTriageId(id)) return null;
    return {
      id,
      channel: String(j.channel || "").trim() || undefined,
      message_ts: String(j.message_ts || j.ts || "").trim() || undefined,
    };
  } catch {
    return null;
  }
}

export function maDoneBlocks(title: string, detail: string, ok: boolean) {
  const icon = ok ? "✅" : "❌";
  return [
    {
      type: "section",
      text: {
        type: "mrkdwn" as const,
        text: `${icon} *${title}*\n${detail}`,
      },
    },
  ];
}

/** モーダル内ボタン（誤字脱字チェック／見直し） */
export const MA_MODAL_ACTION_IDS = {
  proofread: "mail_action_modal_proofread",
  revise: "mail_action_modal_revise",
  findFiles: "mail_action_modal_find_files",
} as const;

type MaModalState = {
  body: string;
  to: string;
  account: string;
  instruction: string;
  /** 資料の検索語（任意） */
  fileQuery: string;
  /** 添付に選んだ候補（od:{id} / gd:{id}） */
  files: string[];
};

const EMPTY_STATE: MaModalState = {
  body: "", to: "", account: "", instruction: "", fileQuery: "", files: [],
};

type ReplyViewInput = {
  meta: MaModalMeta;
  who: string;
  inbound: string;
  state: MaModalState;
  /** 本文ブロックの版。上げると initial_value が反映される（Slack は同じ block_id の入力を保持する） */
  version: number;
  notice?: string;
  busy?: boolean;
  /** 依頼された資料（本文から抽出） */
  materials?: string[];
  /** 探した添付候補（private_metadata に持ち回る） */
  candidates?: MaterialCandidate[];
  /** 依頼品目がなくても検索語欄を出す */
  showFileQuery?: boolean;
};

const SOURCE_LABEL = { od: "OneDrive", gd: "Google Drive" } as const;

function fileOption(c: MaterialCandidate) {
  const size = humanSize(c.z);
  return {
    text: { type: "plain_text" as const, text: c.n.slice(0, 75) },
    description: {
      type: "plain_text" as const,
      text: [SOURCE_LABEL[c.s], size, (c.m || "").slice(0, 10)].filter(Boolean).join("・"),
    },
    value: candidateValue(c),
  };
}

/** private_metadata は 3000 字まで。候補名は短くして持つ */
function packMeta(meta: MaModalMeta, version: number, cands: MaterialCandidate[]): string {
  const c = cands.map((x) => ({ s: x.s, id: x.id, n: x.n.slice(0, 60), z: x.z, m: (x.m || "").slice(0, 10) }));
  let raw = JSON.stringify({ ...meta, v: version, c });
  while (raw.length > 2900 && c.length) {
    c.pop();
    raw = JSON.stringify({ ...meta, v: version, c });
  }
  return raw;
}

function metaCandidates(metaRaw: string): MaterialCandidate[] {
  try {
    const j = JSON.parse(metaRaw) as { c?: unknown };
    if (!Array.isArray(j.c)) return [];
    return j.c
      .map((x) => x as MaterialCandidate)
      .filter((x) => (x.s === "od" || x.s === "gd") && typeof x.id === "string" && typeof x.n === "string");
  } catch {
    return [];
  }
}

function metaVersion(metaRaw: string): number {
  try {
    return Number((JSON.parse(metaRaw) as { v?: number }).v || 1) || 1;
  } catch {
    return 1;
  }
}

function buildReplyView(input: ReplyViewInput) {
  const { meta, state, version } = input;
  const inbound = (input.inbound || "").slice(0, 1500);
  const accountOptions = MAIL_SEND_ACCOUNTS.map((a) => ({
    text: { type: "plain_text" as const, text: a.label },
    value: a.key,
  }));
  const initialAccount =
    accountOptions.find((o) => o.value === state.account) || accountOptions[0];
  const blocks: Array<Record<string, unknown>> = [
    {
      type: "section",
      text: {
        type: "mrkdwn",
        text: `*相手:* ${input.who.slice(0, 80)}
\`\`\`${inbound || "(本文なし)"}\`\`\``,
      },
    },
    {
      type: "input",
      block_id: "mail_reply_from_block",
      label: { type: "plain_text", text: "送信元" },
      element: {
        type: "static_select",
        action_id: "mail_reply_from",
        options: accountOptions,
        initial_option: initialAccount,
      },
    },
    {
      type: "input",
      block_id: "mail_reply_to_block",
      label: { type: "plain_text", text: "宛先" },
      element: {
        type: "plain_text_input",
        action_id: "mail_reply_to",
        ...(state.to ? { initial_value: state.to } : {}),
        placeholder: { type: "plain_text", text: "name@example.com" },
      },
    },
    {
      type: "input",
      block_id: `mail_reply_body_block_v${version}`,
      label: { type: "plain_text", text: "返信本文（直接修正できます）" },
      element: {
        type: "plain_text_input",
        action_id: "mail_reply_body",
        multiline: true,
        initial_value: state.body || "",
      },
    },
    {
      type: "input",
      block_id: `mail_reply_instr_block_v${version}`,
      optional: true,
      label: { type: "plain_text", text: "見直し指示（任意）" },
      element: {
        type: "plain_text_input",
        action_id: "mail_reply_instr",
        ...(state.instruction ? { initial_value: state.instruction } : {}),
        placeholder: {
          type: "plain_text",
          text: "例: もう少し柔らかく／日程候補を3つ提示する形に",
        },
      },
    },
    {
      type: "actions",
      block_id: "mail_reply_tools",
      elements: [
        {
          type: "button",
          action_id: MA_MODAL_ACTION_IDS.proofread,
          text: { type: "plain_text", text: "誤字脱字チェック" },
          value: "proofread",
        },
        {
          type: "button",
          action_id: MA_MODAL_ACTION_IDS.revise,
          text: { type: "plain_text", text: "指示で見直し" },
          value: "revise",
        },
        {
          type: "button",
          action_id: MA_MODAL_ACTION_IDS.findFiles,
          text: { type: "plain_text", text: "📎 資料を探す" },
          value: "find_files",
        },
      ],
    },
  ];
  const materials = input.materials || [];
  const cands = input.candidates || [];
  if (materials.length || cands.length || state.fileQuery || input.showFileQuery) {
    if (materials.length) {
      blocks.push({
        type: "context",
        elements: [
          {
            type: "mrkdwn",
            text: `📎 *依頼された資料:* ${materials.map((m) => m.slice(0, 40)).join(" ／ ")}`.slice(0, 2900),
          },
        ],
      });
    }
    blocks.push({
      type: "input",
      block_id: "mail_reply_fquery_block",
      optional: true,
      label: { type: "plain_text", text: "資料の検索語（任意・空なら依頼品目で探す）" },
      element: {
        type: "plain_text_input",
        action_id: "mail_reply_fquery",
        ...(state.fileQuery ? { initial_value: state.fileQuery } : {}),
        placeholder: { type: "plain_text", text: "例: 謄本 2025 試算表" },
      },
    });
  }
  if (cands.length) {
    const options = cands.map(fileOption);
    const initial = options.filter((o) => state.files.includes(o.value));
    blocks.push({
      type: "input",
      block_id: `mail_reply_files_block_v${version}`,
      optional: true,
      label: { type: "plain_text", text: "添付する資料（チェックしたものを添付）" },
      element: {
        type: "checkboxes",
        action_id: "mail_reply_files",
        options,
        ...(initial.length ? { initial_options: initial } : {}),
      },
    });
  }
  if (input.notice) {
    blocks.push({
      type: "context",
      elements: [{ type: "mrkdwn", text: input.notice.slice(0, 2900) }],
    });
  }
  return {
    type: "modal",
    callback_id: MA_MODAL_CALLBACK,
    private_metadata: packMeta(meta, version, cands),
    title: { type: "plain_text", text: "メール返信" },
    submit: { type: "plain_text", text: input.busy ? "送信（点検中）" : "送信" },
    close: { type: "plain_text", text: "キャンセル" },
    blocks,
  };
}

async function slackApi(
  token: string,
  method: string,
  body: Record<string, unknown>,
): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(`https://slack.com/api/${method}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json; charset=utf-8",
    },
    body: JSON.stringify(body),
  });
  const j = (await res.json()) as { ok?: boolean; error?: string };
  return j.ok ? { ok: true } : { ok: false, error: j.error || `${method} failed` };
}

async function openReplyModal(opts: {
  token: string;
  triggerId: string;
  triageId: string;
  who: string;
  draft: string;
  inbound: string;
  to: string;
  account: string;
  channelId?: string;
  messageTs?: string;
}): Promise<{ ok: boolean; error?: string }> {
  const view = buildReplyView({
    meta: { id: opts.triageId, channel: opts.channelId, message_ts: opts.messageTs },
    who: opts.who,
    inbound: opts.inbound,
    state: { ...EMPTY_STATE, body: opts.draft, to: opts.to, account: opts.account },
    version: 1,
    materials: extractMaterialRequests(opts.inbound),
  });
  return slackApi(opts.token, "views.open", { trigger_id: opts.triggerId, view });
}

/** view.state から入力値を拾う（本文・指示ブロックは版付き block_id） */
export function extractMaModalState(payload: Record<string, unknown>): MaModalState {
  const view = (payload.view || {}) as Record<string, unknown>;
  const state = (view.state || {}) as Record<string, unknown>;
  const values = (state.values || {}) as Record<
    string,
    Record<string, Record<string, unknown>>
  >;
  const out: MaModalState = { ...EMPTY_STATE, files: [] };
  for (const [blockId, block] of Object.entries(values)) {
    for (const [actionId, el] of Object.entries(block || {})) {
      if (actionId === "mail_reply_body" && blockId.startsWith("mail_reply_body_block")) {
        out.body = String(el.value || "").trim();
      } else if (actionId === "mail_reply_instr") {
        out.instruction = String(el.value || "").trim();
      } else if (actionId === "mail_reply_to") {
        out.to = String(el.value || "").trim();
      } else if (actionId === "mail_reply_from") {
        const sel = (el.selected_option || {}) as Record<string, unknown>;
        out.account = String(sel.value || "").trim();
      } else if (actionId === "mail_reply_fquery") {
        out.fileQuery = String(el.value || "").trim();
      } else if (actionId === "mail_reply_files") {
        const sel = (el.selected_options || []) as Array<Record<string, unknown>>;
        out.files = sel.map((o) => String(o.value || "")).filter(Boolean);
      }
    }
  }
  return out;
}

export function extractMaModalBody(payload: Record<string, unknown>): string {
  return extractMaModalState(payload).body;
}

/** 現在の本文ブロック id（入力エラーの表示先） */
export function maBodyBlockId(payload: Record<string, unknown>): string {
  const view = (payload.view || {}) as Record<string, unknown>;
  const values = ((view.state || {}) as Record<string, unknown>).values || {};
  return (
    Object.keys(values as Record<string, unknown>).find((k) =>
      k.startsWith("mail_reply_body_block"),
    ) || "mail_reply_body_block_v1"
  );
}

/**
 * モーダル内の「誤字脱字チェック」「指示で見直し」。
 * Slack には 3 秒以内に応答が要るため、点検中表示だけ先に出して本処理は後で views.update する。
 */
export function isMaModalAction(actionId: string): boolean {
  return (
    actionId === MA_MODAL_ACTION_IDS.proofread ||
    actionId === MA_MODAL_ACTION_IDS.revise ||
    actionId === MA_MODAL_ACTION_IDS.findFiles
  );
}

type ModalCtx = {
  bot: string;
  viewId: string;
  meta: MaModalMeta;
  version: number;
  who: string;
  inbound: string;
  materials: string[];
  candidates: MaterialCandidate[];
  state: MaModalState;
};

async function loadModalCtx(
  payload: Record<string, unknown>,
): Promise<ModalCtx | { error: string }> {
  const bot = (process.env.SLACK_BOT_TOKEN || "").trim();
  if (!bot) return { error: "SLACK_BOT_TOKEN 未設定" };
  const view = (payload.view || {}) as Record<string, unknown>;
  const viewId = String(view.id || "");
  const metaRaw = String(view.private_metadata || "");
  const meta = parseMaModalMeta(metaRaw);
  if (!viewId || !meta) return { error: "モーダル情報が不正です" };
  const row = await fetchMailActionTriage(meta.id);
  if (!row) return { error: "対象のメール要対応が見つかりません" };
  const inbound = String(row.original_body || "");
  return {
    bot,
    viewId,
    meta,
    version: metaVersion(metaRaw),
    who: String(row.partner || row.from_email || "相手"),
    inbound,
    materials: extractMaterialRequests(inbound),
    candidates: metaCandidates(metaRaw),
    state: extractMaModalState(payload),
  };
}

function viewFrom(
  ctx: ModalCtx,
  patch: Partial<ReplyViewInput> & { version: number },
) {
  return buildReplyView({
    meta: ctx.meta,
    who: ctx.who,
    inbound: ctx.inbound,
    state: ctx.state,
    materials: ctx.materials,
    candidates: ctx.candidates,
    ...patch,
  });
}

export async function handleMaModalAction(opts: {
  actionId: string;
  payload: Record<string, unknown>;
}): Promise<{ run: () => Promise<void> } | { error: string }> {
  const ctx = await loadModalCtx(opts.payload);
  if ("error" in ctx) return ctx;
  const { bot, viewId, state, version } = ctx;
  const update = (view: Record<string, unknown>) =>
    slackApi(bot, "views.update", { view_id: viewId, view });

  if (opts.actionId === MA_MODAL_ACTION_IDS.findFiles) {
    const terms = searchTermsFromItems(state.fileQuery ? [] : ctx.materials, state.fileQuery);
    if (!terms.length) {
      // 検索語欄を出して入力を促す
      await update(
        viewFrom(ctx, {
          version: version + 1,
          showFileQuery: true,
          notice: "⚠️ 依頼品目が見つかりませんでした。資料の検索語を入れて、もう一度「📎 資料を探す」",
        }),
      );
      return { run: async () => {} };
    }
    const busyVersion = version + 1;
    await update(
      viewFrom(ctx, { version: busyVersion, busy: true, notice: `⏳ 資料を探しています（${terms.join("・")}）…` }),
    );
    return {
      run: async () => {
        const found = await searchMaterialFiles(terms);
        // 既に選んだものは残し、新しい候補を後ろに足す（最大10件）
        const kept = ctx.candidates.filter((c) => state.files.includes(candidateValue(c)));
        const merged = [...kept];
        for (const c of found.candidates) {
          if (merged.length >= 10) break;
          if (!merged.some((m) => m.s === c.s && m.id === c.id)) merged.push(c);
        }
        let notice = merged.length
          ? `📎 候補 ${found.candidates.length} 件（検索語: ${terms.join("・")}）。添付するものにチェックして「送信」`
          : `📎 見つかりませんでした（検索語: ${terms.join("・")}）。検索語を変えてもう一度どうぞ`;
        if (found.notes.length) notice += `\n${found.notes.map((n) => `⚠️ ${n}`).join("\n")}`;
        await update(
          viewFrom(ctx, {
            version: busyVersion + 1,
            candidates: merged,
            state: { ...state, fileQuery: state.fileQuery || terms.join(" ") },
            notice,
          }),
        );
      },
    };
  }

  const mode = opts.actionId === MA_MODAL_ACTION_IDS.proofread ? "proofread" : "revise";

  if (mode === "revise" && !state.instruction) {
    await update(
      viewFrom(ctx, {
        version: version + 1,
        notice: "⚠️ 見直し指示を入力してから「指示で見直し」を押してください",
      }),
    );
    return { run: async () => {} };
  }

  const busyVersion = version + 1;
  await update(
    viewFrom(ctx, {
      version: busyVersion,
      busy: true,
      notice: mode === "proofread" ? "⏳ 誤字脱字をチェック中…" : "⏳ 指示どおり見直し中…",
    }),
  );

  return {
    run: async () => {
      const result =
        mode === "proofread"
          ? await proofreadDraft(state.body)
          : await reviseDraft(state.body, state.instruction);
      let notice: string;
      let next = state;
      if (!result.ok) {
        notice = `❌ ${mode === "proofread" ? "誤字脱字チェック" : "見直し"}に失敗しました: ${result.error}（本文はそのままです）`;
      } else {
        next = { ...state, body: result.text, instruction: mode === "revise" ? "" : state.instruction };
        const label = mode === "proofread" ? "✅ 誤字脱字チェック済み" : "✅ 見直し済み";
        notice = result.changes.length
          ? `${label}（${result.changes.length}件）\n` +
            result.changes.map((c) => `• ${c}`).join("\n")
          : `${label} — ${mode === "proofread" ? "直す箇所はありませんでした" : "本文を更新しました"}`;
        notice += "\n内容を確認して、必要なら直接直してから「送信」";
      }
      await update(viewFrom(ctx, { version: busyVersion + 1, state: next, notice }));
    },
  };
}

/** 選んだ添付（od:/gd: 値）を参照に直す */
export function maSelectedFiles(state: { files: string[] }) {
  return state.files
    .map(parseCandidateValue)
    .filter((x): x is NonNullable<ReturnType<typeof parseCandidateValue>> => Boolean(x));
}

/**
 * 添付ありの送信。ファイル取得に時間がかかるので、すぐ「送信中」に切り替えて後で送る。
 * 失敗したら入力内容を保ったままフォームに戻す。
 */
export async function prepareMaModalSubmitWithFiles(
  payload: Record<string, unknown>,
): Promise<{ view: Record<string, unknown>; run: () => Promise<void> } | { error: string }> {
  const ctx = await loadModalCtx(payload);
  if ("error" in ctx) return ctx;
  const refs = maSelectedFiles(ctx.state);
  const names = ctx.candidates
    .filter((c) => ctx.state.files.includes(candidateValue(c)))
    .map((c) => `• ${c.n}`);
  const sendingView = {
    type: "modal",
    callback_id: `${MA_MODAL_CALLBACK}_sending`,
    title: { type: "plain_text", text: "メール返信" },
    close: { type: "plain_text", text: "閉じる" },
    blocks: [
      {
        type: "section",
        text: {
          type: "mrkdwn",
          text: `⏳ 添付 ${refs.length} 件を付けて送信しています…\n${names.join("\n")}`.slice(0, 2900),
        },
      },
    ],
  };
  return {
    view: sendingView,
    run: async () => {
      const result = await handleMaModalSubmit({
        triageId: ctx.meta.id,
        body: ctx.state.body,
        to: ctx.state.to,
        account: ctx.state.account,
        attachments: refs,
        channelId: ctx.meta.channel,
        messageTs: ctx.meta.message_ts,
      });
      const view = result.ok
        ? {
            type: "modal",
            callback_id: `${MA_MODAL_CALLBACK}_done`,
            title: { type: "plain_text", text: "メール返信" },
            close: { type: "plain_text", text: "閉じる" },
            blocks: maDoneBlocks("返信を送信しました", result.text, true),
          }
        : viewFrom(ctx, {
            version: ctx.version + 1,
            notice: `❌ 送信できませんでした: ${result.text}`,
          });
      await slackApi(ctx.bot, "views.update", { view_id: ctx.viewId, view });
    },
  };
}

export async function handleMaModalSubmit(opts: {
  triageId: string;
  body: string;
  to?: string;
  account?: string;
  attachments?: Array<{ s: "od" | "gd"; id: string }>;
  /** エラー表示先の本文ブロック（版付き） */
  bodyBlockId?: string;
  channelId?: string;
  messageTs?: string;
}): Promise<{
  ok: boolean;
  text: string;
  errors?: Record<string, string>;
}> {
  if (!opts.body.trim()) {
    return {
      ok: false,
      text: "本文が空です",
      errors: { [opts.bodyBlockId || "mail_reply_body_block_v1"]: "返信本文を入力してください" },
    };
  }
  const result = await applyMailActionSlack(opts.triageId, "reply", {
    body: opts.body,
    to: opts.to,
    account: opts.account,
    attachments: opts.attachments,
    source: "slack_modal",
  });
  if (!result.ok) {
    const onTo = /宛先/.test(result.message);
    return {
      ok: false,
      text: result.message,
      errors: onTo
        ? { mail_reply_to_block: result.message.slice(0, 100) }
        : { [opts.bodyBlockId || "mail_reply_body_block_v1"]: result.message.slice(0, 100) },
    };
  }
  const bot = (process.env.SLACK_BOT_TOKEN || "").trim();
  if (bot && opts.channelId && opts.messageTs) {
    await fetch("https://slack.com/api/chat.update", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${bot}`,
        "Content-Type": "application/json; charset=utf-8",
      },
      body: JSON.stringify({
        channel: opts.channelId,
        ts: opts.messageTs,
        text: `✅ ${result.message}`,
        blocks: maDoneBlocks("返信を送信しました", result.message, true),
      }),
    });
  }
  return { ok: true, text: result.message };
}

export async function handleMaBlockAction(opts: {
  action: MailActionSlackAction;
  triageId: string;
  triggerId?: string;
  channelId?: string;
  messageTs?: string;
}): Promise<{
  kind: "replace" | "delete" | "ephemeral" | "modal_opened" | "error";
  text: string;
  blocks?: ReturnType<typeof maDoneBlocks>;
  slack_deleted?: boolean;
}> {
  const { action, triageId, triggerId, channelId, messageTs } = opts;

  if (action === "reply") {
    const row = await fetchMailActionTriage(triageId);
    if (!row) {
      return { kind: "error", text: "対象のメール要対応が見つかりません" };
    }
    const bot = (process.env.SLACK_BOT_TOKEN || "").trim();
    if (bot && triggerId) {
      const opened = await openReplyModal({
        token: bot,
        triggerId,
        triageId,
        who: String(row.partner || row.from_email || "相手"),
        draft: String(row.draft_text || ""),
        inbound: String(row.original_body || ""),
        to: guessMailReplyTo(row),
        account: normalizeMailAccount(row.account) || "estate",
        channelId,
        messageTs,
      });
      if (opened.ok) {
        return { kind: "modal_opened", text: "返信モーダルを開きました" };
      }
      return {
        kind: "ephemeral",
        text: `モーダルを開けませんでした（${opened.error}）。編集ページ: ${maActionUrl(triageId, "reply")}`,
      };
    }
    return {
      kind: "ephemeral",
      text: `返信ページを開いてください: ${maActionUrl(triageId, "reply")}`,
    };
  }

  const result = await applyMailActionSlack(triageId, action, {
    source: "slack_block_actions",
  });

  // 見送り成功 → カードをチャットから削除（残す必要なし）
  if (action === "skip" && result.ok) {
    const deletedNow = await deleteSlackMaMessage({
      channel: channelId,
      ts: messageTs,
    });
    return {
      kind: "delete",
      text: result.message,
      slack_deleted: deletedNow || result.slack_deleted,
    };
  }

  const title =
    action === "done"
      ? result.ok
        ? "返信済み"
        : "返信済みの記録に失敗"
      : result.ok
        ? "Todoist 登録"
        : "Todoist 登録失敗";
  return {
    kind: result.ok ? "replace" : "error",
    text: result.message,
    blocks: maDoneBlocks(title, result.message, result.ok),
  };
}
