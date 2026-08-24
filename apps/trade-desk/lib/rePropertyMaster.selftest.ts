/**
 * Run: npx tsx lib/rePropertyMaster.selftest.ts
 */
import {
  RE_PROPERTY_MASTER,
  fmtKeyNumber,
  fmtPostalCode,
  formatMasterLocation,
  getRePropertyMaster,
} from "./rePropertyMaster";

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg);
}

assert(RE_PROPERTY_MASTER.length === 3, "3 properties");

const g1 = getRePropertyMaster("grandole-i");
const g2 = getRePropertyMaster("grandole-ii");
const caramel = getRePropertyMaster("caramel");
assert(g1 && g2 && caramel, "ids present");

assert(g1.postalCode === "462-0834", "G1 postal");
assert(g2.postalCode === "462-0834", "G2 postal");
assert(caramel.postalCode === "459-8008", "caramel postal");
assert(fmtPostalCode(g1.postalCode) === "〒462-0834", "fmt G1 postal");
assert(fmtPostalCode("4598008") === "〒459-8008", "digits only");
assert(
  formatMasterLocation(g1).startsWith("〒462-0834 "),
  "location includes postal"
);

assert(g1.keyNumber === 2842, "G1 key from Notion cache");
assert(g2.keyNumber === 1555, "G2 key from Notion cache");
assert(caramel.keyNumber === null, "caramel has no key");
assert(fmtKeyNumber(g1.keyNumber) === "2842", "fmt G1 key");
assert(fmtKeyNumber(g2.keyNumber) === "1555", "fmt G2 key");
assert(fmtKeyNumber(caramel.keyNumber) === "なし", "caramel key is なし");
assert(fmtKeyNumber(null) === "なし", "null key");
assert(fmtKeyNumber(undefined) === "なし", "undefined key");

assert(g1.book && g1.book.bodyPriceJpy === 68_532_000, "G1 book body");
assert(g1.entity === "corporate", "G1 entity");
assert(caramel.entity === "personal", "caramel entity");
assert(caramel.book && caramel.book.buildingYears === 22, "caramel years");

for (const p of RE_PROPERTY_MASTER) {
  assert(/^\d{3}-\d{4}$/.test(p.postalCode), `${p.id} postal format`);
  assert(p.address.length > 8, `${p.id} address`);
  assert(p.book != null, `${p.id} book`);
}

console.log("rePropertyMaster.selftest: ok");
