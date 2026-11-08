/**
 * メール要対応の判断ログ（owner_decisions）まわりの、外部に依存しない部品。
 * - 見送り後の理由タグ（押さなくても進める）
 * - 「同じ送り手の見送りが2回目です。次からも？」の確認
 * - 「✓ 判断ログに記録（今週N件）」の表示
 * - 送った文が下書きからどれだけ変わったか
 *
 * 迷って見送ったものは NG（skipped）に混ぜず hesitated として残す。
 */

export const MA_REASON_TAGS = {
  promo: "宣伝・通知",
  handled: "対応済み",
  notnow: "今は不要",
  hesitate: "迷う",
} as const;

export type MaReasonTag = keyof typeof MA_REASON_TAGS;

/** once = 今回だけ（数え直す）／ partner = この送り手は次から出さない */
export type MaMuteChoice = "once" | "partner";

const ID_RE = "([a-zA-Z0-9_.:-]{6,80})";

/** value: mar:{tag}:{triage_id} */
export function maReasonValue(tag: MaReasonTag, id: string): string {
  return `mar:${tag}:${id}`;
}

export function parseMaReasonValue(value: string): { tag: MaReasonTag; id: string } | null {
  const m = String(value || "").trim().match(new RegExp(`^mar:(promo|handled|notnow|hesitate):${ID_RE}$`));
  if (!m) return null;
  return { tag: m[1] as MaReasonTag, id: m[2] };
}

/** value: mam:{once|partner}:{triage_id} */
export function maMuteValue(choice: MaMuteChoice, id: string): string {
  return `mam:${choice}:${id}`;
}

export function parseMaMuteValue(value: string): { choice: MaMuteChoice; id: string } | null {
  const m = String(value || "").trim().match(new RegExp(`^mam:(once|partner):${ID_RE}$`));
  if (!m) return null;
  return { choice: m[1] as MaMuteChoice, id: m[2] };
}

/** 週の始まり（月曜 0:00 JST）を UTC ISO で */
export function weekStartIso(now: Date = new Date()): string {
  const jstMs = now.getTime() + 9 * 3600_000;
  const jst = new Date(jstMs);
  const dow = (jst.getUTCDay() + 6) % 7; // 月=0
  const startJst = Date.UTC(jst.getUTCFullYear(), jst.getUTCMonth(), jst.getUTCDate() - dow);
  return new Date(startJst - 9 * 3600_000).toISOString();
}

export function loggedLine(weekCount: number | null): string {
  return weekCount && weekCount > 0
    ? `✓ 判断ログに記録（今週 ${weekCount} 件）`
    : "✓ 判断ログに記録";
}

/**
 * 下書きと送った文の違い（0 = そのまま、1 = 全部書き直し）。
 * 文字単位の編集距離を長い方の長さで割る。長文は先頭 2000 字で見る。
 */
export function editRatio(draft: string | null | undefined, sent: string | null | undefined): number | null {
  const a = String(draft || "").trim().slice(0, 2000);
  const b = String(sent || "").trim().slice(0, 2000);
  if (!a) return null;
  if (a === b) return 0;
  const n = a.length;
  const m = b.length;
  let prev = new Array<number>(m + 1);
  let cur = new Array<number>(m + 1);
  for (let j = 0; j <= m; j++) prev[j] = j;
  for (let i = 1; i <= n; i++) {
    cur[0] = i;
    const ca = a.charCodeAt(i - 1);
    for (let j = 1; j <= m; j++) {
      const cost = ca === b.charCodeAt(j - 1) ? 0 : 1;
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost);
    }
    [prev, cur] = [cur, prev];
  }
  return Math.round((prev[m] / Math.max(n, m)) * 100) / 100;
}

export function editLabel(ratio: number | null): string {
  if (ratio === null) return "下書きなし";
  if (ratio <= 0.05) return "ほぼそのまま";
  if (ratio <= 0.4) return "少し直した";
  return "書き直した";
}

type Block = Record<string, unknown>;

/**
 * 見送った直後のカード。カードは消さずに1行に縮め、理由タグを任意で出す。
 * tagged があれば理由の行だけにする。askMute があれば送り手の確認を足す。
 */
export function maSkipFollowupBlocks(opts: {
  id: string;
  who: string;
  weekCount: number | null;
  tagged?: MaReasonTag | null;
  askMute?: { skips: number } | null;
  muteDone?: MaMuteChoice | null;
}): Block[] {
  const who = (opts.who || "").slice(0, 60);
  const reason = opts.tagged ? ` · 理由: ${MA_REASON_TAGS[opts.tagged]}` : "";
  const head = opts.tagged === "hesitate" ? `🤔 迷ったので見送り（${who}）` : `⏭ 見送り（${who}）`;
  const blocks: Block[] = [
    {
      type: "context",
      elements: [{ type: "mrkdwn", text: `${head}${reason} · ${loggedLine(opts.weekCount)}` }],
    },
  ];
  if (!opts.tagged) {
    blocks.push({
      type: "actions",
      block_id: "ma_reason",
      elements: (Object.keys(MA_REASON_TAGS) as MaReasonTag[]).map((tag) => ({
        type: "button",
        text: { type: "plain_text", text: MA_REASON_TAGS[tag], emoji: true },
        action_id: `mail_action_reason_${tag}`,
        value: maReasonValue(tag, opts.id),
      })),
    });
    blocks.push({
      type: "context",
      elements: [{ type: "mrkdwn", text: "理由は？（押さなくても進めます。「迷う」は不要扱いにしません）" }],
    });
  }
  if (opts.muteDone) {
    blocks.push({
      type: "context",
      elements: [
        {
          type: "mrkdwn",
          text:
            opts.muteDone === "partner"
              ? "🔕 この送り手は次から出しません"
              : "↩︎ 今回だけにしました。次も出します",
        },
      ],
    });
  } else if (opts.askMute) {
    blocks.push({
      type: "section",
      text: {
        type: "mrkdwn",
        text: `この送り手の見送りは *${opts.askMute.skips} 回目* です。次からも出さないようにしますか？`,
      },
    });
    blocks.push({
      type: "actions",
      block_id: "ma_mute",
      elements: [
        {
          type: "button",
          text: { type: "plain_text", text: "今回だけ", emoji: true },
          action_id: "mail_action_mute_once",
          value: maMuteValue("once", opts.id),
        },
        {
          type: "button",
          text: { type: "plain_text", text: "この送り手は出さない", emoji: true },
          action_id: "mail_action_mute_partner",
          value: maMuteValue("partner", opts.id),
        },
      ],
    });
  }
  return blocks;
}
