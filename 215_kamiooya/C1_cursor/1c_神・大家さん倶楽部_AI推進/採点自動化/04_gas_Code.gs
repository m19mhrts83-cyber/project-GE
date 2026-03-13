/**
 * WeStudy 採点自動化 (Google Apps Script)
 *
 * 前提シート:
 * - 設定
 * - 元データ
 * - 得点基準
 * - 採点結果
 * - ログ
 */

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("採点自動化")
    .addItem("CSV取込（Drive File ID）", "importCsvByConfig")
    .addItem("採点実行", "runScoring")
    .addItem("ヘッダー初期化", "initializeSheets")
    .addToUi();
}

function importCsvByConfig() {
  var cfg = readConfig_();
  var fileId = cfg.DRIVE_CSV_FILE_ID;
  if (!fileId) {
    throw new Error("設定シートに DRIVE_CSV_FILE_ID を設定してください。");
  }
  importCsvFromDrive_(fileId);
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
  var resultIndex = buildResultIndex_(resultSheet);
  var rulesText = buildRulesText_(rulesSheet);
  var apiKey = cfg.GEMINI_API_KEY;
  var model = cfg.GEMINI_MODEL || "gemini-2.0-flash";
  var maxRows = Number(cfg.MAX_ROWS_PER_RUN || 50);
  var includeReplies = String(cfg.INCLUDE_REPLIES || "FALSE").toUpperCase() === "TRUE";

  if (!apiKey) {
    throw new Error("設定シートに GEMINI_API_KEY を設定してください。");
  }

  var processed = 0;
  for (var r = 1; r < rows.length; r++) {
    if (processed >= maxRows) break;

    var row = rows[r];
    var commentId = val_(row, idx["コメントID"]);
    var parentId = val_(row, idx["親コメントID"]);
    var commentBody = val_(row, idx["コメント内容"]);
    var postedAt = val_(row, idx["投稿日時"]);
    var authorName = val_(row, idx["投稿者名"]);

    if (!commentId || !commentBody) continue;
    if (!includeReplies && parentId) continue;
    if (resultIndex[commentId]) continue; // すでに採点済み

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
        finalScore: result.score,
        version: "v1",
        scoredAt: new Date(),
        error: ""
      });
      processed++;
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
        finalScore: "",
        version: "v1",
        scoredAt: new Date(),
        error: String(err)
      });
      log_("ERROR", "runScoring", String(commentId), String(err));
    }
  }

  log_("INFO", "runScoring", "", "採点件数: " + processed);
}

function initializeSheets() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  var resultSheet = ss.getSheetByName("採点結果") || ss.insertSheet("採点結果");
  resultSheet.clearContents();
  resultSheet.appendRow([
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
  ]);

  var logSheet = ss.getSheetByName("ログ") || ss.insertSheet("ログ");
  logSheet.clearContents();
  logSheet.appendRow(["時刻", "レベル", "関数名", "コメントID", "メッセージ"]);
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
  log_("INFO", "importCsvFromDrive_", "", "CSV取り込み完了: " + file.getName());
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
    item.manualScore,
    item.finalScore,
    item.version,
    item.scoredAt,
    item.error
  ]);
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

