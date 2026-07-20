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
 *   { secret, email, type? }
 *   type 省略 / "registration" … 管理者へ承認依頼
 *   type "approval"           … 申請者（email）へ承認完了＋APP_URL
 *   type "password_reset"     … 申請者へ再設定URL（reset_url 必須、または APP_URL+token）
 *
 * デプロイ: デプロイ → 新しいデプロイ → 種類「ウェブアプリ」
 *   実行ユーザー: 自分 / アクセスできるユーザー: 全員
 * → ウェブアプリ URL を NOTIFY_WEBHOOK_URL に保存
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

  var subject = '【神大家Q&A】新規登録の承認をお願いします';
  var lines = [
    '神・大家さん倶楽部 情報Q&Aチャットボットに新規登録がありました。',
    '',
    '登録メール: ' + registrantEmail,
    registeredAt ? '受付時刻: ' + registeredAt : '',
    note ? 'メモ: ' + note : '',
    '',
    'アプリに管理者でログインし、「ユーザー承認」から承認してください。',
    appUrl ? 'アプリURL: ' + appUrl : '',
    '',
    '（このメールは自動送信です）'
  ].filter(function (x) {
    return x !== '';
  });

  MailApp.sendEmail({
    to: adminTo,
    subject: subject,
    body: lines.join('\n')
  });

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
  var lines = [
    '神・大家さん倶楽部 情報Q&Aチャットボットへのご登録が承認されました。',
    '',
    '承認が完了しました。以下のURLからアクセス（ログイン）して確認してください。',
    '',
    appUrl,
    '',
    '（このメールは自動送信です）'
  ];

  MailApp.sendEmail({
    to: applicantEmail,
    subject: subject,
    body: lines.join('\n')
  });

  return json_(200, { ok: true, type: 'approval' });
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
  var lines = [
    '神・大家さん倶楽部 情報Q&Aチャットボットのパスワード再設定リクエストを受け付けました。',
    '',
    '以下のURLから、新しいパスワードを設定してください。',
    '',
    resetUrl,
    '',
    expiresNote
      ? '有効期限: ' + expiresNote + 'まで（期限を過ぎるとリンクは使えません）'
      : 'リンクの有効期限は、発行日の1週間後・日本時間23:59までです。',
    '',
    '心当たりがない場合は、このメールを無視してください。パスワードは変更されません。',
    '',
    '（このメールは自動送信です）'
  ];

  MailApp.sendEmail({
    to: applicantEmail,
    subject: subject,
    body: lines.join('\n')
  });

  return json_(200, { ok: true, type: 'password_reset' });
}

/** ブラウザで開いたときの簡易ヘルスチェック */
function doGet() {
  return json_(200, {
    ok: true,
    service: 'kamiooya-qa-registration-notify',
    hint: 'POST JSON { secret, email, type?: registration|approval|password_reset }'
  });
}

function json_(status, obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(
    ContentService.MimeType.JSON
  );
}
