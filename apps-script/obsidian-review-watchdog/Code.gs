/** Cloud watchdog for the Mac Obsidian review/read poller. */
const WATCHDOG_HANDLER = 'runObsidianReviewWatchdog';

function runObsidianReviewWatchdog() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(5000)) return;
  try {
    const properties = PropertiesService.getScriptProperties();
    const endpoint = properties.getProperty('OBSIDIAN_WATCHDOG_URL');
    const key = properties.getProperty('OBSIDIAN_WATCHDOG_KEY');
    if (!endpoint || !key) throw new Error('Missing watchdog Script Properties');

    const response = UrlFetchApp.fetch(endpoint, {
      method: 'post',
      contentType: 'application/json',
      headers: { Authorization: 'Bearer ' + key },
      payload: JSON.stringify({ source: 'gas-time-trigger' }),
      muteHttpExceptions: true,
    });
    const code = response.getResponseCode();
    if (code < 200 || code >= 300) {
      // Do not include response body or credentials in execution logs.
      throw new Error('Watchdog endpoint returned HTTP ' + code);
    }
  } finally {
    lock.releaseLock();
  }
}

/** Run once from the Apps Script editor after setting Script Properties. */
function installObsidianReviewWatchdogTrigger() {
  ScriptApp.getProjectTriggers()
    .filter(function (trigger) { return trigger.getHandlerFunction() === WATCHDOG_HANDLER; })
    .forEach(function (trigger) { ScriptApp.deleteTrigger(trigger); });
  ScriptApp.newTrigger(WATCHDOG_HANDLER).timeBased().everyMinutes(5).create();
  runObsidianReviewWatchdog();
}
