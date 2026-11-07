"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Icon from "./Icon";
import { SEED_TOPICS_312 } from "@/lib/seed312";
import { loadStore } from "@/lib/storage";

export default function FocusCard() {
  const [decided, setDecided] = useState<string[]>([]);
  useEffect(() => {
    setDecided(
      loadStore()
        .decisions.filter((d) => d.agentId === "312")
        .map((d) => d.topicId),
    );
  }, []);
  const pending = SEED_TOPICS_312.filter((t) => !decided.includes(t.id));
  const next = pending[0];

  if (!next) {
    return (
      <div className="glass" style={{ padding: 20 }}>
        <div className="eyebrow acc" style={{ color: "var(--positive)" }}>
          ALL CLEAR
        </div>
        <p style={{ margin: "8px 0 0", fontSize: 15, fontWeight: 600 }}>
          判断待ちはありません
        </p>
        <p className="meta" style={{ margin: "4px 0 0" }}>
          312 の例題はすべて記録済みです。
        </p>
      </div>
    );
  }

  return (
    <div className="focus-card">
      <div className="label">
        <Icon name="clock" size={18} />
        <span className="eyebrow" style={{ margin: 0, color: "inherit" }}>
          判断待ち
        </span>
      </div>
      <div className="big">
        <b>{pending.length}</b>
        <span>件のお題</span>
      </div>
      <div>{next.title}。3案から選ぶ。</div>
      <Link
        className="cta"
        href={`/312?topic=${next.id}`}
        style={{ textDecoration: "none" }}
      >
        判断する <Icon name="arrow" size={18} stroke={2.4} />
      </Link>
    </div>
  );
}
