"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { loadVoice, saveVoice, type VoiceComment } from "@/lib/storage";

async function post(op: "add" | "delete" | "reassign", c: VoiceComment, fromTargetId?: string): Promise<boolean> {
  try {
    const res = await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        op,
        comment: {
          id: c.id,
          agentId: c.agentId,
          targetId: c.targetId,
          targetLabel: c.targetLabel,
          text: c.text,
          at: c.at,
          via: c.via,
          startedAt: c.startedAt,
          mode: c.mode,
          alt: c.alt,
          fromTargetId,
        },
      }),
    });
    const j = (await res.json().catch(() => null)) as { persisted?: boolean } | null;
    return j?.persisted === true;
  } catch {
    return false;
  }
}

/** 音声コメントの保持（端末）＋ Supabase への追記。 */
export function useVoiceLog(agentId: VoiceComment["agentId"]) {
  const [all, setAll] = useState<VoiceComment[]>([]);
  const ref = useRef<VoiceComment[]>([]);

  const commit = useCallback((next: VoiceComment[]) => {
    ref.current = next;
    setAll(next);
    saveVoice(next);
  }, []);

  useEffect(() => {
    const list = loadVoice();
    ref.current = list;
    setAll(list);
    // 前回送れなかったものを再送
    list
      .filter((c) => c.agentId === agentId && c.synced !== true)
      .slice(0, 20)
      .forEach(async (c) => {
        const ok = await post("add", c);
        commit(ref.current.map((x) => (x.id === c.id ? { ...x, synced: ok } : x)));
      });
  }, [agentId, commit]);

  const add = useCallback(
    async (
      text: string,
      targetId: string,
      targetLabel: string,
      via: "voice" | "text",
      meta?: { startedAt?: string; mode?: "follow" | "pin"; alt?: { id: string; label: string } },
    ) => {
      const t = text.trim();
      if (!t) return;
      const c: VoiceComment = {
        id: `vc-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        agentId,
        targetId,
        targetLabel,
        text: t,
        at: new Date().toISOString(),
        via,
        synced: null,
        ...meta,
      };
      commit([c, ...ref.current]);
      const ok = await post("add", c);
      commit(ref.current.map((x) => (x.id === c.id ? { ...x, synced: ok } : x)));
    },
    [agentId, commit],
  );

  const remove = useCallback(
    async (id: string) => {
      const c = ref.current.find((x) => x.id === id);
      commit(ref.current.filter((x) => x.id !== id));
      if (c) await post("delete", c);
    },
    [commit],
  );

  /** 見ながら言った発話を、別のカードへ付け替える（元の行は残し、付け替えた記録を足す） */
  const reassign = useCallback(
    async (id: string, targetId: string, targetLabel: string) => {
      const c = ref.current.find((x) => x.id === id);
      if (!c) return;
      const from = c.targetId;
      const next: VoiceComment = { ...c, targetId, targetLabel, alt: undefined, synced: null };
      commit(ref.current.map((x) => (x.id === id ? next : x)));
      const ok = await post("reassign", next, from);
      commit(ref.current.map((x) => (x.id === id ? { ...x, synced: ok } : x)));
    },
    [commit],
  );

  const forTarget = useCallback(
    (targetId: string) =>
      all.filter((c) => c.agentId === agentId && c.targetId === targetId),
    [all, agentId],
  );

  return { all, add, remove, reassign, forTarget };
}
