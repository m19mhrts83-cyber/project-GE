"use client";

import { useEffect, useState } from "react";

/** 数字を 0 から目標値まで数え上げる（動きを減らす設定なら最初から最終値） */
export default function MaturityCountUp({ value, decimals = 1, ms = 1400, delay = 0 }: { value: number; decimals?: number; ms?: number; delay?: number }) {
  const [v, setV] = useState(value);
  useEffect(() => {
    if (typeof window === "undefined" || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setV(value);
      return;
    }
    let raf = 0;
    let start = 0;
    setV(0);
    const tick = (t: number) => {
      if (!start) start = t;
      const p = Math.min(1, Math.max(0, (t - start - delay) / ms));
      const eased = 1 - Math.pow(1 - p, 3);
      setV(value * eased);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, ms, delay]);
  return <>{v.toFixed(decimals)}</>;
}
