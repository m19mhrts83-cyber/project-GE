/**
 * WeStudy 採点自動化 (Google Apps Script)
 *
 * 前提シート:
 * - 設定
 * - 元データ
 * - 得点基準
 * - 採点結果
 * - ログ
 * - 補正学習データ
 */

function onOpen() {
  buildMenu_();
}

function buildMenu_() {
  SpreadsheetApp.getUi()
    .createMenu("採点自動化")
    .addItem("CSV取込", "importCsvByConfig")
    .addItem("採点実行", "runScoring")
    .addItem("補正学習データを追加", "appendCorrectionLearningData")
    .addItem("ヘッダー初期化", "initializeSheets")
    .addToUi();
}

/**
 * メニューが出ないときの初回セットアップ。
 * Apps Script エディタでこの関数を1回実行 → スプレッドシートを再読込。
 */
function setupMenuTrigger() {
  var ssId = SpreadsheetApp.getActiveSpreadsheet().getId();
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === "buildMenu_" && t.getEventType() === ScriptApp.EventType.ON_OPEN) {
      ScriptApp.deleteTrigger(t);
    }
  });
  ScriptApp.newTrigger("buildMenu_")
    .forSpreadsheet(ssId)
    .onOpen()
    .create();
  Logger.log("採点自動化メニューのトリガーを登録しました。スプレッドシートを再読込してください。");
}

var DEFAULT_CSV_FILENAME_ = "WeStudy_for_scoring.csv";

function importCsvByConfig() {
  var cfg = readConfig_();
  var fileId = resolveCsvFileId_(cfg);
  importCsvFromDrive_(fileId);
}

/**
 * 設定シートのフォルダ ID + 固定ファイル名で CSV を特定する。
 * DRIVE_CSV_FOLDER_ID が未設定のときのみ DRIVE_CSV_FILE_ID（旧方式）にフォールバック。
 */
function resolveCsvFileId_(cfg) {
  var folderId = String(cfg.DRIVE_CSV_FOLDER_ID || "").trim();
  var filename = String(cfg.DRIVE_CSV_FILENAME || DEFAULT_CSV_FILENAME_).trim();

  if (folderId && filename) {
    var folder;
    try {
      folder = DriveApp.getFolderById(folderId);
    } catch (e) {
      throw new Error("DRIVE_CSV_FOLDER_ID のフォルダにアクセスできません: " + folderId);
    }
    var files = folder.getFilesByName(filename);
    if (files.hasNext()) {
      return files.next().getId();
    }
    throw new Error(
      'フォルダ内に "' +
        filename +
        '" がありません。WeStudy の CSV を同名で上書き配置してください。'
    );
  }

  var legacyId = String(cfg.DRIVE_CSV_FILE_ID || "").trim();
  if (legacyId) {
    return legacyId;
  }

  throw new Error(
    "設定シートに DRIVE_CSV_FOLDER_ID を設定してください（ファイル名は DRIVE_CSV_FILENAME、未設定時は " +
      DEFAULT_CSV_FILENAME_ +
      "）。"
  );
}

