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

## Deployment state

Applied on 2026-11-12:

- Supabase migration `20261112_obsidian_vault_read_watchdog.sql`.
- Vercel Production read, poll, and monitor keys plus private `#ops` webhook.
- Read-only tools added to the existing owner-only ChatGPT Site plugin, which retains `submit_daily_review`.
- Mac poll key added to `~/git-repos/.env.jarvis_private`; the LaunchAgent runs from a persistent checkout at 60-second intervals.

Still required: create a private Apps Script project, set these Script Properties, and run the installer function once:

- `OBSIDIAN_WATCHDOG_URL` = `https://jarvis-dashboard-amber.vercel.app/api/obsidian-review/monitor`
- `OBSIDIAN_WATCHDOG_KEY` = Vercel Production `OBSIDIAN_REVIEW_MONITOR_KEY`

The Site plugin has separate read and submit tools; the read MCP key is stored as a Site secret and is distinct from the review submit key. Open a new ChatGPT conversation if the refreshed tool list is not visible. Do not paste key values into chat or commit them.
