/**
 * Run: npx tsx lib/notionPropertyKeys.selftest.ts
 */
import {
  fetchPropertyKeyNumbers,
  parseKeyNumberValue,
  yamlKeyCache,
} from "./notionPropertyKeys";
import {
  applyLiveKeyNumbers,
  matchPropertyIdByNotionName,
  RE_PROPERTY_MASTER,
} from "./rePropertyMaster";

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg);
}

assert(matchPropertyIdByNotionName("Grandole志賀本通II") === "grandole-ii", "II first");
assert(matchPropertyIdByNotionName("01_Grandole志賀本通II") === "grandole-ii", "II prefix");
assert(matchPropertyIdByNotionName("Grandole志賀本通I") === "grandole-i", "I not II");
assert(matchPropertyIdByNotionName("Grandole志賀本通Ⅰ") === "grandole-i", "roman I");
assert(matchPropertyIdByNotionName("02_Grandole志賀本通I") === "grandole-i", "I prefix");
assert(matchPropertyIdByNotionName("03_キャラメル") === "caramel", "caramel");
assert(matchPropertyIdByNotionName("") === null, "empty");

assert(parseKeyNumberValue({ number: 2842 }) === 2842, "number");
assert(parseKeyNumberValue({ number: null }) === null, "empty number");
assert(
  parseKeyNumberValue({
    rich_text: [{ plain_text: "なし" }],
  }) === null,
  "text なし"
);
assert(
  parseKeyNumberValue({
    rich_text: [{ plain_text: "1555" }],
  }) === 1555,
  "text digits"
);
assert(parseKeyNumberValue({ select: { name: "なし" } }) === null, "select none");

const cached = yamlKeyCache();
assert(cached["grandole-i"] === 2842, "yaml G1");
assert(cached["caramel"] === null, "yaml caramel");

const overlaid = applyLiveKeyNumbers(RE_PROPERTY_MASTER, {
  "grandole-i": 2842,
  "grandole-ii": 1555,
  caramel: null,
});
assert(overlaid.find((p) => p.id === "caramel")?.keyNumber === null, "live none");
assert(overlaid.find((p) => p.id === "grandole-i")?.keyNumber === 2842, "live G1");

async function main() {
  const fetched = await fetchPropertyKeyNumbers();
  if (!process.env.NOTION_API_TOKEN?.trim()) {
    assert(fetched.source === "yaml_cache", "offline cache");
    assert(fetched.reason === "NOTION_API_TOKEN 未設定", "offline reason");
    console.log("notionPropertyKeys.selftest: ok (skip live, no token)");
    return;
  }
  assert(fetched.source === "notion", `live source: ${fetched.reason || ""}`);
  assert(fetched.keys["grandole-i"] === 2842, "live G1 key");
  assert(fetched.keys["grandole-ii"] === 1555, "live G2 key");
  assert(fetched.keys["caramel"] == null, "live caramel none");
  console.log("notionPropertyKeys.selftest: ok (live Notion)");
}

void main().catch((e) => {
  console.error(e);
  process.exit(1);
});