function runScoring() {
  var cfg = readConfig_();
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sourceSheet = ss.getSheetByName(cfg.SOURCE_SHEET_NAME || "元データ");
  var rulesSheet = ss.getSheetByName(cfg.RULES_SHEET_NAME || "得点基準");
  var resultSheet = ss.getSheetByName(cfg.RESULT_SHEET_NAME || "採点結果");

  if (!sourceSheet || !rulesSheet || !resultSheet) {
    throw new Error("必要シートが見つかりません。設定値またはシート名を確認してください。");
  }

  var rows = sourceSheet.getDataRange().getValues();
  if (rows.length <= 1) {
    log_("INFO", "runScoring", "", "元データが空です。");
    return;
  }

  var headers = rows[0];
  var idx = buildIndex_(headers);
  var rulesText = buildRulesText_(rulesSheet);
  var apiKey = cfg.GEMINI_API_KEY;
  var model = cfg.GEMINI_MODEL || "gemini-2.5-flash";
  var maxRows = parseMaxRows_(cfg.MAX_ROWS_PER_RUN, rows.length - 1);
  var includeReplies = String(cfg.INCLUDE_REPLIES || "FALSE").toUpperCase() === "TRUE";

  if (!apiKey) {
    throw new Error("設定シートに GEMINI_API_KEY を設定してください。");
  }

  prepareResultSheetForRun_(resultSheet);
  ss.toast("採点結果をクリアしました。最大 " + maxRows + " 件を採点します…", "採点自動化", 5);

  var attempted = 0;
  for (var r = 1; r < rows.length; r++) {
    if (attempted >= maxRows) break;

    var row = rows[r];
    var commentId = val_(row, idx["コメントID"]);
    var parentId = val_(row, idx["親コメントID"]);
    var commentBody = val_(row, idx["コメント内容"]);
    var postedAt = val_(row, idx["投稿日時"]);
    var authorName = val_(row, idx["投稿者名"]);

    if (!commentId || !commentBody) continue;
    if (!includeReplies && parentId) continue;

    attempted++;

    try {
      var prompt = buildPrompt_({
        commentId: commentId,
        postedAt: postedAt,
        authorName: authorName,
        parentCommentId: parentId || "",
        commentBody: commentBody,
        rulesText: rulesText
      });

      var result = callGemini_(apiKey, model, prompt);
      writeResult_(resultSheet, {
        commentId: commentId,
        postedAt: postedAt,
        authorName: authorName,
        parentCommentId: parentId || "",
        commentBody: commentBody,
        isTarget: result.is_target,
        classification: result.classification,
        subcategory: result.subcategory,
        ruleId: result.rule_id,
        score: result.score,
        reason: result.reason,
        evidence: (result.evidence || []).join(" | "),
        confidence: result.confidence,
        manualScore: "",
        version: "v1",
        scoredAt: new Date(),
        error: ""
      });
      Utilities.sleep(200);
    } catch (err) {
      writeResult_(resultSheet, {
        commentId: commentId,
        postedAt: postedAt,
        authorName: authorName,
        parentCommentId: parentId || "",
        commentBody: commentBody,
        isTarget: "",
        classification: "",
        subcategory: "",
        ruleId: "",
        score: "",
        reason: "",
        evidence: "",
        confidence: "",
        manualScore: "",
        version: "v1",
        scoredAt: new Date(),
        error: String(err)
      });
      log_("ERROR", "runScoring", String(commentId), String(err));
    }
  }

  log_("INFO", "runScoring", "", "採点試行件数: " + attempted);
  var resultRows = Math.max(0, resultSheet.getLastRow() - 1);
  ss.toast("採点完了: " + attempted + " 件処理（結果 " + resultRows + " 行）", "採点自動化", 10);
}

function resultSheetHeaders_() {
  return [
    "コメントID",
    "投稿日時",
    "投稿者名",
    "親コメントID",
    "コメント内容",
    "対象判定",
    "推定分野",
    "サブ分類",
    "ルールID",
    "得点",
    "根拠",
    "根拠抜粋",
    "信頼度",
    "手動補正点",
    "最終点",
    "採点バージョン",
    "採点日時",
    "エラー"
  ];
}

/** 採点実行のたびにヘッダーだけ残して採点結果を空にする */
function prepareResultSheetForRun_(sheet) {
  sheet.clearContents();
  sheet.appendRow(resultSheetHeaders_());
  SpreadsheetApp.flush();
}

function initializeSheets() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  var resultSheet = ss.getSheetByName("採点結果") || ss.insertSheet("採点結果");
  prepareResultSheetForRun_(resultSheet);

  var logSheet = ss.getSheetByName("ログ") || ss.insertSheet("ログ");
  logSheet.clearContents();
  logSheet.appendRow(["時刻", "レベル", "関数名", "コメントID", "メッセージ"]);

  var learnSheet = ss.getSheetByName("補正学習データ") || ss.insertSheet("補正学習データ");
  learnSheet.clearContents();
  learnSheet.appendRow([
    "追加日時",
    "コメントID",
    "投稿者名",
    "コメント内容",
    "Gemini得点",
    "手動補正点",
    "点差",
    "GeminiルールID",
    "最終ルールID",
    "補正理由メモ",
    "採点バージョン"
  ]);

  initVersionHistorySheet_(ss);
}

/** バージョン履歴シート（提供起点 V1.0）。既存シートは消さない */
function initVersionHistorySheet_(ss) {
  var sh = ss.getSheetByName("バージョン履歴");
  if (sh) return;
  sh = ss.insertSheet("バージョン履歴");
  sh.appendRow(["版", "日付", "変更内容", "備考"]);
  sh.appendRow([
    "",
    "",
    "※ V1.0 = 相手先への初回提供時に記載。以降 V1.1, V1.2 … で変更履歴を追記",
    "提供前の開発・検証は記載しない"
  ]);
}

