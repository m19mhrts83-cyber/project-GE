/** グルコン活動／成果報告の Gemini プロンプト */

import type {
  GluconActiveCycle,
  GluconCarryMemo,
  GluconClarifyItem,
  GluconExample,
  GluconFactItem,
  GluconJournalDay,
  GluconMemberHeaderStatus,
} from "./types";

export type { GluconMemberHeaderStatus };

export function getMemberHeaderStatus(): GluconMemberHeaderStatus {
  const id = (process.env.KAMIOOYA_MEMBER_ID || "").trim();
  const name = (process.env.PERSONAL_NAME || "").trim();
  const missing: string[] = [];
  if (!id) missing.push("KAMIOOYA_MEMBER_ID");
  if (!name) missing.push("PERSONAL_NAME");
  let preview = "会員番号：（未設定）";
  if (id && name) preview = `会員番号：${id} ${name}`;
  else if (id) preview = `会員番号：${id}`;
  else if (name) preview = name;
  return { ok: missing.length === 0, missing, preview };
}

function memberHeader(): string {
  return getMemberHeaderStatus().preview;
}

const RESULT_CANDIDATE_TAGS =
  "購入AP／戸建・空室・修繕・売却・融資・業者・情報・幹事";

export function injectableCarryMemos(
  memos: GluconCarryMemo[],
  periodKey: string,
): GluconCarryMemo[] {
  return memos.filter(
    (m) =>
      m.status === "open" && m.available_from_period_key <= periodKey,
  );
}

/** 下書き生成に渡す次月メモブロック。未実施を成果として断定しない */
export function carryMemoPromptBlock(
  memos: GluconCarryMemo[],
  kind: "activity" | "result",
): string {
  if (!memos.length) return "";
  const lines = memos
    .map((m) => `- [${m.kind_hint}] ${m.title}\n  ${m.body.trim()}`)
    .join("\n");
  if (kind === "activity") {
    return `
【次月から回したメモ（今月やる／宣言に含めてよい）】
- 進行中・予定なら今月の活動や来月の宣言に書いてよい。
- 未実施なら成果として書かない。
${lines}
`;
  }
  return `
【次月から回した報告候補メモ】
- Journal／今月の動きに無くても候補にしてよい。
- 共有・見直しが完了したと断定しない。未実施なら成果本文に入れない。
- facts に載せるなら source に「carry_memo（未実施の可能性）」と書き、完了が確認できないなら forResult=false。
${lines}
`;
}

/** Step1: 事実のみ（推測禁止）。JSON で返す */
export function resultFactsPrompt(args: {
  cycle: GluconActiveCycle;
  journals: GluconJournalDay[];
  monthlyMovesBlock?: string;
  earlyFillBlock?: string;
  rubricSummary?: string;
  carryMemoBlock?: string;
  grokMaterialsBlock?: string;
}): string {
  const moves = args.monthlyMovesBlock?.trim()
    ? `\n${args.monthlyMovesBlock.trim()}\n`
    : "";
  const early = args.earlyFillBlock?.trim()
    ? `\n${args.earlyFillBlock.trim()}\n`
    : "";
  const rubric = args.rubricSummary?.trim()
    ? `\n【scoring 観点（タグ付け用。点数は書かない）】\n${args.rubricSummary.trim()}\n`
    : "";
  const carry = args.carryMemoBlock?.trim()
    ? `\n${args.carryMemoBlock.trim()}\n`
    : "";
  const grok = args.grokMaterialsBlock?.trim()
    ? `\n${args.grokMaterialsBlock.trim()}\n`
    : "";

  return `あなたは神・大家さん倶楽部の成果報告向け「事実抽出」アシスタントです。

【厳守】
- 推測・解釈・感情・「たぶん」は禁止。データに明示された事実だけを書く。
- Journal／今月の動き／早期入居／Grok材料に無いことは出さない。ただし【次月から回した報告候補メモ】は候補として出してよい（完了を断定しない）。
- 会社人事・家庭雑談は除外。神大家・不動産・融資・物件・空室・修繕・AI推進（神大家関連）のみ。
- 出力は JSON のみ（前後の説明文・マークダウン禁止）。

【神・大家さんポイント方針】
- ポイントが貯まるのは成果報告のみ。塾生に共有すべき実践成果は forResult=true にする。
- 候補タグは次から選ぶ（該当しなければ null）: ${RESULT_CANDIDATE_TAGS}
- 空室の早期入居付け（退去から短い日数で入居）は立派な成果候補。

【出力 JSON スキーマ】
{
  "facts": [
    {
      "id": "f1",
      "text": "事実1文",
      "source": "Journal 2026-07-12 / occupancy / yoritoori 等",
      "resultCandidateTag": "空室" | null,
      "forResult": true
    }
  ],
  "factsBody": "事実だけを箇条書きにした短い下書き（推測なし・見出し可）"
}

【提出期限】${args.cycle.reportDeadline}
【Journal 期間】${args.cycle.journalFrom} 〜 ${args.cycle.journalTo}
【会員】${memberHeader()}
${rubric}
【ジャーナル抜粋】
${JSON.stringify(
    args.journals.map((j) => ({
      date: j.recorded_at,
      keywords: j.keywords,
      excerpt: j.excerpt,
    })),
    null,
    2,
  )}
${moves}${early}${carry}${grok}`;
}

