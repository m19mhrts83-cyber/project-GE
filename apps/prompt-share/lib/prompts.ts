export type PromptVariable = {
  key: string;
  label: string;
  placeholder?: string;
  help_text?: string;
  required?: boolean;
  default_example?: string;
};

export type PromptRow = {
  id: number;
  group_id: number | null;
  title: string;
  description: string;
  template: string;
  variables: PromptVariable[];
  public_token: string;
  status: "draft" | "published";
  access_level: "public" | "member";
  view_count: number;
  generate_count: number;
  copy_count: number;
  created_by: number | null;
  created_at: string;
  updated_at: string;
};

export type PromptGroup = {
  id: number;
  name: string;
  slug: string;
  description: string;
  sort_order: number;
  access_level: "public" | "member";
  created_at: string;
  updated_at: string;
};

export type EventType =
  | "view"
  | "generate"
  | "copy"
  | "open_chatgpt"
  | "open_gemini"
  | "open_claude"
  | "open_aistudio";

const VAR_RE = /\{([^{}]+)\}/g;

export function extractVariableKeys(template: string): string[] {
  const keys: string[] = [];
  const seen = new Set<string>();
  for (const m of String(template || "").matchAll(VAR_RE)) {
    const key = m[1].trim();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    keys.push(key);
  }
  return keys;
}

export function syncVariablesFromTemplate(
  template: string,
  existing: PromptVariable[] = []
): PromptVariable[] {
  const byKey = new Map(existing.map((v) => [v.key, v]));
  return extractVariableKeys(template).map((key) => {
    const prev = byKey.get(key);
    return {
      key,
      label: prev?.label || key,
      placeholder: prev?.placeholder || "",
      help_text: prev?.help_text || "",
      required: prev?.required ?? false,
      default_example: prev?.default_example || ""
    };
  });
}

export function fillTemplate(
  template: string,
  values: Record<string, string>,
  variables: PromptVariable[] = []
): string {
  const defaults = new Map(variables.map((v) => [v.key, v.default_example || ""]));
  return String(template || "").replace(VAR_RE, (_full, keyRaw: string) => {
    const key = keyRaw.trim();
    const v = values[key];
    if (v != null && String(v).length > 0) return String(v);
    return String(defaults.get(key) || "");
  });
}

export function randomPublicToken(bytes = 12): string {
  const arr = new Uint8Array(bytes);
  crypto.getRandomValues(arr);
  return Array.from(arr, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function slugify(input: string): string {
  const base = String(input || "")
    .trim()
    .toLowerCase()
    .replace(/[\s_/]+/g, "-")
    .replace(/[^a-z0-9\-一-龥ぁ-んァ-ヶー]/g, "")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
  return base || `group-${Date.now()}`;
}

export function siteUrl(): string {
  return (process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3002").replace(/\/$/, "");
}

export function publicPromptUrl(token: string): string {
  return `${siteUrl()}/p/${token}`;
}

export const AI_LINKS = [
  { key: "open_chatgpt" as const, label: "ChatGPT", href: "https://chatgpt.com/" },
  { key: "open_gemini" as const, label: "Gemini", href: "https://gemini.google.com/app" },
  { key: "open_claude" as const, label: "Claude", href: "https://claude.ai/" },
  { key: "open_aistudio" as const, label: "Google AI Studio", href: "https://aistudio.google.com/app/prompts/new_chat?hl=ja" }
];

export const VARIABLE_COLORS = [
  "#fef08a",
  "#fbcfe8",
  "#bbf7d0",
  "#bfdbfe",
  "#ddd6fe",
  "#fed7aa"
];
