/** 購入比較ループウェア — 型・シード・エクスポート（クライアント完結） */

export const STORAGE_KEY = "jarvis_purchase_compare_v1";

export type Candidate = {
  id: string;
  label: string;
  price: string;
  features: string;
  compatibility: string;
  annualConsumables: string;
  electricity?: string;
  checkedAt: string;
  source: string;
  unknowns: string;
  /** 商品写真・現物写真（https または data URL） */
  imageUrl?: string;
  imageCredit?: string;
  /** 価格・仕様の根拠（公式・サポート等） */
  referenceLinks?: { label: string; url: string }[];
  /** Amazon.co.jp 商品ページ（売っている場合） */
  amazonUrl?: string;
};

export type Topic = {
  id: string;
  title: string;
  conditions: string;
  candidates: Candidate[];
};

export type DecisionKind = "selected" | "skip_all";

export type TopicResult = {
  topicId: string;
  decision: DecisionKind;
  selectedCandidateId: string | null;
  selectReasons: string[];
  skipReasons: Record<string, string[]>;
  candidatesSnapshot: Candidate[];
  conditionsSnapshot: string;
  decidedAt: string;
  postPurchase?: {
    at: string;
    status: "purchased" | "cancelled" | "still_considering";
    satisfaction: "satisfied" | "regret" | "mixed" | "unknown";
    note: string;
  };
};

export type Store = {
  version: 1;
  topics: Topic[];
  results: TopicResult[];
};

export const REASON_TAGS = [
  "本体が安い",
  "手入れが楽",
  "交換品が高い",
  "互換性に不安",
  "必須条件を満たす",
  "工事不要で付けられる",
  "接続規格が合う",
  "一時止水が要る",
  "塩素低減が欲しい",
  "価格差に見合う差が不明",
] as const;

export const SHOWER_TOPIC_ID = "shower-head-20261107";