/** Step2: 確認質問の生成 */
export function resultClarifyPrompt(args: {
  cycle: GluconActiveCycle;
  facts: GluconFactItem[];
  factsBody: string;
}): string {
  return `あなたは神・大家さん倶楽部の成果報告向け「確認質問」アシスタントです。

【目的】
最終稿に必要な不足情報（苦労・工夫・入会前の状態・数字の裏付け・成果として書けるか）を、3〜5問で聞く。

【厳守】
- 事実に無いことを前提にした質問はしない。
- 出力は JSON のみ。

【出力】
{
  "questions": [
    { "id": "q1", "question": "質問文" }
  ]
}

【期間】${args.cycle.journalFrom} 〜 ${args.cycle.journalTo}
【事実リスト】
${JSON.stringify(args.facts, null, 2)}

【事実下書き】
${args.factsBody}`;
}

/** Step3: 型テンプレ＋Before/After＋回答を織り込んだ最終稿 */
export function resultPrompt(args: {
  cycle: GluconActiveCycle;
  journals: GluconJournalDay[];
  examples: GluconExample[];
  rubricSummary?: string;
  monthlyMovesBlock?: string;
  facts?: GluconFactItem[];
  factsBody?: string;
  clarify?: GluconClarifyItem[];
  earlyFillBlock?: string;
  carryMemoBlock?: string;
}): string {
  const rubricBlock = args.rubricSummary?.trim()
    ? `
【神大家ポイント観点（採点者が見る軸。投稿本文に点数・ルールIDは書かない）】
${args.rubricSummary.trim()}
`
    : "";

  const moves = args.monthlyMovesBlock?.trim()
    ? `\n${args.monthlyMovesBlock.trim()}\n`
    : "";
  const early = args.earlyFillBlock?.trim()
    ? `\n${args.earlyFillBlock.trim()}\n`
    : "";
  const carry = args.carryMemoBlock?.trim()
    ? `\n${args.carryMemoBlock.trim()}\n`
    : "";

  const factsBlock =
    args.facts?.length || args.factsBody?.trim()
      ? `
【確定した事実（これ以外の成果・金額を捏造しない）】
${args.factsBody?.trim() || ""}
${JSON.stringify(args.facts || [], null, 2)}
`
      : "";

  const clarifyBlock =
    args.clarify && args.clarify.some((c) => c.answer.trim())
      ? `
【ユーザー回答（苦労・工夫・入会前後など。未回答の観点は書かない）】
${JSON.stringify(
        args.clarify.filter((c) => c.answer.trim()),
        null,
        2,
      )}
`
      : "";

  return `あなたは神・大家さん倶楽部の塾生向け「成果報告」の下書きライターです。

【厳守】
- 物件購入・融資実行・空室解消・賃料アップ・修繕コスト削減・管理改善など「実践して成果が出た」ことだけを書く。
- ジャーナル／今月の動き／確定事実に明確な成果が無い場合は、本文を次の1行だけにする:
  （今月は該当する成果報告なし）
- 事実にない成果・金額を捏造しない。会社業務の成果は書かない。
- 投稿本文に「〇点」「ルールID」は書かない。
- 出力は投稿本文のみ。
${rubricBlock}
【必須の型（成果があるとき・コミュニティ実例に合わせる）】
■【カテゴリの成果報告】（空室／修繕／融資／購入AP など）
${memberHeader()}
・項目行（分かる範囲で）: エリア／物件／号室／対策前／対策後／実施内容 1. 2. 3.／金額・日数など
・再現できる手順と数字を書く
所感等：
・学びと次の一手
■Before(入会前)：
・入会前の状態・悩み（ユーザー回答または事実から。無い場合は短い所感のみ）
■After(入会後)：
・入会後に得られた変化・学び（同上）

※ 空室の早期入居付けは立派な成果。退去→入居の日数があれば必ず書く。
※ Before/After は毎月必ず入れる（回答が無い場合も、事実から書ける範囲の短い所感で可。捏造は禁止）。

【提出期限】${args.cycle.reportDeadline}
【Journal 期間】${args.cycle.journalFrom} 〜 ${args.cycle.journalTo}

【参考例（文体のみ。内容はコピーしない）】
${JSON.stringify(args.examples, null, 2)}
${factsBlock}${clarifyBlock}
【ジャーナル抜粋】
${JSON.stringify(
    args.journals.map((j) => ({
      date: j.recorded_at,
      keywords: j.keywords,
      excerpt: j.excerpt,
    })),
    null,
    2,
  )}
${moves}${early}${carry}`;
}

