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

const WORK_BUNDLE_SECTIONS: Record<string, string> = {
  未着手: "6hXX2m9G5vq9gQ3j",
  進行中: "6hXX2m9H2gjfx5hj",
  相手待ち: "6hXX2mFph4hpV5jC",
  HOLD: "6hXmWXmfMfMx62GC",
  オーナー確認: "6hXX2mGJJFhV6mgj",
};

const WORK_BUNDLE_ID = "6hXX2m7CJVrvmh9j";

function workBundleLane(
  title: string,
  label: string,
  hideDone = true,
): TodoistLaneConfig {
  return {
    title,
    projectKey: "work_bundle",
    projectId: WORK_BUNDLE_ID,
    laneLabel: label,
    boardUrl: `https://app.todoist.com/app/project/${WORK_BUNDLE_ID}`,
    initialSection: "未着手",
    openSections: [...OPEN_SECTIONS],
    doneSections: [],
    hideDoneOnBoard: hideDone,
    filterByLaneLabel: true,
    sectionIds: WORK_BUNDLE_SECTIONS,
  };
}

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
  ai_raimo: workBundleLane("AI・Raimo", "ai_raimo"),
  kamiooya: workBundleLane("神大家運営", "kamiooya"),
  kanji: workBundleLane("飲み会幹事", "kanji"),
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