export const SHOWER_TOPIC: Topic = {
  id: SHOWER_TOPIC_ID,
  title: "シャワーヘッド",
  conditions: `シャワーヘッド。予算3.5万円。現在はTOTO手元シャワー（ヘッド単体着脱・ホース側メスねじ・ヘッド側Oリング2本・一時止水ボタンあり・金網フィルタあり）。2026-11-07にヘッドを外して再装着済み（単体交換可を確認）。ヘッドのみ交換希望。工事なし。塩素低減は任意。一時止水はあれば嬉しいが必須ではない。本体価格だけでなく、カートリッジ等の年間維持費も比較する。価格差が大きいなら「TOTO替えで十分か／上位の差に払う価値があるか」を判断する。取り付け時は金網フィルタとパッキンを戻す。`,
  candidates: [
    {
      id: "toto-replacement",
      label: "TOTO 現使用ヘッド相当（純正替え）",
      price: "4,000〜17,000円（機種による。要品番確認）",
      features:
        "手元一時止水ボタンあり。円形フェイス・クロムボディ。水流は標準〜節水寄り（エアイン／クリック系）",
      compatibility:
        "TOTOホース G1/2想定。実機でヘッド単体着脱確認済み。アダプター不要の可能性が高い。既存フィルタ・パッキン流用可",
      annualConsumables: "ほぼ0円（フィルタ清掃のみ）",
      checkedAt: "2026-11-07",
      source: "実機写真（2026-11-07）・TOTO公式サポート・パーツショップ価格帯",
      unknowns: "現行ヘッドの正確な品番、希望する水流モード",
      imageUrl: "/purchase-compare/toto-current.jpg",
      imageCredit: "自宅の現物写真（2026-11-07）",
      referenceLinks: [
        {
          label: "TOTO公式：シャワーヘッド交換手順（G1/2）",
          url: "https://jp.toto.com/support/repair/bath/faucet/replaceshowerhead",
        },
      ],
      // クロム丸型エアイン・クリック取替用（THC57C）。現物品番確定までは参考
      amazonUrl: "https://www.amazon.co.jp/dp/B00MWR5QC6",
    },
    {
      id: "refa-one",
      label: "ReFa Fine Bubble ONE",
      price: "約18,480円",
      features: "ファインバブル。水流モードは上位より少なめ",
      compatibility:
        "グリップねじ G1/2。TOTOホースなら直結想定。KVK／MYM／ガスター時は付属アダプター",
      annualConsumables: "0円（カートリッジ無し想定）",
      checkedAt: "2026-11-07",
      source: "ReFa公式・販売ページ（要再確認）",
      unknowns: "一時止水の有無、手元ボタンの操作感",
      imageUrl:
        "https://www.refa.net/item/refa_fine_bubble_one/images/img-product.jpg",
      imageCredit: "ReFa公式商品ページ",
      referenceLinks: [
        {
          label: "ReFa公式：FINE BUBBLE ONE 商品ページ",
          url: "https://www.refa.net/item/refa_fine_bubble_one/",
        },
        {
          label: "MTG公式通販：FINE BUBBLE ONE",
          url: "https://www.mtgec.jp/shop/g/g5459520101",
        },
      ],
      amazonUrl: "https://www.amazon.co.jp/dp/B09Q5RFJG6",
    },
    {
      id: "refa-pure",
      label: "ReFa Fine Bubble PURE",
      price:
        "本体のみ約30,000〜33,000円／カートリッジ付約32,500〜35,500円",
      features:
        "4水流（ミスト／ジェット／ストレート／ピュアストレート）＋塩素低減カートリッジ対応",
      compatibility: "G1/2。TOTOホースなら直結想定。アダプター付属",
      annualConsumables:
        "約10,000円前後（カートリッジ約2,500円×目安3ヶ月。人数で短縮）",
      checkedAt: "2026-11-07",
      source: "ReFa公式価格・仕様",
      unknowns: "一時止水の有無、実使用でのカートリッジ交換頻度",
      imageUrl:
        "https://www.refa.net/item/refa_fine_bubble_pure/images/img-product.jpg",
      imageCredit: "ReFa公式商品ページ",
      referenceLinks: [
        {
          label: "ReFa公式：FINE BUBBLE PURE 商品ページ",
          url: "https://www.refa.net/item/refa_fine_bubble_pure/",
        },
        {
          label: "MTG公式通販：FINE BUBBLE PURE",
          url: "https://www.mtgec.jp/shop/pages/refa_bubble_pure.aspx",
        },
      ],
      amazonUrl: "https://www.amazon.co.jp/dp/B0BJTY5WP7",
    },
    {
      id: "bollina-wide",
      label: "ボリーナワイド（Bollina Wide／TKS）",
      price: "約11,550円（税込・公式ショップ目安。実売要確認）",
      features:
        "ウルトラファインバブル系。ワイドな浴び心地。ReFaより安価なファインバブル枠",
      compatibility:
        "日本製。一般的なG1/2想定（取り付け前にねじ確認）。工事なし・ヘッド交換想定",
      annualConsumables: "カートリッジ無し想定（ほぼ0円）",
      checkedAt: "2026-11-07",
      source: "TKS公式オンラインショップ・価格比較サイト",
      unknowns: "一時止水の有無、現行TOTOホースとの実機適合、水流モード数",
      imageUrl: "/purchase-compare/bollina-wide.jpg",
      imageCredit: "TKS公式ショップ商品画像（保存コピー）",
      referenceLinks: [
        {
          label: "Bollina公式サイト",
          url: "https://bollina.jp/",
        },
        {
          label: "TKS公式ショップ：シャワーヘッド一覧",
          url: "https://shop.tks-gifu.jp/collections/shower-head",
        },
      ],
      amazonUrl: "https://www.amazon.co.jp/dp/B07TB4H2B7",
    },
  ],
};

export function defaultStore(): Store {
  return {
    version: 1,
    topics: [structuredClone(SHOWER_TOPIC)],
    results: [],
  };
}

/** 既存 localStorage のお題に、シード側の写真・候補更新を反映する */
export function mergeSeedMedia(store: Store): Store {
  const seedById = new Map(
    SHOWER_TOPIC.candidates.map((c) => [c.id, c] as const),
  );
  const topics = store.topics.map((t) => {
    if (t.id !== SHOWER_TOPIC_ID) return t;
    let candidates = t.candidates.map((c) => {
      // 旧「他社ファインバブル」枠 → ボリーナワイドへ置換
      if (c.id === "other-fb") {
        return structuredClone(seedById.get("bollina-wide")!);
      }
      const seed = seedById.get(c.id);
      if (!seed) return c;
      const next = { ...c };
      // 現物写真・公式シード写真は最新シードを優先（ユーザーがdata URLを入れた場合は残す）
      const userLocalPhoto = Boolean(
        next.imageUrl?.startsWith("data:") ||
          (next.imageUrl &&
            !next.imageUrl.startsWith("/purchase-compare/") &&
            !next.imageUrl.includes("refa.net")),
      );
      if (!userLocalPhoto && seed.imageUrl) {
        next.imageUrl = seed.imageUrl;
        next.imageCredit = seed.imageCredit || next.imageCredit;
      }
      if (c.id === "toto-replacement") {
        next.label = seed.label;
        next.features = seed.features;
        next.source = seed.source;
      }
      // 根拠URL・Amazonはシードを優先更新（手入力上書きはしない想定の比較アプリ）
      if (seed.referenceLinks?.length) {
        next.referenceLinks = structuredClone(seed.referenceLinks);
      }
      if (seed.amazonUrl) next.amazonUrl = seed.amazonUrl;
      return next;
    });
    if (!candidates.some((c) => c.id === "bollina-wide")) {
      candidates = [
        ...candidates,
        structuredClone(seedById.get("bollina-wide")!),
      ];
    }
    return { ...t, candidates };
  });
  return { ...store, topics };
}

