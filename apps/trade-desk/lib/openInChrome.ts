/** 掲載・ポータル URL を可能なら Mac の Google Chrome で開く（Cursor 中央ブラウザ回避） */

const LOCAL_OPEN = "http://127.0.0.1:18765/open-chrome";

export type OpenChromeResult = "chrome" | "fallback";

export async function openInGoogleChrome(url: string): Promise<OpenChromeResult> {
  const target = String(url || "").trim();
  if (!/^https?:\/\//i.test(target)) return "fallback";

  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 900);
    const endpoint = `${LOCAL_OPEN}?url=${encodeURIComponent(target)}`;
    const res = await fetch(endpoint, {
      method: "GET",
      mode: "cors",
      signal: ctrl.signal,
    });
    clearTimeout(timer);
    if (res.ok) return "chrome";
  } catch {
    /* local helper 未起動 → fallback */
  }

  if (typeof window !== "undefined") {
    window.open(target, "_blank", "noopener,noreferrer");
  }
  return "fallback";
}
