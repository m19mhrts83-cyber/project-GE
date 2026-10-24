/**
 * S9 Slack インタラクション（採用／見送り）
 *
 * 押した瞬間: 元メッセージの該当ボタンを「✅ 社名 を採用（台帳へ反映中）」へ置換。
 * 全社を判断し終えたらメッセージ全体を結果一覧に差し替える。
 * iPhone では `replace_original` でその場が更新される（画面遷移なし）。
 */
import {
  applyS9Action,
  parseS9ButtonValue,
  S9_DECISION_ICON,
  S9_DECISION_LABEL,
  type S9Decision,
} from "@/lib/s9SlackAction";

type SlackBlock = {
  type?: string;
  block_id?: string;
  elements?: Array<Record<string, unknown>>;
  text?: Record<string, unknown>;
  [key: string]: unknown;
};

function blockId(block: SlackBlock): string {
  return String(block.block_id || "");
}

function candidateBlockIds(blocks: SlackBlock[]): number[] {
  const out: number[] = [];
  for (const b of blocks) {
    const m = blockId(b).match(/^s9_c_(\d+)$/);
    if (m) out.push(Number(m[1]));
  }
  return out;
}

export function rewriteAfterDecision(opts: {
  blocks: SlackBlock[];
  n: number;
  decision: S9Decision;
  name: string;
  channelId?: string;
  messageTs?: string;
}): { blocks: SlackBlock[]; text: string; remaining: number } {
  const { n, decision, name } = opts;
  const icon = S9_DECISION_ICON[decision];
  const label = S9_DECISION_LABEL[decision];
  const before = candidateBlockIds(opts.blocks).length;
  const next: SlackBlock[] = [];

  for (const raw of opts.blocks) {
    const b = { ...raw } as SlackBlock;
    if (blockId(b) === `s9_c_${n}`) {
      next.push({
        type: "context",
        block_id: `s9_done_${n}`,
        elements: [
          {
            type: "mrkdwn",
            text: `${icon} *${name}* を${label}（台帳へ反映中…）`,
          },
        ],
      });
      continue;
    }
    if (blockId(b) === "s9_footer") {
      continue; // 末尾で作り直す
    }
    next.push(b);
  }

  const remaining = candidateBlockIds(next).length;
  if (remaining > 0) {
    next.push({
      type: "context",
      block_id: "s9_footer",
      elements: [
        {
          type: "mrkdwn",
          text: `残り${remaining}件 · 押した結果はこのメッセージに残ります`,
        },
      ],
    });
    return {
      blocks: next,
      text: `S9 候補: ${name} を${label}しました（残り${remaining}件）`,
      remaining,
    };
  }

  // 全社判断済み → カードを結果一覧に畳む
  const done: string[] = [];
  for (const b of next) {
    if (blockId(b).startsWith("s9_done_")) {
      const el = (b.elements || [])[0] || {};
      const t = String((el as Record<string, unknown>).text || "");
      if (t) done.push(t.replace(/（台帳へ反映中…）/g, ""));
    }
  }
  const summary: SlackBlock[] = [
    {
      type: "header",
      text: {
        type: "plain_text",
        text: "【完了】S9 管理会社・候補の判断",
      },
    },
    { type: "divider" },
    {
      type: "section",
      text: {
        type: "mrkdwn",
        text: done.join("\n") || `${icon} ${name} を${label}`,
      },
    },
    {
      type: "context",
      elements: [
        {
          type: "mrkdwn",
          text: `全${before}社の判断が終わりました · 台帳へは数秒で反映`,
        },
      ],
    },
  ];
  return {
    blocks: summary,
    text: `【完了】S9 候補 ${before}社の判断`,
    remaining: 0,
  };
}

export type S9BlockActionResult =
  | { kind: "updated"; text: string; blocks: SlackBlock[]; jobId?: string }
  | { kind: "error"; text: string };

export async function handleS9BlockAction(opts: {
  value: string;
  blocks: SlackBlock[];
  channelId?: string;
  messageTs?: string;
  userId?: string;
}): Promise<S9BlockActionResult | null> {
  const parsed = parseS9ButtonValue(opts.value);
  if (!parsed) return null;
  const { decision, candidate } = parsed;

  const res = await applyS9Action({
    decision,
    candidate,
    source: "slack_button",
    channelId: opts.channelId,
    messageTs: opts.messageTs,
    userId: opts.userId,
  });
  if (!res.ok) {
    return { kind: "error", text: `❌ ${res.message}` };
  }

  const rewritten = rewriteAfterDecision({
    blocks: opts.blocks,
    n: candidate.n,
    decision,
    name: candidate.name,
    channelId: opts.channelId,
    messageTs: opts.messageTs,
  });
  return {
    kind: "updated",
    text: rewritten.text,
    blocks: rewritten.blocks,
    jobId: res.jobId,
  };
}