export function activityPrompt(args: {
  cycle: GluconActiveCycle;
  journals: GluconJournalDay[];
  examples: GluconExample[];
  /** メール・metrics・入退去の月次集約テキスト（任意） */
  monthlyMovesBlock?: string;
  /** 成果報告側に採用した事実（大きな区切り。詳細は成果へ） */
  resultExcludedFacts?: string[];
  carryMemoBlock?: string;
  /** Grok Drive 材料 */
  grokMaterialsBlock?: string;
  /** 前回投稿本文（再掲禁止） */
  previousPostedBody?: string | null;
  /** 今回書く進展の期間 */
  progressFrom?: string | null;
  progressTo?: string | null;
}): string {
  const monthLabel = args.cycle.periodKey.replace("-", "年") + "月";
  const nextMonth = (() => {
    const [y, m] = args.cycle.periodKey.split("-").map(Number);
    const nm = m === 12 ? 1 : m + 1;
    const ny = m === 12 ? y + 1 : y;
    return `${ny}年${nm}月`;
  })();

  const moves = args.monthlyMovesBlock?.trim()
    ? `\n${args.monthlyMovesBlock.trim()}\n`
    : "";
  const carry = args.carryMemoBlock?.trim()
    ? `\n${args.carryMemoBlock.trim()}\n`
    : "";
  const grok = args.grokMaterialsBlock?.trim()
    ? `\n${args.grokMaterialsBlock.trim()}\n`
    : "";

  const exclude =
    args.resultExcludedFacts && args.resultExcludedFacts.length
      ? `
【大きな成果の扱い】
- 購入完了・満室化などの大きな区切りは、活動では1行触れる程度。詳細は成果報告パネルへ。
${args.resultExcludedFacts.map((t) => `- ${t}`).join("\n")}
`
      : "";

  const previous = args.previousPostedBody?.trim()
    ? `
【前回投稿済み（再掲禁止。同じ事実を繰り返さない）】
${args.previousPostedBody.trim()}
`
    : "";

  const progressLabel =
    args.progressFrom && args.progressTo
      ? `${args.progressFrom} 〜 ${args.progressTo}`
      : `${args.cycle.journalFrom} 〜 ${args.cycle.journalTo}`;

  return `あなたは神・大家さん倶楽部の塾生向け「月次活動報告」の下書きライターです。

【厳守】
- 会社の人員計画・社内DX・家庭の雑談など、神大家・不動産投資・融資・物件・空室・修繕・コミュニティ学習・AI推進（神大家関連）以外は書かない。
- 事実のない成果を捏造しない。ジャーナル／今月の動き／Grok材料に無いことは「宣言」側の予定としてだけ書いてよい。
- 定常の本線は活動報告。前回投稿以降の進展だけを書く。
- Grok Bot の活躍（組織整備・調査・ルーティン等）も神大家関連なら活動に含めてよい。
- 出力は投稿本文のみ（前置き・説明・マークダウン見出しの#は不要）。
${exclude}${previous}
【形式】コミュニティの定型に合わせる:
■1■今月の活動報告（${monthLabel}度）
・箇条書き（3〜8行）
■2■来月の宣言（${nextMonth}）
・箇条書き（3〜6行）
末尾に短い挨拶1行可。

【提出期限】${args.cycle.reportDeadline}（グルコン ${args.cycle.gluconDate} の10日前）
【今回書く進展の期間】${progressLabel}
【Journal 期間】${args.cycle.journalFrom} 〜 ${args.cycle.journalTo}
【会員】${memberHeader()}

【参考例（文体のみ。内容はコピーしない）】
${JSON.stringify(args.examples, null, 2)}

【ジャーナル抜粋（神大家関連）】
${JSON.stringify(
    args.journals.map((j) => ({
      date: j.recorded_at,
      keywords: j.keywords,
      excerpt: j.excerpt,
    })),
    null,
    2,
  )}
${moves}${carry}${grok}`;
}

/** 聞く／直すパネル用 */
export function consultAskPrompt(args: {
  body: string;
  question: string;
  kind: "activity" | "result";
}): string {
  return `あなたは神・大家さん倶楽部の${
    args.kind === "result" ? "成果" : "活動"
  }報告の相談相手です。

【厳守】
- 本文の事実を増やして捏造しない。質問に短く答える。
- 出力は回答本文のみ。

【現在の本文】
${args.body}

【質問】
${args.question}`;
}

export function consultRevisePrompt(args: {
  body: string;
  instruction: string;
  kind: "activity" | "result";
}): string {
  return `あなたは神・大家さん倶楽部の${
    args.kind === "result" ? "成果" : "活動"
  }報告の編集アシスタントです。

【厳守】
- 指示に沿って本文を書き直す。事実の捏造は禁止。
- 成果報告の場合、型（■【カテゴリ】・所感等・■Before(入会前)／■After(入会後)）を崩さない。
- 出力は修正後の投稿本文のみ。

【現在の本文】
${args.body}

【修正指示】
${args.instruction}`;
}