function appendCorrectionLearningData() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var resultSheet = ss.getSheetByName("採点結果");
  var learnSheet = ss.getSheetByName("補正学習データ");

  if (!resultSheet) throw new Error("採点結果シートがありません。");
  if (!learnSheet) throw new Error("補正学習データシートがありません。");

  var resultValues = resultSheet.getDataRange().getValues();
  if (resultValues.length <= 1) {
    SpreadsheetApp.getUi().alert("補正学習データに 0 件追加しました。");
    return;
  }

  var headers = resultValues[0];
  var idx = buildIndex_(headers);

  var needCols = [
    "コメントID", "投稿者名", "コメント内容", "得点", "手動補正点", "最終点", "ルールID", "採点バージョン"
  ];
  for (var n = 0; n < needCols.length; n++) {
    if (idx[needCols[n]] === undefined) {
      throw new Error("採点結果シートに必要列がありません: " + needCols[n]);
    }
  }

  var existing = {};
  var lv = learnSheet.getDataRange().getValues();
  if (lv.length > 1) {
    for (var r = 1; r < lv.length; r++) {
      var cid = lv[r][1];
      if (cid !== "" && cid !== null) existing[String(cid)] = true;
    }
  }

  var appendRows = [];
  for (var r2 = 1; r2 < resultValues.length; r2++) {
    var row = resultValues[r2];
    var commentId = row[idx["コメントID"]];
    var authorName = row[idx["投稿者名"]];
    var body = row[idx["コメント内容"]];
    var aiScore = row[idx["得点"]];
    var manualCorrection = row[idx["手動補正点"]];
    var finalScore = row[idx["最終点"]];
    var ruleId = row[idx["ルールID"]];
    var version = row[idx["採点バージョン"]];

    if (finalScore === "" || finalScore === null) continue;
    if (
      aiScore !== "" && aiScore !== null && !isNaN(aiScore) &&
      !isNaN(finalScore) && Number(finalScore) === Number(aiScore)
    ) {
      continue;
    }
    if (!commentId) continue;
    if (existing[String(commentId)]) continue;

    var diff = "";
    if (manualCorrection !== "" && manualCorrection !== null && !isNaN(manualCorrection)) {
      diff = Number(manualCorrection);
    }

    appendRows.push([
      new Date(),
      commentId,
      authorName,
      body,
      aiScore,
      manualCorrection,
      diff,
      ruleId,
      "",
      "",
      version
    ]);
  }

  if (appendRows.length > 0) {
    var startRow = learnSheet.getLastRow() + 1;
    learnSheet
      .getRange(startRow, 1, appendRows.length, appendRows[0].length)
      .setValues(appendRows);
  }

  SpreadsheetApp.getUi().alert("補正学習データに " + appendRows.length + " 件追加しました。");
}

function importCsvFromDrive_(fileId) {
  var cfg = readConfig_();
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sourceSheet = ss.getSheetByName(cfg.SOURCE_SHEET_NAME || "元データ");
  if (!sourceSheet) throw new Error("元データシートがありません。");

  var file = DriveApp.getFileById(fileId);
  var blob = file.getBlob();
  var text = blob.getDataAsString("UTF-8");
  var csv = Utilities.parseCsv(text);

  sourceSheet.clearContents();
  sourceSheet.getRange(1, 1, csv.length, csv[0].length).setValues(csv);
  var dataRows = Math.max(0, csv.length - 1);
  log_("INFO", "importCsvFromDrive_", "", "CSV取り込み完了: " + file.getName() + " (" + dataRows + " 行)");
  ss.toast(
    file.getName() + " を取り込みました（データ " + dataRows + " 行）",
    "CSV取込",
    8
  );
}

function buildPrompt_(ctx) {
  return [
    "以下はWeStudyの投稿です。",
    "",
    "[投稿メタ]",
    "- コメントID: " + ctx.commentId,
    "- 投稿日時: " + ctx.postedAt,
    "- 投稿者名: " + ctx.authorName,
    "- 親コメントID: " + ctx.parentCommentId,
    "",
    "[投稿本文]",
    ctx.commentBody,
    "",
    "[得点基準ルール一覧]",
    ctx.rulesText,
    "",
    "判定手順:",
    "1) この投稿が成果報告/有用情報共有として採点対象か判定",
    "2) 対象なら最適なrule_idを1つ選択",
    "3) scoreはrule_idに対応する点数を返す",
    "4) reasonに本文中の根拠を簡潔に記載",
    "5) confidenceをhigh/medium/lowで返す",
    "",
    "出力はJSONのみ。キー:",
    "{",
    '  "is_target": true/false,',
    '  "classification": "成果報告系_購入" or "成果報告系_他" or "情報共有系" or "対象外",',
    '  "subcategory": "文字列",',
    '  "rule_id": "候補内のIDかN/A",',
    '  "score": 0以上の整数,',
    '  "reason": "文字列",',
    '  "evidence": ["文字列"],',
    '  "confidence": "high|medium|low"',
    "}"
  ].join("\n");
}

