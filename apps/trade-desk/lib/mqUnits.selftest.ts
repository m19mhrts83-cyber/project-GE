/**
 * Run: npx tsx lib/mqUnits.selftest.ts
 */
import { fmtMqMan, roundMan, yenToMan } from "./mqUnits";

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg);
}

assert(yenToMan(19999) === 2, "round up 1.9999万");
assert(yenToMan(15000) === 2, "round half up 1.5万");
assert(yenToMan(14999) === 1, "round down");
assert(yenToMan(8250000) === 825, "demo scale");
assert(roundMan(20.4) === 20, "roundMan down");
assert(roundMan(20.5) === 21, "roundMan up");
assert(fmtMqMan(825) === "825万", "fmt");
assert(fmtMqMan(null) === "—", "null");

console.log("mqUnits.selftest: ok");
