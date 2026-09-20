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

const WORK_BUNDLE_SECTIONS: Record<string, string> = {
  未着手: "6hXX2m9G5vq9gQ3j",
  進行中: "6hXX2m9H2gjfx5hj",
  相手待ち: "6hXX2mFph4hpV5jC",
  オーナー確認: "6hXX2mGJJFhV6mgj",
  完了: "6hXX2mJ9fwgCMGJC",
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
    openSections: ["未着手", "進行中", "相手待ち", "オーナー確認"],
    doneSections: ["完了"],
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
    openSections: ["未着手", "進行中", "相手待ち", "オーナー確認"],
    doneSections: ["完了"],
    hideDoneOnBoard: true,
    filterByLaneLabel: false,
    sectionIds: {
      未着手: "6hXX2m59CJHWHXfQ",
      進行中: "6hXX2m4FXrw8hVCQ",
      相手待ち: "6hXX2m4vV2hwqhRx",
      オーナー確認: "6hXX2m7MJ3FchGcx",
      完了: "6hXX2m7mcJJf6wWQ",
    },
  },
  ai_raimo: workBundleLane("AI・Raimo", "ai_raimo"),
  kamiooya: workBundleLane("神大家運営", "kamiooya"),
  kanji: workBundleLane("飲み会幹事", "kanji"),
  apps: workBundleLane("アプリ開発", "apps"),
  kodate: {
    title: "戸建て",
    projectKey: "kodate",
    projectId: "6hXX2mMc58ff5QH2",
    laneLabel: "kodate",
    boardUrl: "https://app.todoist.com/app/project/6hXX2mMc58ff5QH2",
    initialSection: "未着手",
    openSections: ["未着手", "進行中", "相手待ち", "オーナー確認"],
    doneSections: ["完了"],
    hideDoneOnBoard: false,
    filterByLaneLabel: false,
    sectionIds: {
      未着手: "6hXX2mMCjRGj7JC2",
      進行中: "6hXX2mVQr59jxhm2",
      相手待ち: "6hXX2mRgGHQ5Xg5R",
      オーナー確認: "6hXX2mQVQJrv3QVR",
      完了: "6hXX2mXvW5vMGmq2",
    },
  },
  kazoku: {
    title: "家族",
    projectKey: "kazoku",
    projectId: "6hXX2mWRmPJHMfR3",
    laneLabel: "kazoku",
    boardUrl: "https://app.todoist.com/app/project/6hXX2mWRmPJHMfR3",
    initialSection: "未着手",
    openSections: ["未着手", "進行中", "相手待ち", "オーナー確認"],
    doneSections: ["完了"],
    hideDoneOnBoard: false,
    filterByLaneLabel: false,
    sectionIds: {
      未着手: "6hXX2mg9vgCf3MQ3",
      進行中: "6hXX2mghq49PHrg3",
      相手待ち: "6hXX2mjRc93w6hm3",
      オーナー確認: "6hXX2mp7RMMcvVgV",
      完了: "6hXX2mpgfqFFRR93",
    },
  },
};

export function loadTodoistLaneConfig(lane: string): TodoistLaneConfig | null {
  return TODOIST_TASK_LANES[lane] || null;
}