function callGemini_(apiKey, model, prompt) {
  var url = "https://generativelanguage.googleapis.com/v1beta/models/" + model + ":generateContent?key=" + encodeURIComponent(apiKey);
  var payload = {
    contents: [{ parts: [{ text: prompt }] }],
    generationConfig: {
      temperature: 0.1,
      responseMimeType: "application/json"
    }
  };

  var res = UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });

  var code = res.getResponseCode();
  var body = res.getContentText();
  if (code < 200 || code >= 300) {
    throw new Error("Gemini API error: " + code + " " + body);
  }

  var data = JSON.parse(body);
  var text = (((data.candidates || [])[0] || {}).content || {}).parts || [];
  if (!text.length || !text[0].text) {
    throw new Error("Geminiレスポンスにtextがありません");
  }

  var raw = text[0].text.trim();
  raw = stripCodeFence_(raw);
  var parsed = JSON.parse(raw);
  return parsed;
}

function buildRulesText_(rulesSheet) {
  var values = rulesSheet.getDataRange().getValues();
  if (values.length <= 1) return "";
  var headers = values[0];
  var idx = buildIndex_(headers);
  var lines = [];
  for (var i = 1; i < values.length; i++) {
    var row = values[i];
    if (String(val_(row, idx["有効"])).toUpperCase() !== "TRUE") continue;
    lines.push(
      [
        "- rule_id=" + val_(row, idx["ルールID"]),
        "大分類=" + val_(row, idx["大分類"]),
        "中分類=" + val_(row, idx["中分類"]),
        "レベル=" + val_(row, idx["レベル"]),
        "判定基準=" + val_(row, idx["判定基準"]),
        "点数=" + val_(row, idx["点数"])
      ].join(" / ")
    );
  }
  return lines.join("\n");
}

function buildResultIndex_(resultSheet) {
  var values = resultSheet.getDataRange().getValues();
  var index = {};
  if (values.length <= 1) return index;
  var headers = values[0];
  var idx = buildIndex_(headers);
  for (var i = 1; i < values.length; i++) {
    var id = val_(values[i], idx["コメントID"]);
    if (id) index[String(id)] = true;
  }
  return index;
}

function writeResult_(sheet, item) {
  var initialFinal =
    item.error === "" && item.score !== "" && item.score !== null ? item.score : "";
  sheet.appendRow([
    item.commentId,
    item.postedAt,
    item.authorName,
    item.parentCommentId,
    item.commentBody,
    item.isTarget,
    item.classification,
    item.subcategory,
    item.ruleId,
    item.score,
    item.reason,
    item.evidence,
    item.confidence,
    "",
    initialFinal,
    item.version,
    item.scoredAt,
    item.error
  ]);
  var rowNum = sheet.getLastRow();
  sheet
    .getRange(rowNum, 14)
    .setFormula('=IF(OR(O' + rowNum + '="",J' + rowNum + '=""),"",O' + rowNum + '-J' + rowNum + ')');
  SpreadsheetApp.flush();
}

function parseMaxRows_(raw, fallback) {
  if (raw === "" || raw === null || raw === undefined) {
    return fallback;
  }
  var n = Number(raw);
  if (isNaN(n) || n <= 0) {
    return fallback;
  }
  return n;
}

function readConfig_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName("設定");
  if (!sh) return {};
  var values = sh.getDataRange().getValues();
  var cfg = {};
  for (var i = 0; i < values.length; i++) {
    var k = String(values[i][0] || "").trim();
    if (!k) continue;
    cfg[k] = values[i][1];
  }
  return cfg;
}

function log_(level, fn, commentId, message) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName("ログ");
  if (!sh) return;
  sh.appendRow([new Date(), level, fn, commentId || "", message || ""]);
}

function buildIndex_(headers) {
  var idx = {};
  for (var i = 0; i < headers.length; i++) {
    var k = headers[i];
    if (k !== null && k !== "") idx[String(k).trim()] = i;
  }
  return idx;
}

function val_(row, index) {
  if (index === undefined || index === null) return "";
  return row[index];
}

function stripCodeFence_(txt) {
  var s = txt.trim();
  if (s.indexOf("```") === 0) {
    s = s.replace(/^```[a-zA-Z]*\n?/, "");
    s = s.replace(/```$/, "").trim();
  }
  return s;
}
