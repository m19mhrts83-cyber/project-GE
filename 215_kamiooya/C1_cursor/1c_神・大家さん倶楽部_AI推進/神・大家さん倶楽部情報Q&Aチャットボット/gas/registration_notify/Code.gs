/**
 * 神・大家さん倶楽部 Q&A — 登録・承認・パスワード再設定メール通知
 *
 * 配置: Google Apps Script プロジェクトに本ファイルを貼り付け
 * プロジェクト名案: kamiooya-qa-registration-notify
 *
 * スクリプトのプロパティ（プロジェクト設定 → スクリプト プロパティ）:
 *   SHARED_SECRET  … 呼び出し元と共有する秘密（必須）
 *   ADMIN_TO       … 承認依頼の宛先（type=registration 時必須）。複数はカンマ区切り
 *   APP_URL        … アプリURL。type=approval では必須。registration / password_reset では任意
 *
 * POST JSON:
 *   { secret, email, type?, member_no?, registered_at?, note?, ... }
 *   type 省略 / "registration" … 管理者へ承認依頼（member_no 任意・あれば本文に記載）
 *   type "approval"           … 申請者（email）へ承認完了＋APP_URL
 *   type "rejection"          … 申請者へ却下通知（固定文）
 *   type "password_reset"     … 申請者へ再設定URL（reset_url 必須、または APP_URL+token）
 *
 * デプロイ: デプロイ → 新しいデプロイ → 種類「ウェブアプリ」
 *   実行ユーザー: 自分 / アクセスできるユーザー: 全員
 * → ウェブアプリ URL を NOTIFY_WEBHOOK_URL に保存
 *
 * メールは plain + htmlBody の両方を送る（Gmail の狭い幅での不自然な折り返しを抑える）
 */

function doPost(e) {
  try {
    var props = PropertiesService.getScriptProperties();
    var sharedSecret = props.getProperty('SHARED_SECRET') || '';
    var adminTo = props.getProperty('ADMIN_TO') || '';
    var appUrl = props.getProperty('APP_URL') || '';

    if (!sharedSecret) {
      return json_(500, {
        ok: false,
        error: 'SCRIPT_PROPERTIES_MISSING',
        message: 'SHARED_SECRET をスクリプトプロパティに設定してください'
      });
    }

    var body = {};
    if (e && e.postData && e.postData.contents) {
      body = JSON.parse(e.postData.contents);
    }

    var gotSecret = String(body.secret || '');
    if (gotSecret !== sharedSecret) {
      return json_(401, { ok: false, error: 'UNAUTHORIZED' });
    }

    var notifyType = String(body.type || 'registration').trim().toLowerCase();
    if (
      notifyType !== 'registration' &&
      notifyType !== 'approval' &&
      notifyType !== 'rejection' &&
      notifyType !== 'password_reset'
    ) {
      return json_(400, { ok: false, error: 'INVALID_TYPE' });
    }

    var email = String(body.email || body.registrant_email || '').trim();
    if (!email) {
      return json_(400, { ok: false, error: 'EMAIL_REQUIRED' });
    }

    if (notifyType === 'approval') {
      return sendApprovalToApplicant_(email, appUrl);
    }
    if (notifyType === 'rejection') {
      return sendRejectionToApplicant_(email);
    }
    if (notifyType === 'password_reset') {
      return sendPasswordResetToApplicant_(email, appUrl, body);
    }
    return sendRegistrationToAdmin_(email, adminTo, appUrl, body);
  } catch (err) {
    return json_(500, {
      ok: false,
      error: 'INTERNAL',
      message: String(err && err.message ? err.message : err)
    });
  }
}

function sendRegistrationToAdmin_(registrantEmail, adminTo, appUrl, body) {
  if (!adminTo) {
    return json_(500, {
      ok: false,
      error: 'SCRIPT_PROPERTIES_MISSING',
      message: 'ADMIN_TO をスクリプトプロパティに設定してください'
    });
  }

  var registeredAt = String(body.registered_at || '').trim();
  var note = String(body.note || '').trim();
  var memberNo = String(body.member_no || body.memberNo || '').trim();
  var subject = '【神大家Q&A】新規登録の承認をお願いします';

  var parts = [];
  parts.push({
    lines: [
      '神・大家さん倶楽部 Q&Aチャットボットに',
      '新規登録がありました。'
    ]
  });
  parts.push({ lines: ['登録メール: ' + registrantEmail] });
  if (memberNo) {
    parts.push({ lines: ['会員番号: ' + memberNo] });
  }
  if (registeredAt) {
    parts.push({ lines: ['受付時刻: ' + registeredAt] });
  }
  if (note) {
    parts.push({ lines: ['メモ: ' + note] });
  }
  parts.push({
    lines: [
      'アプリに管理者でログインし、',
      '「ユーザー承認」から承認してください。'
    ]
  });
  if (appUrl) {
    parts.push({ lines: ['アプリURL:'], linkUrl: appUrl, linkLabel: appUrl });
  }
  parts.push({ lines: ['（このメールは自動送信です）'] });

  sendMail_(adminTo, subject, parts);
  return json_(200, { ok: true, type: 'registration' });
}

