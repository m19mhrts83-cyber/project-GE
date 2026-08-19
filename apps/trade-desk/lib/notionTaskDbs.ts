/** KURASHIFT 向け Notion 看板（正本: config/notion_task_dbs.yaml） */

export type NotionLaneConfig = {
  title: string;
  database_id: string;
  board_url: string;
  title_prop: string;
  status_prop: string;
  due_prop: string | null;
  open_statuses: string[];
  done_statuses: string[];
};

export const KURASHIFT_NOTION_LANES: Record<string, NotionLaneConfig> = {
  properties: {
    title: "所有物件",
    database_id: "25ef6bbe-5a76-80ad-bdd1-e5c378572cac",
    board_url:
      "https://app.notion.com/p/25ef6bbe5a7680adbdd1e5c378572cac?v=25ef6bbe5a768040870d000c89e6f889",
    title_prop: "プロジェクト名",
    status_prop: "ステータス",
    due_prop: "終了日",
    open_statuses: ["未着手", "メンバー_進行中", "オーナー_進行中"],
    done_statuses: ["完了(アーカイブ)", "完了(オーナー確認)"],
  },
  kodate: {
    title: "戸建て",
    database_id: "656aa175-2371-4b14-a704-3aa965b2619a",
    board_url: "https://app.notion.com/p/656aa17523714b14a7043aa965b2619a",
    title_prop: "プロジェクト名",
    status_prop: "ステータス",
    due_prop: "終了日",
    open_statuses: ["未着手", "進行中"],
    done_statuses: ["完了"],
  },
  kazoku: {
    title: "家族",
    database_id: "9a5b4921-5835-49f8-b8c4-22e8caf8621a",
    board_url: "https://app.notion.com/p/9a5b4921583549f8b8c422e8caf8621a",
    title_prop: "プロジェクト名",
    status_prop: "ステータス",
    due_prop: "終了日",
    open_statuses: ["未着手", "進行中"],
    done_statuses: ["完了"],
  },
};
