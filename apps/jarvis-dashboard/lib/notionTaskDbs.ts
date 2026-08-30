/** Notion 看板マッピング（正本の写し: config/notion_task_dbs.yaml） */
export type NotionLaneConfig = {
  title: string;
  database_id: string;
  data_source_id?: string;
  board_url: string;
  title_prop: string;
  status_prop: string;
  due_prop: string | null;
  start_prop: string | null;
  /** 所有物件のサブグループ（select）。例: 物件名 */
  property_prop: string | null;
  initial_status: string;
  open_statuses: string[];
  done_statuses: string[];
  /** true なら看板に完了列を出さない */
  hide_done_on_board?: boolean;
};

export const NOTION_TASK_LANES: Record<string, NotionLaneConfig> = {
  properties: {
    title: "所有物件",
    database_id: "25ef6bbe-5a76-80ad-bdd1-e5c378572cac",
    data_source_id: "25ef6bbe-5a76-80bb-92ea-000b6bf56668",
    board_url:
      "https://app.notion.com/p/25ef6bbe5a7680adbdd1e5c378572cac?v=25ef6bbe5a768040870d000c89e6f889",
    title_prop: "プロジェクト名",
    status_prop: "ステータス",
    due_prop: "終了日",
    start_prop: "開始日",
    property_prop: "物件名",
    initial_status: "未着手",
    open_statuses: ["未着手", "メンバー_進行中", "オーナー_進行中"],
    done_statuses: ["完了(アーカイブ)", "完了(オーナー確認)"],
    hide_done_on_board: true,
  },
  ai_raimo: {
    title: "AI・Raimo",
    database_id: "394f6bbe-5a76-800d-9cef-c97abea7941e",
    data_source_id: "394f6bbe-5a76-8044-b42c-000be7ee6bde",
    board_url:
      "https://app.notion.com/p/394f6bbe5a76800d9cefc97abea7941e?v=394f6bbe5a7680ac9e6f000cb554aa73",
    title_prop: "名前",
    status_prop: "ステータス",
    due_prop: null,
    start_prop: null,
    property_prop: null,
    initial_status: "未着手",
    open_statuses: ["未着手", "エージェント待ち", "進行中"],
    done_statuses: ["完了"],
    hide_done_on_board: true,
  },
  kodate: {
    title: "戸建て",
    database_id: "656aa175-2371-4b14-a704-3aa965b2619a",
    data_source_id: "07abf776-6863-4d10-820a-e62e1b2afc62",
    board_url: "https://app.notion.com/p/656aa17523714b14a7043aa965b2619a",
    title_prop: "プロジェクト名",
    status_prop: "ステータス",
    due_prop: "終了日",
    start_prop: "開始日",
    property_prop: null,
    initial_status: "未着手",
    open_statuses: ["未着手", "進行中"],
    done_statuses: ["完了"],
    hide_done_on_board: false,
  },
  kamiooya: {
    title: "神大家運営",
    database_id: "03628f50-047d-4308-8c3a-6cb763ceecca",
    data_source_id: "b95b5bd1-256a-4e87-9269-430f8ce098ae",
    board_url: "https://app.notion.com/p/03628f50047d43088c3a6cb763ceecca",
    title_prop: "プロジェクト名",
    status_prop: "ステータス",
    due_prop: "終了日",
    start_prop: "開始日",
    property_prop: null,
    initial_status: "未着手",
    open_statuses: ["未着手", "進行中"],
    done_statuses: ["完了"],
    hide_done_on_board: false,
  },
  kazoku: {
    title: "家族",
    database_id: "9a5b4921-5835-49f8-b8c4-22e8caf8621a",
    data_source_id: "017c5f6b-61c0-4f63-871c-2072e15014e5",
    board_url: "https://app.notion.com/p/9a5b4921583549f8b8c422e8caf8621a",
    title_prop: "プロジェクト名",
    status_prop: "ステータス",
    due_prop: "終了日",
    start_prop: "開始日",
    property_prop: null,
    initial_status: "未着手",
    open_statuses: ["未着手", "進行中"],
    done_statuses: ["完了"],
    hide_done_on_board: false,
  },
};

/** カードタイトル等から物件名 select を推定するヒント */
export const PROPERTY_NAME_HINTS: { match: RegExp; prefer: string }[] = [
  { match: /Grandole\s*[ⅡI2]|志賀本通\s*[ⅡI2]|GrandoleⅡ/i, prefer: "01_Grandole志賀本通II" },
  { match: /Grandole\s*[ⅠI1]|志賀本通\s*[ⅠI1]|GrandoleⅠ/i, prefer: "01_Grandole志賀本通I" },
  { match: /LEAF/i, prefer: "LEAF" },
  { match: /ミニテック|ミニミニ/i, prefer: "ミニテック" },
  { match: /Tcell|T-cell|キャラメル/i, prefer: "Tcell" },
  { match: /ホームプランナー|HP/i, prefer: "ホームプランナー" },
];

export function guessPropertyName(
  haystack: string,
  options: string[],
): string {
  const hay = haystack || "";
  for (const hint of PROPERTY_NAME_HINTS) {
    if (!hint.match.test(hay)) continue;
    const found = options.find(
      (o) =>
        o === hint.prefer ||
        o.includes(hint.prefer) ||
        hint.prefer.includes(o),
    );
    if (found) return found;
    if (!options.length) return hint.prefer;
  }
  for (const o of options) {
    if (o && hay.includes(o)) return o;
  }
  return options[0] || "";
}
