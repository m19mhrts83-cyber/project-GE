/** Zaim 費目カタログ。正本: config/zaim_category_catalog.yaml */
export type ZaimCategoryEntry = {
  value: string;
  label: string;
  group: string;
  genres: string[];
};

export const ZAIM_CATEGORY_CATALOG: ZaimCategoryEntry[] = [
  { value: "β.1F.住まい", label: "1F. 住まい", group: "β 生活", genres: [] },
  { value: "β.2C.食費", label: "2C. 食費", group: "β 生活", genres: [] },
  { value: "β.3C.水道/光熱", label: "3C. 水道/光熱", group: "β 生活", genres: [] },
  { value: "β.4C.通信", label: "4C. 通信", group: "β 生活", genres: [] },
  { value: "β.5C.日用雑貨", label: "5C. 日用雑貨", group: "β 生活", genres: [] },
  {
    value: "β.6.1C.エ/交際/被服/趣味",
    label: "6.1C. 交際/被服/趣味",
    group: "β 生活",
    genres: [],
  },
  {
    value: "β.6.2C 自己投資・寄付",
    label: "6.2C. 自己投資・寄付",
    group: "β 生活",
    genres: [],
  },
  { value: "β.7C.医療費", label: "7C. 医療費", group: "β 生活", genres: [] },
  { value: "β.8C.交通", label: "8C. 交通", group: "β 生活", genres: [] },
  {
    value: "β.10.1C.こども服/雑貨/写真",
    label: "10.1C. こども服/雑貨/写真",
    group: "β 生活",
    genres: [],
  },
  {
    value: "β.10.2C.こども教育",
    label: "10.2C. こども教育",
    group: "β 生活",
    genres: [],
  },
  {
    value: "β.10.2F.こども学費/結婚_固定",
    label: "10.2F. こども学費/結婚",
    group: "β 生活",
    genres: [],
  },
  {
    value: "β.10.3F.学資保険",
    label: "10.3F. 学資保険",
    group: "β 生活",
    genres: [],
  },
  {
    value: "β.11.1F.クルマ維持",
    label: "11.1F. クルマ維持",
    group: "β 生活",
    genres: [],
  },
  {
    value: "β.11.2F.維持(他生活インフラ)",
    label: "11.2F. 維持(他生活インフラ)",
    group: "β 生活",
    genres: [],
  },
  {
    value: "β.12.C.その他/使途不明",
    label: "12.C. その他/使途不明",
    group: "β 生活",
    genres: [],
  },
  {
    value: "β.13.1F.生命保険",
    label: "13.1F. 生命保険",
    group: "β 生活",
    genres: [],
  },
  {
    value: "β.13.2F.自動車保険",
    label: "13.2F. 自動車保険",
    group: "β 生活",
    genres: [],
  },
  {
    value: "β.15F.奨学金返済",
    label: "15F. 奨学金返済",
    group: "β 生活",
    genres: [],
  },
  {
    value: "β.17S.帰省・旅行",
    label: "17S. 帰省・旅行",
    group: "β 生活",
    genres: [],
  },
  {
    value: "β.20.1S.大型出費",
    label: "20.1S. 大型出費",
    group: "β 生活",
    genres: [],
  },
  { value: "β.20.2S.ご褒美", label: "20.2S. ご褒美", group: "β 生活", genres: [] },
  {
    value: "β.21F.AIリスキリング",
    label: "21F. AIリスキリング",
    group: "β 生活",
    genres: [],
  },
  { value: "B.C.投資", label: "B.C. 投資", group: "投資・法人", genres: [] },
  {
    value: "A.C.会社費用",
    label: "A.C. 会社費用",
    group: "投資・法人",
    genres: [],
  },
];

const byValue = new Map(ZAIM_CATEGORY_CATALOG.map((c) => [c.value, c]));

export function getZaimCategory(value: string): ZaimCategoryEntry | undefined {
  return byValue.get(value.trim());
}

export function isValidZaimCategory(value: string): boolean {
  return byValue.has(value.trim());
}

/** optgroup 付きの大分類グループ */
export function zaimCategoryGroups(): { group: string; items: ZaimCategoryEntry[] }[] {
  const map = new Map<string, ZaimCategoryEntry[]>();
  for (const c of ZAIM_CATEGORY_CATALOG) {
    const list = map.get(c.group) || [];
    list.push(c);
    map.set(c.group, list);
  }
  return [...map.entries()].map(([group, items]) => ({ group, items }));
}

/** 提案費目名からカタログ value を推定（部分一致） */
export function matchCategoryValue(suggest: string | undefined): string {
  const s = (suggest || "").trim();
  if (!s) return "";
  if (byValue.has(s)) return s;
  for (const c of ZAIM_CATEGORY_CATALOG) {
    if (s.includes(c.value) || c.value.includes(s)) return c.value;
    const short = c.value.replace(/^β\./, "");
    if (s.includes(short)) return c.value;
  }
  return "";
}

export type ZaimCategoryReviewItem = {
  row_key?: string;
  date?: string;
  shop?: string;
  item?: string;
  amount?: number;
  category?: string;
  genre?: string;
  suggest?: string;
  suggest_genre?: string;
  confidence?: string;
  learn_key?: string;
  pay?: string;
  method?: string;
  proposal?: string;
  pending_apply?: boolean;
  pending_category?: string;
  pending_genre?: string;
};

export type ZaimPendingCategoryApply = {
  id: string;
  row_key: string;
  status: "queued" | "applying" | "applied" | "failed";
  category: string;
  genre: string;
  date?: string;
  shop?: string;
  item?: string;
  amount?: number;
  learn_key?: string;
  pay?: string;
  method?: string;
  category_before?: string;
  source: "category_review" | "recent_fix";
  queued_at: string;
  applied_at?: string;
  message?: string;
};
