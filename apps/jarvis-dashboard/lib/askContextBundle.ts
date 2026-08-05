/** タスク「聞く」用 ContextBundle（Server が根拠を集めて注入） */

import {
  retrieveKamiooyaForAsk,
  type KamiooyaHit,
} from "@/lib/kamiooya/retrieveForAsk";
import { defaultUseKamiooyaKnowledge } from "@/lib/kamiooya/lanes";
import {
  defaultUseOnedriveYoritoori,
  retrieveYoritooriForAsk,
} from "@/lib/onedrive/retrieveYoritoori";
import { retrieveNotebookLmForAsk } from "@/lib/gdrive/retrieveNotebookLmForAsk";

export type AskContextSources = {
  /** 運営 kamiooya-qa（読取のみ） */
  kamiooya?: boolean;
  /** OneDrive パートナー 5.やり取り.md（Graph） */
  onedriveYoritoori?: boolean;
  /** admin Google Drive `200_NoteBookLM`（Phase3） */
  gdrive?: boolean;
};

export type AskContextBundle = {
  sources: Required<AskContextSources>;
  notices: string[];
  /** エンジン（Cloud／Gemini）へ注入するブロック */
  promptBlock: string;
  /** ローカルハンドオフに同梱する同じ根拠 */
  handoffExtra: string;
  kamiooyaHits: KamiooyaHit[];
};

export function defaultAskContextSources(
  lane: string | null | undefined,
): Required<AskContextSources> {
  return {
    kamiooya: defaultUseKamiooyaKnowledge(lane),
    onedriveYoritoori: defaultUseOnedriveYoritoori(lane),
    /** 手動オン既定（誤爆・トークン消費を抑える） */
    gdrive: false,
  };
}

/**
 * カード／ウォッチ共通。失敗したソースは notice のみで全体は止めない。
 */
export async function buildAskContextBundle(opts: {
  lane?: string | null;
  title?: string | null;
  summary?: string | null;
  payload?: Record<string, unknown> | null;
  /** 検索クエリ（ユーザー質問＋タイトル等） */
  query: string;
  sources?: AskContextSources;
}): Promise<AskContextBundle> {
  const defaults = defaultAskContextSources(opts.lane);
  const sources: Required<AskContextSources> = {
    kamiooya: opts.sources?.kamiooya ?? defaults.kamiooya,
    onedriveYoritoori:
      opts.sources?.onedriveYoritoori ?? defaults.onedriveYoritoori,
    gdrive: opts.sources?.gdrive ?? defaults.gdrive,
  };

  const notices: string[] = [];
  const blocks: string[] = [];
  let kamiooyaHits: KamiooyaHit[] = [];

  if (sources.kamiooya) {
    const kr = await retrieveKamiooyaForAsk(opts.query);
    notices.push(kr.notice);
    if (kr.promptBlock) blocks.push(kr.promptBlock);
    kamiooyaHits = kr.hits;
  }

  if (sources.onedriveYoritoori) {
    const yr = await retrieveYoritooriForAsk({
      lane: opts.lane,
      title: opts.title,
      summary: opts.summary,
      payload: opts.payload,
    });
    notices.push(yr.notice);
    if (yr.promptBlock) blocks.push(yr.promptBlock);
  }

  if (sources.gdrive) {
    const gr = await retrieveNotebookLmForAsk(opts.query);
    notices.push(gr.notice);
    if (gr.promptBlock) blocks.push(gr.promptBlock);
  }

  const promptBlock = blocks.join("\n\n");
  return {
    sources,
    notices,
    promptBlock,
    handoffExtra: promptBlock,
    kamiooyaHits,
  };
}
