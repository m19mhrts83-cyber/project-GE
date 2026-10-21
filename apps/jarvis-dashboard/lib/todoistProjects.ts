/** Todoist レーン写し（正本: config/todoist_projects.yaml） */

export type TodoistLaneConfig = {
  title: string;
  projectKey: string;
  projectId: string;
  laneLabel: string;
  boardUrl: string;
  initialSection: string;
  openSections: string[];
  doneSections: string[];
  hideDoneOnBoard?: boolean;
  /** work_bundle 同居時は lane_label でフィルタ */
  filterByLaneLabel: boolean;
  sectionIds: Record<string, string>;
};

/** Board列。完了列は使わない（チェック完了で閉じる）。HOLD=一時保留 */
const OPEN_SECTIONS = ["未着手", "進行中", "相手待ち", "HOLD", "オーナー確認"] as const;

export const TODOIST_TASK_LANES: Record<string, TodoistLaneConfig> = {
  properties: {
    title: "所有物件",
    projectKey: "properties",
    projectId: "6hXX2jxvG8ChWX7x",
    laneLabel: "properties",
    boardUrl: "https://app.todoist.com/app/project/6hXX2jxvG8ChWX7x",
    initialSection: "未着手",
    openSections: [...OPEN_SECTIONS],
    doneSections: [],
    hideDoneOnBoard: true,
    filterByLaneLabel: false,
    sectionIds: {
      未着手: "6hXX2m59CJHWHXfQ",
      進行中: "6hXX2m4FXrw8hVCQ",
      相手待ち: "6hXX2m4vV2hwqhRx",
      HOLD: "6hXmWXhqwjvg2cGx",
      オーナー確認: "6hXX2m7MJ3FchGcx",
    },
  },
  // 専用PJへ（業務まとめ work_bundle は archived。Slack Todoist追加が 403 PROJECT_ARCHIVED になっていた）
  ai_raimo: {
    title: "AI・Raimo",
    projectKey: "ai_raimo",
    projectId: "6hXp5cmgjR83Rj6g",
    laneLabel: "ai_raimo",
    boardUrl: "https://app.todoist.com/app/project/6hXp5cmgjR83Rj6g",
    initialSection: "未着手",
    openSections: [...OPEN_SECTIONS],
    doneSections: [],
    hideDoneOnBoard: true,
    filterByLaneLabel: false,
    sectionIds: {
      未着手: "6hXp5crCpR7FV5Gg",
      進行中: "6hXp5crRPm5M43C8",
      相手待ち: "6hXp5cwWWjJ6QVG8",
      HOLD: "6hXp5cwX72pFWrX8",
      オーナー確認: "6hXp5cxwr9pRPw28",
    },
  },
  kamiooya: {
    title: "神大家運営",
    projectKey: "kamiooya",
    projectId: "6hXp5f57rFHGPhV6",
    laneLabel: "kamiooya",
    boardUrl: "https://app.todoist.com/app/project/6hXp5f57rFHGPhV6",
    initialSection: "未着手",
    openSections: [...OPEN_SECTIONS],
    doneSections: [],
    hideDoneOnBoard: true,
    filterByLaneLabel: false,
    sectionIds: {
      未着手: "6hXp5f972whJ6fX6",
      進行中: "6hXp5f8wQM88Gfgc",
      相手待ち: "6hXp5fCMXj52xFXc",
      HOLD: "6hXp5fFRWrPpgHf6",
      オーナー確認: "6hXp5fHCqG85XjMc",
    },
  },
  kanji: {
    title: "飲み会幹事",
    projectKey: "kanji",
    projectId: "6hXp5fRGj5Cq4Q5q",
    laneLabel: "kanji",
    boardUrl: "https://app.todoist.com/app/project/6hXp5fRGj5Cq4Q5q",
    initialSection: "未着手",
    openSections: [...OPEN_SECTIONS],
    doneSections: [],
    hideDoneOnBoard: true,
    filterByLaneLabel: false,
    sectionIds: {
      未着手: "6hXp5fV3qVVj2phH",
      進行中: "6hXp5fXM4qRvPXfq",
      相手待ち: "6hXp5fVJ77RJjWFH",
      HOLD: "6hXp5ffFq7J3CWVH",
      オーナー確認: "6hXp5ffjVw9fc9fH",
    },
  },
  apps: {
    title: "アプリ開発",
    projectKey: "apps",
    projectId: "6hXfrWj4gwv9xQj6",
    laneLabel: "apps",
    boardUrl: "https://app.todoist.com/app/project/6hXfrWj4gwv9xQj6",
    initialSection: "未着手",
    openSections: [...OPEN_SECTIONS],
    doneSections: [],
    hideDoneOnBoard: true,
    filterByLaneLabel: false,
    sectionIds: {
      未着手: "6hXfrWvX6vpjfV26",
      進行中: "6hXfrWw2r3HRX92c",
      相手待ち: "6hXfrX2g76rcc4wc",
      HOLD: "6hXmWXwH43cgvrf6",
      オーナー確認: "6hXfrX2839CrjP46",
    },
  },
  kodate: {
    title: "戸建て",
    projectKey: "kodate",
    projectId: "6hXX2mMc58ff5QH2",
    laneLabel: "kodate",
    boardUrl: "https://app.todoist.com/app/project/6hXX2mMc58ff5QH2",
    initialSection: "未着手",
    openSections: [...OPEN_SECTIONS],
    doneSections: [],
    hideDoneOnBoard: false,
    filterByLaneLabel: false,
    sectionIds: {
      未着手: "6hXX2mMCjRGj7JC2",
      進行中: "6hXX2mVQr59jxhm2",
      相手待ち: "6hXX2mRgGHQ5Xg5R",
      HOLD: "6hXmWcJhrjHhMCG2",
      オーナー確認: "6hXX2mQVQJrv3QVR",
    },
  },
  kazoku: {
    title: "家族",
    projectKey: "kazoku",
    projectId: "6hXX2mWRmPJHMfR3",
    laneLabel: "kazoku",
    boardUrl: "https://app.todoist.com/app/project/6hXX2mWRmPJHMfR3",
    initialSection: "未着手",
    openSections: [...OPEN_SECTIONS],
    doneSections: [],
    hideDoneOnBoard: false,
    filterByLaneLabel: false,
    sectionIds: {
      未着手: "6hXX2mg9vgCf3MQ3",
      進行中: "6hXX2mghq49PHrg3",
      相手待ち: "6hXX2mjRc93w6hm3",
      HOLD: "6hXmWcRP27rfpVXV",
      オーナー確認: "6hXX2mp7RMMcvVgV",
    },
  },
};

export function loadTodoistLaneConfig(lane: string): TodoistLaneConfig | null {
  return TODOIST_TASK_LANES[lane] || null;
}
