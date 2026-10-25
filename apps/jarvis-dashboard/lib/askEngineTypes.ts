/** クライアント／サーバー共有の「聞く」エンジン型（副作用なし） */

export type AskEngine = "auto" | "cursor" | "gemini";
export type AskVia = "cloud" | "gemini" | "local_worker";
