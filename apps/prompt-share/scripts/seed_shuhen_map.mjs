#!/usr/bin/env node
/**
 * 周辺MAP 3プロンプトを kamiooya-qa に初期登録する。
 * 使い方: cd apps/prompt-share && node --env-file=.env.local scripts/seed_shuhen_map.mjs
 */
import { createClient } from "@supabase/supabase-js";
import { randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "../../..");
const MAP_DIR = resolve(
  ROOT,
  "215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/AI×周辺MAP"
);

function requireEnv(k) {
  const v = process.env[k]?.trim();
  if (!v) throw new Error(`Missing env: ${k}`);
  return v;
}

function token() {
  return randomBytes(12).toString("hex");
}

function extractFence(md) {
  const m = md.match(/```\n([\s\S]*?)\n```/);
  if (!m) throw new Error("code fence not found");
  return m[1].trim() + "\n";
}

function syncVars(template, meta = {}) {
  const keys = [];
  const seen = new Set();
  for (const m of template.matchAll(/\{([^{}]+)\}/g)) {
    const key = m[1].trim();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    keys.push(key);
  }
  return keys.map((key) => ({
    key,
    label: meta[key]?.label || key,
    placeholder: meta[key]?.placeholder || "",
    help_text: meta[key]?.help_text || "",
    required: !!meta[key]?.required,
    default_example: meta[key]?.default_example || ""
  }));
}

const sb = createClient(requireEnv("SUPABASE_URL"), requireEnv("SUPABASE_SERVICE_ROLE_KEY"), {
  auth: { persistSession: false, autoRefreshToken: false }
});

const step11Path = resolve(MAP_DIR, "01_Raimoプロンプト_Step1基本洗い出し.md");
const step12Path = resolve(MAP_DIR, "02_DeepResearchプロンプト_評判店リサーチ.md");
const step3Path = resolve(MAP_DIR, "11_Raimoプロンプト_C1下地色味寄せ.md");

let t11 = extractFence(readFileSync(step11Path, "utf8"));
const t12 = extractFence(readFileSync(step12Path, "utf8"));
const t3 = extractFence(readFileSync(step3Path, "utf8"));

const { data: existingGroup } = await sb
  .from("prompt_groups")
  .select("*")
  .eq("slug", "ai-shuhen-map")
  .maybeSingle();

let group = existingGroup;
if (!group) {
  const { data, error } = await sb
    .from("prompt_groups")
    .insert({
      name: "AI×周辺MAP",
      slug: "ai-shuhen-map",
      description: "周辺MAP作成用プロンプト（Step1.1 / 1.2 / Step3）",
      sort_order: 10,
      access_level: "public"
    })
    .select("*")
    .single();
  if (error) throw error;
  group = data;
  console.log("created group", group.id);
} else {
  console.log("reuse group", group.id);
}

const token12 = token();
const token11 = token();
const token3 = token();
const site = (process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3002").replace(/\/$/, "");
const url12 = `${site}/p/${token12}`;

// Step1.1 の次工程URLを自前アプリへ差し替え
t11 = t11.replace(/https:\/\/chapro\.jp\/prompt\/475607/g, url12);

const defs = [
  {
    title: "【周辺MAP作成_Step1.1】基本洗い出し",
    description: "通常チャット用。物件名・住所からAccess／施設候補／吹き出しのたたきを作成。",
    template: t11,
    public_token: token11,
    variables: syncVars(t11, {
      物件名: { label: "物件名", required: true, placeholder: "Grandole志賀本通", default_example: "Grandole志賀本通" },
      住所: {
        label: "住所",
        required: true,
        placeholder: "愛知県名古屋市北区（志賀本通駅周辺）",
        default_example: "愛知県名古屋市北区（志賀本通駅周辺）",
        help_text: "番地まで分かる範囲で"
      },
      ターゲット: { label: "ターゲット", placeholder: "単身・カップル", default_example: "単身・カップル" },
      施設数の目安: { label: "施設数の目安", placeholder: "15", default_example: "15" }
    })
  },
  {
    title: "【周辺MAP作成_Step1.2】実在検証・評判店リサーチ",
    description: "Deep Research用。Step1.1の候補を実在確認し ## E / ## H を出力。",
    template: t12,
    public_token: token12,
    variables: syncVars(t12, {
      "Step1.1出力（Step1.2へ渡す用）": {
        label: "Step1.1出力（Step1.2へ渡す用）",
        required: true,
        help_text: "Step1.1の「6. Step1.2へ渡す用」コードブロックの中身だけを貼る"
      },
      "ペルソナ要約（任意・あれば最優先）": {
        label: "ペルソナ要約（任意・あれば最優先）",
        help_text: "アドバンス時のみ。空で可"
      }
    })
  },
  {
    title: "【周辺MAP作成_Step3】下地色味寄せ",
    description: "画像モード用（任意）。骨格スクショの色味寄せ。",
    template: t3,
    public_token: token3,
    variables: syncVars(t3, {
      物件名: { label: "物件名", placeholder: "Grandole志賀本通", default_example: "Grandole志賀本通" },
      タッチの強さ: {
        label: "タッチの強さ",
        placeholder: "控えめ / 標準 / 強め",
        default_example: "標準",
        help_text: "空なら標準"
      }
    })
  }
];

for (const d of defs) {
  const { data: ex } = await sb.from("prompts").select("id,title").eq("title", d.title).maybeSingle();
  if (ex) {
    const { data, error } = await sb
      .from("prompts")
      .update({
        description: d.description,
        template: d.template,
        variables: d.variables,
        group_id: group.id,
        status: "published",
        access_level: "public",
        public_token: d.public_token,
        updated_at: new Date().toISOString()
      })
      .eq("id", ex.id)
      .select("id,title,public_token")
      .single();
    if (error) throw error;
    console.log("updated", data.title, `${site}/p/${data.public_token}`);
  } else {
    const { data, error } = await sb
      .from("prompts")
      .insert({
        title: d.title,
        description: d.description,
        template: d.template,
        variables: d.variables,
        group_id: group.id,
        status: "published",
        access_level: "public",
        public_token: d.public_token
      })
      .select("id,title,public_token")
      .single();
    if (error) throw error;
    console.log("inserted", data.title, `${site}/p/${data.public_token}`);
  }
}

console.log("done");
