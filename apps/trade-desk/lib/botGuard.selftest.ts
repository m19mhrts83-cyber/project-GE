/**
 * Run: npx tsx lib/botGuard.selftest.ts
 */
import assert from "node:assert/strict";
import { botBlock, isBotAccount } from "./botGuard";

const env: Record<string, string | undefined> = { BOT_ACCOUNT_EMAILS: "bot1@example.com, Bot2@example.com" };
const none: Record<string, string | undefined> = {};

assert.equal(isBotAccount("bot1@example.com", env), true);
assert.equal(isBotAccount("BOT2@example.com", env), true);
assert.ok(botBlock("bot1@example.com", "money", env));
assert.ok(botBlock("bot1@example.com", "secrets", env)?.error.includes("秘密"));
assert.equal(botBlock("owner@example.com", "money", env), null);
assert.equal(botBlock("owner@example.com", "secrets", env), null);
assert.equal(botBlock("bot1@example.com", "money", none), null);
assert.equal(botBlock("bot1@example.com", "money", { BOT_ACCOUNT_EMAILS: "" }), null);
assert.equal(botBlock(null, "money", env), null);
console.log("botGuard selftest ok");