function sendApprovalToApplicant_(applicantEmail, appUrl) {
  if (!appUrl) {
    return json_(500, {
      ok: false,
      error: 'SCRIPT_PROPERTIES_MISSING',
      message: 'APP_URL をスクリプトプロパティに設定してください（承認完了メールに必須）'
    });
  }

  var subject = '【神大家Q&A】登録が承認されました';
  var parts = [
    {
      lines: [
        '神・大家さん倶楽部 Q&Aチャットボットへの',
        'ご登録が承認されました。'
      ]
    },
    {
      lines: [
        '承認が完了しました。',
        '以下のURLからアクセス（ログイン）して確認してください。'
      ]
    },
    { lines: [], linkUrl: appUrl, linkLabel: appUrl },
    { lines: ['（このメールは自動送信です）'] }
  ];

  sendMail_(applicantEmail, subject, parts);
  return json_(200, { ok: true, type: 'approval' });
}

function sendRejectionToApplicant_(applicantEmail) {
  var subject = '【神大家Q&A】登録申請が却下されました';
  // 狭い画面でも「ご登録申請は却下されました。」が途中で切れないよう、
  // こちらで自然な位置に改行を固定する。
  var parts = [
    {
      lines: [
        '神・大家さん倶楽部 Q&Aチャットボットへの',
        'ご登録申請は却下されました。'
      ]
    },
    {
      lines: [
        '神・大家さん倶楽部へ申請した',
        'メールアドレスで申請しているか、',
        '確認してください。'
      ]
    },
    { lines: ['（このメールは自動送信です）'] }
  ];

  sendMail_(applicantEmail, subject, parts);
  return json_(200, { ok: true, type: 'rejection' });
}

function sendPasswordResetToApplicant_(applicantEmail, appUrl, body) {
  var resetUrl = String(body.reset_url || '').trim();
  if (!resetUrl) {
    var token = String(body.token || '').trim();
    var base = String(appUrl || '').trim().replace(/\/+$/, '');
    if (base && token) {
      resetUrl = base + '/#reset-password?token=' + encodeURIComponent(token);
    }
  }
  if (!resetUrl) {
    return json_(400, {
      ok: false,
      error: 'RESET_URL_REQUIRED',
      message: 'reset_url（または APP_URL + token）が必要です'
    });
  }

  var expiresNote = String(body.expires_at || '').trim();
  var subject = '【神大家Q&A】パスワード再設定のご案内';
  var parts = [
    {
      lines: [
        '神・大家さん倶楽部 Q&Aチャットボットの',
        'パスワード再設定リクエストを受け付けました。'
      ]
    },
    {
      lines: ['以下のURLから、新しいパスワードを設定してください。']
    },
    { lines: [], linkUrl: resetUrl, linkLabel: resetUrl }
  ];
  if (expiresNote) {
    parts.push({
      lines: [
        '有効期限: ' + expiresNote + 'まで',
        '（期限を過ぎるとリンクは使えません）'
      ]
    });
  } else {
    parts.push({
      lines: [
        'リンクの有効期限は、',
        '発行日の1週間後・日本時間23:59までです。'
      ]
    });
  }
  parts.push({
    lines: [
      '心当たりがない場合は、このメールを無視してください。',
      'パスワードは変更されません。'
    ]
  });
  parts.push({ lines: ['（このメールは自動送信です）'] });

  sendMail_(applicantEmail, subject, parts);
  return json_(200, { ok: true, type: 'password_reset' });
}

/**
 * plain + HTML の両方で送信。
 * parts: [{ lines: string[], linkUrl?: string, linkLabel?: string }]
 * lines の区切りは <br> / 改行で固定（Gmail の自動折り返し位置を制御するため）
 */
function sendMail_(to, subject, parts) {
  var plainBlocks = [];
  var htmlBlocks = [];

  for (var i = 0; i < parts.length; i++) {
    var part = parts[i] || {};
    var lines = part.lines || [];
    if (!lines.length && part.text) {
      lines = [String(part.text)];
    }

    var plainText = lines.join('\n');
    var htmlText = '';
    for (var j = 0; j < lines.length; j++) {
      if (j > 0) htmlText += '<br>';
      htmlText += escapeHtml_(lines[j]);
    }

    if (part.linkUrl) {
      var href = String(part.linkUrl);
      var label = String(part.linkLabel || part.linkUrl);
      if (plainText) {
        plainBlocks.push(plainText + '\n' + href);
      } else {
        plainBlocks.push(href);
      }
      htmlBlocks.push(
        '<p style="margin:0 0 16px 0;line-height:1.75;">' +
          (htmlText ? htmlText + '<br>' : '') +
          '<a href="' +
          escapeHtml_(href) +
          '" style="word-break:break-all;">' +
          escapeHtml_(label) +
          '</a></p>'
      );
    } else {
      plainBlocks.push(plainText);
      htmlBlocks.push(
        '<p style="margin:0 0 16px 0;line-height:1.75;">' + htmlText + '</p>'
      );
    }
  }

  var htmlBody =
    '<div style="font-family:sans-serif;font-size:15px;color:#222;line-height:1.75;">' +
    htmlBlocks.join('') +
    '</div>';

  MailApp.sendEmail({
    to: to,
    subject: subject,
    body: plainBlocks.join('\n\n'),
    htmlBody: htmlBody
  });
}

function escapeHtml_(s) {
  return String(s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** ブラウザで開いたときの簡易ヘルスチェック */
function doGet() {
  return json_(200, {
    ok: true,
    service: 'kamiooya-qa-registration-notify',
    hint: 'POST JSON { secret, email, type?: registration|approval|rejection|password_reset }'
  });
}

function json_(status, obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(
    ContentService.MimeType.JSON
  );
}
