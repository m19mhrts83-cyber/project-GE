"use client";

import { useEffect, useState } from "react";
import {
  formatDecisionMd,
  loadStore,
  syncBadge,
  upsertDecision,
  type DecisionRecord,
} from "@/lib/storage";
import { postDecision, syncLabel } from "@/lib/postDecision";

type MissCand = {
  id: string;
  source: string;
  folder: string;
  snippet: string;
  hypothesis: string;
};

/** 段階2: ローカル／API が無いときの枠＋シード例 */
const SEED_MISSES: MissCand[] = [
  {
    id: "miss-seed-1",
    source: "yoritoori",
    folder: "P104_LEAF",
    snippet: "ご確認のほどお願いいたします（見積）",
    hypothesis: "やり取りに宿題サイン。未起票の可能性",
  },
  {
    id: "miss-seed-2",
    source: "obsidian_journal",
    folder: "Journal",
    snippet: "ミニテックへ返事まだ",
    hypothesis: "Journal 宿題言及",
  },
];

export default function MissesClient() {
  const [cands, setCands] = useState<MissCand[]>(SEED_MISSES);
  const [results, setResults] = useState<DecisionRecord[]>([]);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    setResults(
      loadStore().decisions.filter(
        (d) => d.agentId === "312" && d.topicId.startsWith("miss-"),
      ),
    );
    fetch("/api/misses")
      .then((r) => r.json())
      .then((j) => {
        if (Array.isArray(j?.candidates) && j.candidates.length) {
          setCands(j.candidates);
        }
      })
      .catch(() => undefined);
  }, []);

  async function verdict(c: MissCand, isMiss: boolean) {
    const rec: DecisionRecord = {
      topicId: c.id,
      agentId: "312",
      choice: isMiss ? "use" : "none_of_above",
      finalText: isMiss ? `漏れ: ${c.snippet}` : `漏れではない: ${c.snippet}`,
      reasonTags: isMiss ? ["拾い漏れ"] : ["漏れではない"],
      freeNote: c.hypothesis,
      decidedAt: new Date().toISOString(),
      decidedVia: "app",
    };
    upsertDecision(rec);
    setResults(
      loadStore().decisions.filter(
        (d) => d.agentId === "312" && d.topicId.startsWith("miss-"),
      ),
    );
    const head = isMiss ? "漏れとして記録" : "漏れではないと記録";
    setMsg(`${head}・共有DBへ送信中…`);
    const res = await postDecision(rec, {
      agentId: "312",
      topicText: `[miss] ${c.source} ${c.folder}\n${c.snippet}`,
      seedId: c.id,
    });
    setResults(
      loadStore().decisions.filter(
        (d) => d.agentId === "312" && d.topicId.startsWith("miss-"),
      ),
    );
    setMsg(`${head}・${syncLabel(res)}${isMiss ? " → 扱いタブへ" : ""}`);
  }

  return (
    <div>
      <p className="meta">
        スクリプト:{" "}
        <code>scripts/jarvis_todoist_312_miss_scan.py</code>
        。候補を漏れ／漏れではないで記録。漏れなら「扱いを決める」へ。
      </p>
      <ul className="list glass">
        {cands.map((c) => (
          <li key={c.id}>
            <strong>
              [{c.source}] {c.folder}
            </strong>
            <div className="meta">{c.snippet}</div>
            <div className="meta">{c.hypothesis}</div>
            <div className="btn-row" style={{ marginTop: 8 }}>
              <button
                type="button"
                className="primary"
                onClick={() => verdict(c, true)}
              >
                漏れ
              </button>
              <button type="button" onClick={() => verdict(c, false)}>
                漏れではない
              </button>
            </div>
          </li>
        ))}
      </ul>
      {msg ? <p className="meta">{msg}</p> : null}
      <h2 style={{ fontSize: "1.05rem", marginTop: 24 }}>漏れ判定ログ</h2>
      <ul className="list glass">
        {results.map((r) => (
          <li key={`${r.topicId}-${r.decidedAt}`}>
            {r.topicId} · {r.finalText} · {syncBadge(r)}
            <button
              type="button"
              style={{ marginLeft: 8 }}
              onClick={() => {
                void navigator.clipboard.writeText(formatDecisionMd(r));
              }}
            >
              コピー
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