export function resultForTopic(
  store: Store,
  topicId: string,
): TopicResult | undefined {
  return store.results.find((r) => r.topicId === topicId);
}

export function upsertResult(store: Store, result: TopicResult): Store {
  const others = store.results.filter((r) => r.topicId !== result.topicId);
  return { ...store, results: [...others, result] };
}

export function formatResultMd(
  topic: Topic,
  result: TopicResult | undefined,
  liveCandidates?: Candidate[],
): string {
  const cands = liveCandidates || result?.candidatesSnapshot || topic.candidates;
  const conditions = result?.conditionsSnapshot || topic.conditions;
  const lines: string[] = [
    `# 購入比較結果：${topic.title}`,
    "",
    "## 買い物の条件",
    "",
    "```text",
    conditions.trim(),
    "```",
    "",
    "## 候補",
    "",
  ];

  for (const [i, c] of cands.entries()) {
    lines.push(`### ${i + 1}. ${c.label}`);
    lines.push("");
    if (c.imageUrl && !c.imageUrl.startsWith("data:")) {
      lines.push(`![${c.label}](${c.imageUrl})`);
      if (c.imageCredit) lines.push(`*写真: ${c.imageCredit}*`);
      lines.push("");
    } else if (c.imageUrl?.startsWith("data:")) {
      lines.push("（写真あり・端末内画像のためURL省略）");
      lines.push("");
    }
    lines.push("```text");
    lines.push(`価格：${c.price}`);
    lines.push(`機能：${c.features}`);
    lines.push(`互換性：${c.compatibility}`);
    lines.push(`年間消耗品代：${c.annualConsumables}`);
    if (c.electricity) lines.push(`電気代：${c.electricity}`);
    lines.push(`確認日：${c.checkedAt}`);
    lines.push(`情報源：${c.source}`);
    lines.push(`不明点：${c.unknowns}`);
    if (c.imageUrl && !c.imageUrl.startsWith("data:")) {
      lines.push(`写真URL：${c.imageUrl}`);
    }
    if (c.referenceLinks?.length) {
      lines.push("根拠URL：");
      for (const r of c.referenceLinks) {
        lines.push(`- ${r.label}: ${r.url}`);
      }
    }
    if (c.amazonUrl) lines.push(`Amazon：${c.amazonUrl}`);
    lines.push("```");
    lines.push("");
  }

  lines.push("## 最終判断");
  lines.push("");
  if (!result) {
    lines.push("（未決定）");
  } else if (result.decision === "skip_all") {
    lines.push("すべて見送り");
  } else {
    const sel =
      cands.find((c) => c.id === result.selectedCandidateId)?.label ||
      result.selectedCandidateId ||
      "（不明）";
    lines.push(`購入予定：${sel}`);
  }
  lines.push("");

  if (result?.selectReasons?.length) {
    lines.push("## 選択理由");
    lines.push("");
    for (const t of result.selectReasons) lines.push(`- ${t}`);
    lines.push("");
  }

  if (result?.skipReasons && Object.keys(result.skipReasons).length) {
    lines.push("## 見送り理由");
    lines.push("");
    for (const c of cands) {
      const tags = result.skipReasons[c.id];
      if (!tags?.length) continue;
      lines.push(`- ${c.label}：${tags.join("／")}`);
    }
    lines.push("");
  }

  if (result?.postPurchase) {
    const p = result.postPurchase;
    lines.push("## 購入後の追記");
    lines.push("");
    lines.push(`- 日付：${p.at}`);
    lines.push(`- 状態：${p.status}`);
    lines.push(`- 評価：${p.satisfaction}`);
    if (p.note) lines.push(`- メモ：${p.note}`);
    lines.push("");
  }

  lines.push("---");
  lines.push(`エクスポート日時：${new Date().toISOString()}`);
  return lines.join("\n");
}
