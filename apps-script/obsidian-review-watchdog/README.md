# Obsidian Mac heartbeat watchdog (Google Apps Script)

Runs outside the Mac every five minutes and calls the authenticated Dashboard monitor. The Dashboard checks the last successful Mac poll and sends a Slack `#ops` message only when the state changes to offline or recovers. The GAS project stores only the monitor endpoint and its dedicated bearer key in Script Properties; Slack webhook credentials stay in Vercel.

## One-time setup

1. Create a private standalone Apps Script project and copy `Code.gs` and `appsscript.json` into it.
2. In **Project Settings → Script properties**, set:
   - `OBSIDIAN_WATCHDOG_URL` = `https://jarvis-dashboard-amber.vercel.app/api/obsidian-review/monitor`
   - `OBSIDIAN_WATCHDOG_KEY` = the value of Vercel Production `OBSIDIAN_REVIEW_MONITOR_KEY`
3. Run `installObsidianReviewWatchdogTrigger` once and approve UrlFetch/time-trigger permissions.
4. Confirm the Apps Script execution is successful. The first online check initializes state without a Slack message. If no Mac poll arrives for 10 minutes after initialization, it sends an offline alert; recovery sends one follow-up.

The trigger is best-effort on Google's schedule. Expected alert delay is approximately 5–10 minutes after the last poll, plus any Apps Script scheduling delay. The Mac poller keeps its existing 60-second LaunchAgent interval, about 43,200 outbound polls per 30-day month, with no additional poller process.

## Secrets and deployment

The following values must be added to Vercel Production (the key value must not enter Git):

- `OBSIDIAN_REVIEW_READ_KEY` — ChatGPT read-only MCP key
- `OBSIDIAN_VAULT_POLL_KEY` — Mac read-queue poll/response key
- `OBSIDIAN_REVIEW_MONITOR_KEY` — GAS-to-Dashboard monitor key
- `SLACK_WEBHOOK_AI_TEAM_OPS` — existing private `#ops` Incoming Webhook

Also add `OBSIDIAN_VAULT_POLL_KEY` to `~/git-repos/.env.jarvis_private` on the Mac. Keep the existing review submit and review poll keys separate. Apply the Supabase migration before deploying the routes. Add the read-only MCP endpoint to the private ChatGPT connector:

`https://jarvis-dashboard-amber.vercel.app/api/obsidian-vault/mcp`

Use HTTP Bearer authentication with `OBSIDIAN_REVIEW_READ_KEY`. The existing review submit connector remains separate and write-only. Do not paste key values into chat or commit them.
