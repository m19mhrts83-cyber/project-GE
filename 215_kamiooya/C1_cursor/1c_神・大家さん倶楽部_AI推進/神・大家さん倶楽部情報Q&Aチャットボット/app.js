const App = {
  state: {
    currentUser: null,
    currentSessionId: null,
    chatSessions: [],
    chatMessages: [],
    suggestedQuestions: [],
    comments: [],
    knowledgeChunks: [],
    knowledgeSources: {},
    lastCitations: [],
    forumCategoryLookup: null,
    pendingUsers: [],
    currentScreen: 'chat',
    returnScreen: null,
    loadingCount: 0,
    resetPasswordEmail: '',
    resetPasswordToken: ''
  },

  elements: {},

  apiClient: async (method, endpoint, body = null) => {
    const url = '/miniAppApi/be_nXbcTm3EumRbotHtAwGGXb45raHz0' + endpoint;
    const options = {
      method: method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (body) options.body = JSON.stringify(body);
    try {
      const response = await fetch(url, options);
      if (!response.ok) {
        const text = await response.text();
        let errorData = {};
        if (text) {
          try {
            errorData = JSON.parse(text);
          } catch (parseErr) {
            errorData = { _rawBody: text };
          }
        }
        const msg =
          errorData.errorMessage ||
          errorData.message ||
          errorData.error ||
          (typeof errorData.detail === 'string' ? errorData.detail : '') ||
          (errorData._rawBody ? String(errorData._rawBody).trim().slice(0, 280) : '');
        const suffix = response.status ? '（HTTP ' + response.status + '）' : '';
        const apiErr = new Error((msg || 'APIエラーが発生しました') + suffix);
        const code = errorData.errorCode || errorData.error_code;
        if (code) {
          apiErr.errorCode = code;
        }
        throw apiErr;
      }
      if (response.status === 204) return null;
      return await response.json();
    } catch (error) {
      console.error('API Error:', error);
      throw error;
    }
  },

  parseAnalysisJson: (jsonString) => {
    try {
      if (typeof jsonString === 'object') return jsonString;
      let cleaned = jsonString.trim();
      if (cleaned.startsWith('```json')) cleaned = cleaned.slice(7);
      if (cleaned.startsWith('```')) cleaned = cleaned.slice(3);
      if (cleaned.endsWith('```')) cleaned = cleaned.slice(0, -3);
      return JSON.parse(cleaned.trim());
    } catch (e) {
      console.error('JSON Parse Error:', e);
      throw new Error('JSONの解析に失敗しました');
    }
  },

  escapeHtml: (str) => {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  },

  /* 改修: シークレットURL時は管理者登録画面を表示。Phase4: #reset-password?token= */
  init: () => {
    App.cacheElements();
    App.bindEvents();
    if (App.isSecretAdminRoute()) {
      App.showSecretAdminRegisterView();
      return;
    }
    const resetToken = App.parseResetPasswordTokenFromHash();
    if (resetToken) {
      App.openResetPasswordFromToken(resetToken);
      return;
    }
    App.showAuthView();
  },

  /* 改修: 管理者ゲート用 dialog 等の要素参照 */
  cacheElements: () => {
    App.elements.authView = document.getElementById('authView');
    App.elements.mainView = document.getElementById('mainView');
    App.elements.forgotPasswordView = document.getElementById('forgotPasswordView');
    App.elements.resetPasswordView = document.getElementById('resetPasswordView');
    App.elements.forgotPasswordForm = document.getElementById('forgotPasswordForm');
    App.elements.resetPasswordForm = document.getElementById('resetPasswordForm');
    App.elements.forgotPasswordSubmitBtn = document.getElementById('forgotPasswordSubmitBtn');
    App.elements.resetPasswordSubmitBtn = document.getElementById('resetPasswordSubmitBtn');
    App.elements.secretAdminRegisterView = document.getElementById('secretAdminRegisterView');
    App.elements.secretAdminRegisterForm = document.getElementById('secretAdminRegisterForm');
    App.elements.secretAdminRegisterSubmitBtn = document.getElementById('secretAdminRegisterSubmitBtn');
    App.elements.adminEntryBtn = document.getElementById('adminEntryBtn');
    App.elements.loginScreenAdminRegisterBtn = document.getElementById('loginScreenAdminRegisterBtn');
    App.elements.adminGateOverlay = document.getElementById('adminGateOverlay');
    App.elements.adminGatePasswordInput = document.getElementById('adminGatePasswordInput');
    App.elements.adminGateError = document.getElementById('adminGateError');
    App.elements.adminGateCancelBtn = document.getElementById('adminGateCancelBtn');
    App.elements.adminGateOkBtn = document.getElementById('adminGateOkBtn');
    App.elements.loginForm = document.getElementById('loginForm');
    App.elements.registerForm = document.getElementById('registerForm');
    App.elements.loginSubmitBtn = document.getElementById('loginSubmitBtn');
    App.elements.registerSubmitBtn = document.getElementById('registerSubmitBtn');
    App.elements.currentUserLabel = document.getElementById('currentUserLabel');
    App.elements.sidebar = document.getElementById('sidebar');
    App.elements.sessionList = document.getElementById('sessionList');
    App.elements.chatMessages = document.getElementById('chatMessages');
    App.elements.messageForm = document.getElementById('messageForm');
    App.elements.messageInput = document.getElementById('messageInput');
    App.elements.sendMessageBtn = document.getElementById('sendMessageBtn');
    App.elements.suggestedQuestions = document.getElementById('suggestedQuestions');
    App.elements.commentTableBody = document.getElementById('commentTableBody');
    App.elements.commentSearchInput = document.getElementById('commentSearchInput');
    App.elements.commentSourceFilter = document.getElementById('commentSourceFilter');
    App.elements.commentCategoryFilter = document.getElementById('commentCategoryFilter');
    App.elements.commentDateFilter = document.getElementById('commentDateFilter');
    App.elements.commentListMeta = document.getElementById('commentListMeta');
    App.elements.knowledgeTableBody = document.getElementById('knowledgeTableBody');
    App.elements.knowledgeSearchInput = document.getElementById('knowledgeSearchInput');
    App.elements.knowledgeListMeta = document.getElementById('knowledgeListMeta');
    App.elements.pendingUsersTableBody = document.getElementById('pendingUsersTableBody');
    App.elements.pendingUsersSelectAll = document.getElementById('pendingUsersSelectAll');
    App.elements.bulkApprovePendingUsersBtn = document.getElementById('bulkApprovePendingUsersBtn');
    App.elements.csvFileInput = document.getElementById('csvFileInput');
    App.elements.importResult = document.getElementById('importResult');
    App.elements.toast = document.getElementById('toast');
    App.elements.loadingOverlay = document.getElementById('loadingOverlay');
    App.elements.confirmDialog = document.getElementById('confirmDialog');
    App.elements.confirmTitle = document.getElementById('confirmTitle');
    App.elements.confirmMessage = document.getElementById('confirmMessage');
    App.elements.confirmOkBtn = document.getElementById('confirmOkBtn');
    App.elements.confirmCancelBtn = document.getElementById('confirmCancelBtn');
    App.elements.deleteSourceTypeInput = document.getElementById('deleteSourceTypeInput');
    App.elements.deleteCommentIdLikeInput = document.getElementById('deleteCommentIdLikeInput');
    App.elements.deleteCommentsBtn = document.getElementById('deleteCommentsBtn');
    App.elements.commentsBackBar = document.getElementById('commentsBackBar');
    App.elements.commentsBackBtn = document.getElementById('commentsBackBtn');
    App.elements.commentsBackLabel = document.getElementById('commentsBackLabel');
    App.elements.knowledgeBackBar = document.getElementById('knowledgeBackBar');
    App.elements.knowledgeBackBtn = document.getElementById('knowledgeBackBtn');
    App.elements.knowledgeBackLabel = document.getElementById('knowledgeBackLabel');
  },

  /* 改修: 管理者登録クリックでパスワードモーダルを開く */
  bindEvents: () => {
    document.getElementById('showLoginTabBtn').addEventListener('click', App.showLoginTab);
    document.getElementById('showRegisterTabBtn').addEventListener('click', App.showRegisterTab);
    App.elements.loginForm.addEventListener('submit', App.handleLogin);
    App.elements.registerForm.addEventListener('submit', App.handleRegister);
    const toForgotBtn = document.getElementById('toForgotPasswordBtn');
    if (toForgotBtn) {
      toForgotBtn.addEventListener('click', App.showForgotPasswordView);
    }
    if (App.elements.forgotPasswordForm) {
      App.elements.forgotPasswordForm.addEventListener('submit', App.handleForgotPasswordEmail);
    }
    if (App.elements.resetPasswordForm) {
      App.elements.resetPasswordForm.addEventListener('submit', App.handleResetPassword);
    }
    const forgotBackBtn = document.getElementById('forgotPasswordBackToLoginBtn');
    if (forgotBackBtn) {
      forgotBackBtn.addEventListener('click', function () {
        App.state.resetPasswordEmail = '';
        App.state.resetPasswordToken = '';
        App.showAuthView();
        App.showLoginTab();
      });
    }
    const resetBackBtn = document.getElementById('resetPasswordBackToLoginBtn');
    if (resetBackBtn) {
      resetBackBtn.addEventListener('click', function () {
        App.state.resetPasswordEmail = '';
        App.state.resetPasswordToken = '';
        App.clearResetPasswordHash();
        App.showAuthView();
        App.showLoginTab();
      });
    }
    if (App.elements.secretAdminRegisterForm) {
      App.elements.secretAdminRegisterForm.addEventListener('submit', App.handleSecretAdminRegister);
    }
    const secretBackBtn = document.getElementById('secretAdminBackToLoginBtn');
    if (secretBackBtn) {
      secretBackBtn.addEventListener('click', function () {
        App.showAuthView();
        App.showLoginTab();
      });
    }
    /* 改修: キャプチャ段階で委譲し、他要素の stopPropagation や古いバインドでも確実に発火 */
    document.addEventListener(
      'click',
      function (ev) {
        const t = ev.target;
        if (!t || typeof t.closest !== 'function') return;
        if (t.closest('#adminEntryBtn') || t.closest('#loginScreenAdminRegisterBtn')) {
          ev.preventDefault();
          App.openAdminGateDialog();
        }
      },
      true
    );
    if (App.elements.adminGateOverlay) {
      App.elements.adminGateOverlay.addEventListener('click', function (e) {
        if (e.target === App.elements.adminGateOverlay) {
          App.closeAdminGateDialog();
        }
      });
    }
    if (App.elements.adminGateCancelBtn) {
      App.elements.adminGateCancelBtn.addEventListener('click', App.closeAdminGateDialog);
    }
    if (App.elements.adminGateOkBtn) {
      App.elements.adminGateOkBtn.addEventListener('click', App.handleAdminGateSubmit);
    }
    if (App.elements.adminGatePasswordInput) {
      App.elements.adminGatePasswordInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          App.handleAdminGateSubmit();
        }
      });
    }
    document.addEventListener('keydown', App.onAdminGateEscape, true);
    document.getElementById('logoutBtn').addEventListener('click', App.logout);
    document.getElementById('newChatBtn').addEventListener('click', App.createNewChatPlaceholder);
    App.elements.messageForm.addEventListener('submit', App.handleSendMessage);
    document.getElementById('reloadCommentsBtn').addEventListener('click', App.loadComments);
    const reloadKnowledgeBtn = document.getElementById('reloadKnowledgeBtn');
    if (reloadKnowledgeBtn) reloadKnowledgeBtn.addEventListener('click', App.loadKnowledge);
    document.getElementById('reloadPendingUsersBtn').addEventListener('click', App.loadPendingUsers);
    if (App.elements.bulkApprovePendingUsersBtn) {
      App.elements.bulkApprovePendingUsersBtn.addEventListener('click', App.confirmBulkApproveUsers);
    }
    if (App.elements.pendingUsersSelectAll) {
      App.elements.pendingUsersSelectAll.addEventListener('change', function () {
        const checked = !!App.elements.pendingUsersSelectAll.checked;
        App.elements.pendingUsersTableBody.querySelectorAll('.pending-user-check').forEach(function (cb) {
          cb.checked = checked;
        });
        App.updateBulkApproveButtonState();
      });
    }
    document.getElementById('sampleCommentBtn').addEventListener('click', App.createSampleComment);
    document.getElementById('importCsvBtn').addEventListener('click', App.importCsvComments);
    document.getElementById('sidebarToggleBtn').addEventListener('click', App.toggleSidebarMobile);
    document.getElementById('commentSearchInput').addEventListener('input', App.renderCommentTable);
    if (App.elements.knowledgeSearchInput) {
      App.elements.knowledgeSearchInput.addEventListener('input', App.renderKnowledgeTable);
    }
    if (App.elements.commentSourceFilter) {
      App.elements.commentSourceFilter.addEventListener('change', App.renderCommentTable);
    }
    if (App.elements.commentCategoryFilter) {
      App.elements.commentCategoryFilter.addEventListener('change', App.renderCommentTable);
    }
    if (App.elements.commentDateFilter) {
      App.elements.commentDateFilter.addEventListener('change', App.renderCommentTable);
    }
    if (App.elements.deleteCommentsBtn) {
      App.elements.deleteCommentsBtn.addEventListener('click', App.deleteComments);
    }
    document.getElementById('confirmCancelBtn').addEventListener('click', App.closeConfirmDialog);
    document.querySelectorAll('.screen-tab').forEach(function (btn) {
      btn.addEventListener('click', function () {
        App.switchScreen(btn.getAttribute('data-screen'), { fromNav: true });
      });
    });
    if (App.elements.commentsBackBtn) {
      App.elements.commentsBackBtn.addEventListener('click', App.goBackFromDbScreen);
    }
    if (App.elements.knowledgeBackBtn) {
      App.elements.knowledgeBackBtn.addEventListener('click', App.goBackFromDbScreen);
    }
  },

  setLoading: (isLoading) => {
    if (isLoading) App.state.loadingCount += 1;
    if (!isLoading) App.state.loadingCount = Math.max(0, App.state.loadingCount - 1);
    if (App.state.loadingCount > 0) App.elements.loadingOverlay.classList.add('active');
    if (App.state.loadingCount === 0) App.elements.loadingOverlay.classList.remove('active');
  },

  setButtonLoading: (buttonEl, isLoading, loadingText) => {
    if (!buttonEl) return;
    if (isLoading) {
      buttonEl.disabled = true;
      buttonEl.dataset.originalText = buttonEl.innerHTML;
      buttonEl.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-1"></i>' + App.escapeHtml(loadingText || '処理中');
    } else {
      buttonEl.disabled = false;
      if (buttonEl.dataset.originalText) {
        buttonEl.innerHTML = buttonEl.dataset.originalText;
      }
    }
  },

  showToast: (message, type) => {
    App.elements.toast.textContent = message || '';
    App.elements.toast.className = 'toast ' + (type || 'info');
    App.elements.toast.classList.remove('hidden');
    window.setTimeout(function () {
      App.elements.toast.classList.add('hidden');
    }, 2600);
  },

  /* 改修: 認証画面表示時に管理者登録・再設定ビューを隠す */
  showAuthView: () => {
    App.elements.authView.classList.remove('hidden');
    App.elements.mainView.classList.add('hidden');
    if (App.elements.secretAdminRegisterView) {
      App.elements.secretAdminRegisterView.classList.add('hidden');
    }
    if (App.elements.forgotPasswordView) {
      App.elements.forgotPasswordView.classList.add('hidden');
    }
    if (App.elements.resetPasswordView) {
      App.elements.resetPasswordView.classList.add('hidden');
    }
  },

  showMainView: () => {
    App.elements.authView.classList.add('hidden');
    App.elements.mainView.classList.remove('hidden');
    if (App.elements.secretAdminRegisterView) {
      App.elements.secretAdminRegisterView.classList.add('hidden');
    }
    if (App.elements.forgotPasswordView) {
      App.elements.forgotPasswordView.classList.add('hidden');
    }
    if (App.elements.resetPasswordView) {
      App.elements.resetPasswordView.classList.add('hidden');
    }
  },

  showSecretAdminRegisterView: () => {
    App.elements.authView.classList.add('hidden');
    App.elements.mainView.classList.add('hidden');
    if (App.elements.forgotPasswordView) {
      App.elements.forgotPasswordView.classList.add('hidden');
    }
    if (App.elements.resetPasswordView) {
      App.elements.resetPasswordView.classList.add('hidden');
    }
    if (App.elements.secretAdminRegisterView) {
      App.elements.secretAdminRegisterView.classList.remove('hidden');
    }
  },

  showForgotPasswordView: () => {
    App.state.resetPasswordEmail = '';
    App.state.resetPasswordToken = '';
    App.elements.authView.classList.add('hidden');
    App.elements.mainView.classList.add('hidden');
    if (App.elements.secretAdminRegisterView) {
      App.elements.secretAdminRegisterView.classList.add('hidden');
    }
    if (App.elements.resetPasswordView) {
      App.elements.resetPasswordView.classList.add('hidden');
    }
    if (App.elements.forgotPasswordForm) {
      App.elements.forgotPasswordForm.reset();
    }
    if (App.elements.forgotPasswordView) {
      App.elements.forgotPasswordView.classList.remove('hidden');
    }
  },

  showResetPasswordView: (email, token) => {
    App.state.resetPasswordEmail = email || '';
    App.state.resetPasswordToken = token || '';
    App.elements.authView.classList.add('hidden');
    App.elements.mainView.classList.add('hidden');
    if (App.elements.secretAdminRegisterView) {
      App.elements.secretAdminRegisterView.classList.add('hidden');
    }
    if (App.elements.forgotPasswordView) {
      App.elements.forgotPasswordView.classList.add('hidden');
    }
    const display = document.getElementById('resetPasswordEmailDisplay');
    if (display) {
      display.textContent = App.state.resetPasswordEmail;
    }
    if (App.elements.resetPasswordForm) {
      App.elements.resetPasswordForm.reset();
    }
    if (App.elements.resetPasswordView) {
      App.elements.resetPasswordView.classList.remove('hidden');
    }
  },

  parseResetPasswordTokenFromHash: () => {
    const hash = String(window.location.hash || '');
    if (!hash) return '';
    const body = hash.replace(/^#/, '');
    if (!body) return '';
    let path = body;
    let query = '';
    const qIdx = body.indexOf('?');
    if (qIdx >= 0) {
      path = body.slice(0, qIdx);
      query = body.slice(qIdx + 1);
    }
    if (path !== 'reset-password') return '';
    const params = new URLSearchParams(query);
    return (params.get('token') || '').trim();
  },

  clearResetPasswordHash: () => {
    if (!App.parseResetPasswordTokenFromHash()) return;
    const url = window.location.pathname + window.location.search;
    window.history.replaceState(null, '', url);
  },

  buildPasswordResetUrl: (token) => {
    const base = (window.location.origin + window.location.pathname).replace(/\/+$/, '') + '/';
    return base + '#reset-password?token=' + encodeURIComponent(token);
  },

  /** 日本時間のカレンダー日付部品を取得 */
  jstYmdParts: (date) => {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Tokyo',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit'
    }).formatToParts(date || new Date());
    const pick = function (type) {
      const hit = parts.find(function (p) {
        return p.type === type;
      });
      return hit ? Number(hit.value) : 0;
    };
    return { y: pick('year'), m: pick('month'), d: pick('day') };
  },

  /**
   * 有効期限: 日本時間で「今日＋7日」の 23:59 まで（その日いっぱい）。
   * iso … DB保存用 / display … メール表記用
   */
  buildPasswordResetExpiry: () => {
    const today = App.jstYmdParts(new Date());
    const anchor = new Date(Date.UTC(today.y, today.m - 1, today.d));
    anchor.setUTCDate(anchor.getUTCDate() + 7);
    const y = anchor.getUTCFullYear();
    const m = anchor.getUTCMonth() + 1;
    const d = anchor.getUTCDate();
    // 23:59:59.999 JST = 同日 14:59:59.999 UTC
    const expires = new Date(Date.UTC(y, m - 1, d, 14, 59, 59, 999));
    return {
      iso: expires.toISOString(),
      display: y + '年' + m + '月' + d + '日 23:59（日本時間）'
    };
  },

  openResetPasswordFromToken: async (token) => {
    App.setLoading(true);
    try {
      const res = await App.apiClient('POST', '/auth/forgot-password/validate', {
        token: token
      });
      const email = (res && res.email) || '';
      const expiresAt = (res && res.expires_at) || '';
      if (expiresAt && Date.parse(expiresAt) <= Date.now()) {
        throw new Error('再設定リンクの有効期限が切れています。もう一度メールアドレスからやり直してください');
      }
      App.showResetPasswordView(email, token);
    } catch (error) {
      App.clearResetPasswordHash();
      App.showAuthView();
      App.showToast(error.message || '再設定リンクが無効です', 'error');
    } finally {
      App.setLoading(false);
    }
  },

  handleForgotPasswordEmail: async (event) => {
    event.preventDefault();
    const email = (document.getElementById('forgotPasswordEmail').value || '').trim();
    if (!email) {
      App.showToast('メールアドレスは必須です', 'error');
      return;
    }
    App.setButtonLoading(App.elements.forgotPasswordSubmitBtn, true, '送信中');
    App.setLoading(true);
    try {
      await App.apiClient('POST', '/auth/reset-password/check', { email: email });
      const token =
        (window.crypto && typeof window.crypto.randomUUID === 'function'
          ? window.crypto.randomUUID()
          : 'rp-' + Date.now() + '-' + Math.random().toString(36).slice(2, 12));
      const expiry = App.buildPasswordResetExpiry();
      await App.apiClient('POST', '/auth/forgot-password/issue', {
        email: email,
        token: token,
        expires_at: expiry.iso
      });
      const resetUrl = App.buildPasswordResetUrl(token);
      await App.notifyPasswordReset(email, resetUrl, expiry.display);
      App.showToast('再設定用のURLをメールで送信しました', 'success');
    } catch (error) {
      App.showToast(error.message || 'メールアドレスの確認に失敗しました', 'error');
    } finally {
      App.setButtonLoading(App.elements.forgotPasswordSubmitBtn, false);
      App.setLoading(false);
    }
  },

  /** Phase 4: 再設定メール。失敗しても throw しない（issue 済みは成功扱い）。 */
  notifyPasswordReset: async (email, resetUrl, expiresAt) => {
    try {
      await App.apiClient('POST', '/notify/password-reset', {
        email: email,
        reset_url: resetUrl,
        expires_at: expiresAt || ''
      });
    } catch (notifyErr) {
      console.warn('password-reset notify failed (issue still OK):', notifyErr);
    }
  },

  handleResetPassword: async (event) => {
    event.preventDefault();
    const email = App.state.resetPasswordEmail || '';
    const token = App.state.resetPasswordToken || '';
    const password = document.getElementById('resetPasswordNewPassword').value;
    const confirm = document.getElementById('resetPasswordConfirmPassword').value;
    if (!token) {
      App.showToast('再設定リンクが無効です。メールのURLから開き直してください', 'error');
      App.showForgotPasswordView();
      return;
    }
    if (!password || !confirm) {
      App.showToast('新しいパスワードを入力してください', 'error');
      return;
    }
    if (password !== confirm) {
      App.showToast('パスワードが一致しません', 'error');
      return;
    }
    if (password.length < 4) {
      App.showToast('パスワードは4文字以上にしてください', 'error');
      return;
    }
    App.setButtonLoading(App.elements.resetPasswordSubmitBtn, true, '再設定中');
    App.setLoading(true);
    try {
      const res = await App.apiClient('POST', '/auth/reset-password', {
        token: token,
        password_hash: password
      });
      const confirmedEmail = (res && res.email) || email;
      App.state.resetPasswordEmail = '';
      App.state.resetPasswordToken = '';
      App.clearResetPasswordHash();
      App.showToast('パスワードを再設定しました。新しいパスワードでログインしてください', 'success');
      App.showAuthView();
      App.showLoginTab();
      const loginEmail = document.getElementById('loginEmail');
      if (loginEmail && confirmedEmail) {
        loginEmail.value = confirmedEmail;
      }
      const loginPassword = document.getElementById('loginPassword');
      if (loginPassword) {
        loginPassword.value = '';
        loginPassword.focus();
      }
    } catch (error) {
      App.showToast(error.message || 'パスワードの再設定に失敗しました', 'error');
    } finally {
      App.setButtonLoading(App.elements.resetPasswordSubmitBtn, false);
      App.setLoading(false);
    }
  },

  isSecretAdminRoute: () => {
    const p = window.location.pathname.replace(/\/+$/, '') || '/';
    return /(^|\/)secret-admin-register$/.test(p);
  },

  onAdminGateEscape: (e) => {
    if (e.key !== 'Escape') return;
    if (!App.elements.adminGateOverlay || App.elements.adminGateOverlay.classList.contains('hidden')) return;
    e.preventDefault();
    App.closeAdminGateDialog();
  },

  openAdminGateDialog: () => {
    if (!App.elements.adminGateOverlay) {
      App.showToast('パスワード入力画面を表示できません', 'error');
      return;
    }
    if (App.elements.adminGatePasswordInput) {
      App.elements.adminGatePasswordInput.value = '';
    }
    if (App.elements.adminGateError) {
      App.elements.adminGateError.textContent = '';
    }
    App.elements.adminGateOverlay.classList.remove('hidden');
    window.setTimeout(function () {
      if (App.elements.adminGatePasswordInput) {
        App.elements.adminGatePasswordInput.focus();
      }
    }, 0);
  },

  closeAdminGateDialog: () => {
    if (!App.elements.adminGateOverlay) return;
    App.elements.adminGateOverlay.classList.add('hidden');
  },

  handleAdminGateSubmit: () => {
    if (!App.elements.adminGatePasswordInput) return;
    const value = (App.elements.adminGatePasswordInput.value || '').trim();
    if (value !== '1162') {
      if (App.elements.adminGateError) {
        App.elements.adminGateError.textContent = 'パスワードが一致しません';
      }
      return;
    }
    App.closeAdminGateDialog();
    /* サーバーに /secret-admin-register が無い環境でも 404 にならないよう、同一ページ内で表示 */
    App.showSecretAdminRegisterView();
  },

  showLoginTab: () => {
    document.getElementById('showLoginTabBtn').className = 'w-1/2 py-2 rounded-md bg-blue-900 text-white';
    document.getElementById('showRegisterTabBtn').className = 'w-1/2 py-2 rounded-md bg-slate-200 text-slate-700';
    App.elements.loginForm.classList.remove('hidden');
    App.elements.registerForm.classList.add('hidden');
  },

  showRegisterTab: () => {
    document.getElementById('showRegisterTabBtn').className = 'w-1/2 py-2 rounded-md bg-blue-900 text-white';
    document.getElementById('showLoginTabBtn').className = 'w-1/2 py-2 rounded-md bg-slate-200 text-slate-700';
    App.elements.registerForm.classList.remove('hidden');
    App.elements.loginForm.classList.add('hidden');
  },

  handleRegister: async (event) => {
    event.preventDefault();
    const email = document.getElementById('registerEmail').value.trim();
    const password = document.getElementById('registerPassword').value;
    if (!email || !password) {
      App.showToast('メールアドレスとパスワードは必須です', 'error');
      return;
    }

    App.setButtonLoading(App.elements.registerSubmitBtn, true, '登録中');
    App.setLoading(true);
    try {
      await App.apiClient('POST', '/auth/register', {
        email: email,
        password_hash: password
      });
      // 通知失敗でも登録は成功扱い（専用 API・分離）
      await App.notifyRegistrationPending(email, '新規登録（アプリ）');
      App.showToast('登録申請を受け付けました（承認待ち）', 'success');
      App.showLoginTab();
      App.elements.registerForm.reset();
    } catch (error) {
      App.showToast(error.message || '登録に失敗しました', 'error');
    } finally {
      App.setButtonLoading(App.elements.registerSubmitBtn, false);
      App.setLoading(false);
    }
  },

  /** Phase 2: 承認依頼メール。失敗しても throw しない。 */
  notifyRegistrationPending: async (email, note) => {
    try {
      const registeredAt =
        new Date().toLocaleString('ja-JP', { timeZone: 'Asia/Tokyo' }) + ' JST';
      await App.apiClient('POST', '/notify/registration', {
        email: email,
        registered_at: registeredAt,
        note: note || ''
      });
    } catch (notifyErr) {
      console.warn('registration notify failed (registration still OK):', notifyErr);
    }
  },

  handleSecretAdminRegister: async (event) => {
    event.preventDefault();
    const email = document.getElementById('secretAdminEmail').value.trim();
    const password = document.getElementById('secretAdminPassword').value;
    const secretKey = document.getElementById('secretAdminSecretKey').value.trim();

    if (!email || !password || !secretKey) {
      App.showToast('メール・パスワード・シークレットキーは必須です', 'error');
      return;
    }

    App.setButtonLoading(App.elements.secretAdminRegisterSubmitBtn, true, '登録中');
    App.setLoading(true);
    const adminBody = {
      email: email,
      password_hash: password,
      secret_key: secretKey
    };
    try {
      /* 既存メール（一般登録済み等）は INSERT で重複エラーになるため、先に昇格APIを試す */
      try {
        await App.apiClient('POST', '/auth/secret-admin-upgrade', adminBody);
      } catch (upgradeErr) {
        const msg = upgradeErr.message || '';
        const isUnregistered =
          upgradeErr.errorCode === 'user_not_found' ||
          msg.indexOf('未登録') !== -1;
        /* 未デプロイ・エンジン不整合で upgrade が 404/500 のときも新規登録を試す（既存メールは register が失敗し得る） */
        const tryRegisterFallback =
          isUnregistered ||
          msg.indexOf('HTTP 404') !== -1 ||
          msg.indexOf('HTTP 500') !== -1 ||
          msg.indexOf('HTTP 502') !== -1;
        if (!tryRegisterFallback) {
          throw upgradeErr;
        }
        await App.apiClient('POST', '/auth/secret-admin-register', adminBody);
      }
      App.showToast('管理者登録が完了しました', 'success');
      App.elements.secretAdminRegisterForm.reset();
      App.showAuthView();
      App.showLoginTab();
    } catch (error) {
      App.showToast(error.message || '管理者登録に失敗しました', 'error');
    } finally {
      App.setButtonLoading(App.elements.secretAdminRegisterSubmitBtn, false);
      App.setLoading(false);
    }
  },

  handleLogin: async (event) => {
    event.preventDefault();
    const email = document.getElementById('loginEmail').value.trim();
    const password = document.getElementById('loginPassword').value;
    if (!email || !password) {
      App.showToast('メールアドレスとパスワードは必須です', 'error');
      return;
    }

    App.setButtonLoading(App.elements.loginSubmitBtn, true, 'ログイン中');
    App.setLoading(true);
    try {
      const res = await App.apiClient('POST', '/auth/login', {
        email: email,
        password_hash: password
      });
      App.state.currentUser = res.user;
      App.afterLogin();
      App.showToast('ログインしました', 'success');
    } catch (error) {
      App.showToast(error.message || 'ログインに失敗しました', 'error');
    } finally {
      App.setButtonLoading(App.elements.loginSubmitBtn, false);
      App.setLoading(false);
    }
  },

  afterLogin: async () => {
    App.showMainView();
    App.elements.currentUserLabel.textContent = App.state.currentUser.email + ' (' + App.state.currentUser.role + ')';

    const isAdmin = App.state.currentUser.role === 'admin';
    document.getElementById('adminUsersTabBtn').classList.toggle('hidden', !isAdmin);
    document.getElementById('adminDataTabBtn').classList.toggle('hidden', !isAdmin);

    App.switchScreen('chat');
    await App.refreshInitialData();
  },

  refreshInitialData: async () => {
    App.setLoading(true);
    try {
      await Promise.all([
        App.loadChatSessions(),
        App.loadSuggestedQuestions(),
        App.loadComments(),
        App.loadKnowledge()
      ]);
      if (App.state.currentUser.role === 'admin') {
        await App.loadPendingUsers();
      }
      App.renderAll();
    } catch (error) {
      App.showToast(error.message || '初期データ取得に失敗しました', 'error');
    } finally {
      App.setLoading(false);
    }
  },

  logout: () => {
    App.state.currentUser = null;
    App.state.currentSessionId = null;
    App.state.chatSessions = [];
    App.state.chatMessages = [];
    App.state.suggestedQuestions = [];
    App.state.comments = [];
    App.state.pendingUsers = [];
    App.elements.loginForm.reset();
    App.elements.registerForm.reset();
    App.showAuthView();
    App.showToast('ログアウトしました', 'info');
  },

  switchScreen: (screenName, opts) => {
    opts = opts || {};
    document.querySelectorAll('.screen-view').forEach(function (el) {
      el.classList.add('hidden');
    });
    const map = {
      chat: 'chatScreen',
      comments: 'commentsScreen',
      knowledge: 'knowledgeScreen',
      adminUsers: 'adminUsersScreen',
      adminData: 'adminDataScreen'
    };
    const targetId = map[screenName];
    if (targetId) {
      const target = document.getElementById(targetId);
      if (target) target.classList.remove('hidden');
    }
    document.querySelectorAll('.screen-tab').forEach(function (btn) {
      if (btn.getAttribute('data-screen') === screenName) {
        btn.classList.add('bg-slate-100');
      } else {
        btn.classList.remove('bg-slate-100');
      }
    });
    App.state.currentScreen = screenName || 'chat';
    App.elements.sidebar.classList.remove('mobile-open');
    // サイドバー手動遷移・戻る完了時は citation 用戻るバーを隠す
    if (opts.fromNav || opts.fromBack) {
      App.clearDbReturnBar();
    }
  },

  screenLabel: (screenName) => {
    const labels = {
      chat: 'チャット',
      comments: 'コメント一覧',
      knowledge: 'セミナー動画',
      adminUsers: 'ユーザー承認',
      adminData: 'CSV取込'
    };
    return labels[screenName] || '前の画面';
  },

  clearDbReturnBar: () => {
    App.state.returnScreen = null;
    if (App.elements.commentsBackBar) {
      App.elements.commentsBackBar.classList.add('hidden');
    }
    if (App.elements.knowledgeBackBar) {
      App.elements.knowledgeBackBar.classList.add('hidden');
    }
  },

  showDbReturnBar: (targetScreen) => {
    const returnTo = App.state.returnScreen || 'chat';
    const label = App.screenLabel(returnTo) + 'に戻る';
    if (targetScreen === 'comments' && App.elements.commentsBackBar) {
      if (App.elements.commentsBackLabel) {
        App.elements.commentsBackLabel.textContent = label;
      }
      App.elements.commentsBackBar.classList.remove('hidden');
      if (App.elements.knowledgeBackBar) {
        App.elements.knowledgeBackBar.classList.add('hidden');
      }
    } else if (targetScreen === 'knowledge' && App.elements.knowledgeBackBar) {
      if (App.elements.knowledgeBackLabel) {
        App.elements.knowledgeBackLabel.textContent = label;
      }
      App.elements.knowledgeBackBar.classList.remove('hidden');
      if (App.elements.commentsBackBar) {
        App.elements.commentsBackBar.classList.add('hidden');
      }
    }
  },

  goBackFromDbScreen: () => {
    const dest = App.state.returnScreen || 'chat';
    App.switchScreen(dest, { fromBack: true });
  },

  toggleSidebarMobile: () => {
    App.elements.sidebar.classList.toggle('mobile-open');
  },

  loadChatSessions: async () => {
    if (!App.state.currentUser || !App.state.currentUser.id) return;
    const res = await App.apiClient('GET', '/users/' + App.state.currentUser.id + '/chat-sessions');
    App.state.chatSessions = (res && res.sessions) ? res.sessions : [];
    App.renderSessionList();

    if (!App.state.currentSessionId && App.state.chatSessions.length > 0) {
      App.state.currentSessionId = App.state.chatSessions[0].id;
      await App.loadSessionDetails(App.state.currentSessionId);
    }
    if (App.state.chatSessions.length === 0) {
      App.state.chatMessages = [];
      App.renderChatMessages();
    }
  },

  loadSessionDetails: async (sessionId) => {
    if (!sessionId) {
      App.showToast('セッションIDが未選択です', 'error');
      return;
    }
    const res = await App.apiClient('GET', '/chat-sessions/' + sessionId);
    App.state.chatMessages = (res && res.messages) ? res.messages : [];
    App.restoreCitationsForSession(sessionId);
    App.renderChatMessages();
    App.state.currentSessionId = sessionId;
    App.renderSessionList();
  },

  loadSuggestedQuestions: async () => {
    const res = await App.apiClient('GET', '/suggested-questions');
    App.state.suggestedQuestions = (res && res.questions) ? res.questions : [];
    App.renderSuggestedQuestions();
  },

  loadComments: async () => {
    const res = await App.apiClient('GET', '/comments');
    const rows = (res && res.comments) ? res.comments : [];
    App.state.comments = rows.map(App.enrichCommentCategory);
    App.renderCommentSourceFilterOptions();
    App.renderCommentTable();
  },

  ensureForumCategoryLookup: () => {
    if (App.state.forumCategoryLookup) return App.state.forumCategoryLookup;
    const fromWindow =
      typeof window !== 'undefined' && window.__FORUM_CATEGORY_LOOKUP__
        ? window.__FORUM_CATEGORY_LOOKUP__
        : null;
    App.state.forumCategoryLookup = fromWindow && typeof fromWindow === 'object' ? fromWindow : {};
    return App.state.forumCategoryLookup;
  },

  enrichCommentCategory: (row) => {
    if (!row || typeof row !== 'object') return row;
    const existing = String(row.forum_category || row.forumCategory || '').trim();
    if (existing && existing !== '未分類') return row;
    const lookup = App.ensureForumCategoryLookup();
    const cid = String(row.comment_id || row.commentId || '').trim();
    const mapped = cid && lookup[cid] ? String(lookup[cid]).trim() : '';
    if (!mapped) {
      if (!existing) {
        row.forum_category = '未分類';
      }
      return row;
    }
    row.forum_category = mapped;
    if (!row.source_system && !row.sourceSystem) row.source_system = 'WeStudy';
    if (!row.source_kind && !row.sourceKind) row.source_kind = 'コミュニティ情報';
    return row;
  },

  loadKnowledge: async () => {
    try {
      const [srcRes, chunkRes] = await Promise.all([
        App.apiClient('GET', '/knowledge-sources'),
        App.apiClient('GET', '/knowledge-chunks')
      ]);
      const sources = (srcRes && srcRes.sources) ? srcRes.sources : [];
      const map = {};
      sources.forEach(function (s) {
        if (s && s.source_key) map[s.source_key] = s;
      });
      App.state.knowledgeSources = map;
      App.state.knowledgeChunks = (chunkRes && chunkRes.chunks) ? chunkRes.chunks : [];
    } catch (e) {
      console.warn('knowledge load skipped', e);
      App.state.knowledgeChunks = App.state.knowledgeChunks || [];
      App.state.knowledgeSources = App.state.knowledgeSources || {};
    }
    App.renderKnowledgeTable();
  },

  formatMmSs: (sec) => {
    const s = Math.max(0, Math.floor(Number(sec) || 0));
    const m = Math.floor(s / 60);
    const ss = s % 60;
    return String(m).padStart(2, '0') + ':' + String(ss).padStart(2, '0');
  },

  withVideoTimeUrl: (url, startSec) => {
    if (!url) return '';
    if (/[?&]t=/.test(url)) return url;
    const hashIdx = url.indexOf('#');
    const base = hashIdx >= 0 ? url.slice(0, hashIdx) : url;
    const hash = hashIdx >= 0 ? url.slice(hashIdx) : '';
    const sep = base.indexOf('?') >= 0 ? '&' : '?';
    return base + sep + 't=' + Math.floor(Number(startSec) || 0) + hash;
  },

  normalizeRelatedList: (value) => {
    if (Array.isArray(value)) return value;
    if (value && typeof value === 'object') return [value];
    if (typeof value === 'string' && value.trim()) {
      try {
        const parsed = JSON.parse(value);
        return Array.isArray(parsed) ? parsed : parsed ? [parsed] : [];
      } catch (e) {
        return [];
      }
    }
    return [];
  },

  citationsStorageKey: (sessionId) => 'qa_citations_' + String(sessionId || ''),

  saveCitationsForSession: (sessionId, citations) => {
    if (!sessionId) return;
    try {
      sessionStorage.setItem(
        App.citationsStorageKey(sessionId),
        JSON.stringify(citations || [])
      );
    } catch (e) {
      console.warn('citations save skipped', e);
    }
  },

  restoreCitationsForSession: (sessionId) => {
    if (!sessionId) {
      App.state.lastCitations = [];
      return;
    }
    try {
      const raw = sessionStorage.getItem(App.citationsStorageKey(sessionId));
      App.state.lastCitations = raw ? JSON.parse(raw) : [];
      if (!Array.isArray(App.state.lastCitations)) App.state.lastCitations = [];
    } catch (e) {
      App.state.lastCitations = [];
    }
  },

  buildCitationsFromRelated: (relatedComments, relatedChunks, relatedSources, usedFilter) => {
    const citations = [];
    const sourcesMap = Object.assign({}, App.state.knowledgeSources || {});
    App.normalizeRelatedList(relatedSources).forEach(function (s) {
      if (s && s.source_key) sourcesMap[s.source_key] = s;
    });

    const filter = usedFilter || null;
    const commentIdSet = filter && filter.commentIds ? filter.commentIds : null;
    const chunkKeySet = filter && filter.chunkKeys ? filter.chunkKeys : null;
    const strict = !!(filter && filter.strict);

    App.normalizeRelatedList(relatedComments).forEach(function (c) {
      const enriched = App.enrichCommentCategory(Object.assign({}, c));
      const cid = String(enriched.comment_id || enriched.commentId || '').trim();
      if (strict && commentIdSet) {
        if (!cid || !commentIdSet[cid]) return;
      }
      citations.push({
        kind: 'comment',
        sourceType: 'WeStudyコミュニティ',
        commentId: cid,
        authorName: enriched.author_name || enriched.authorName || '',
        postedAt: enriched.posted_at || enriched.postedAt || '',
        forumCategory:
          String(enriched.forum_category || enriched.forumCategory || '').trim() || '未分類',
        topicTitle: String(enriched.topic_title || enriched.topicTitle || '').trim(),
        sourceKind: String(enriched.source_kind || enriched.sourceKind || 'コミュニティ情報').trim(),
        snippet: String(enriched.content || '').replace(/\s+/g, ' ').slice(0, 220)
      });
    });
    App.normalizeRelatedList(relatedChunks).forEach(function (ch) {
      const chunkKey = String(ch.chunk_key || ch.chunkKey || '').trim();
      if (strict && chunkKeySet) {
        if (!chunkKey || !chunkKeySet[chunkKey]) return;
      }
      const sk = ch.source_key || '';
      const src = sourcesMap[sk] || {};
      const start = ch.start_sec != null ? Number(ch.start_sec) : 0;
      citations.push({
        kind: 'video_chunk',
        sourceType: 'WeStudyセミナー動画',
        chunkKey: chunkKey,
        videoTitle: src.title || sk || '（タイトル不明）',
        videoUrl: App.withVideoTimeUrl(src.video_url || '', start),
        startSec: start,
        startLabel: App.formatMmSs(start),
        snippet: String(ch.content || '').replace(/\s+/g, ' ').slice(0, 220)
      });
    });
    return citations;
  },

  /**
   * 第2 LLM の usedSources JSON をパース。
   * 成功時: { ok:true, commentIds:{id:1}, chunkKeys:{key:1}, strict:true }
   * 失敗時: { ok:false } → 呼び出し側は従来どおり全件表示にフォールバック
   */
  parseUsedSources: (raw) => {
    let text = String(raw == null ? '' : raw).trim();
    if (!text) return { ok: false };
    const fence = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
    if (fence) text = fence[1].trim();
    const start = text.indexOf('{');
    const end = text.lastIndexOf('}');
    if (start < 0 || end <= start) return { ok: false };
    text = text.slice(start, end + 1);
    let obj;
    try {
      obj = JSON.parse(text);
    } catch (e) {
      return { ok: false };
    }
    if (!obj || typeof obj !== 'object') return { ok: false };
    const commentIds = {};
    const chunkKeys = {};
    const cList = obj.comment_ids || obj.commentIds || [];
    const kList = obj.chunk_keys || obj.chunkKeys || [];
    if (!Array.isArray(cList) || !Array.isArray(kList)) return { ok: false };
    cList.forEach(function (id) {
      const s = String(id == null ? '' : id).trim();
      if (s) commentIds[s] = 1;
    });
    kList.forEach(function (k) {
      const s = String(k == null ? '' : k).trim();
      if (s) chunkKeys[s] = 1;
    });
    return { ok: true, commentIds: commentIds, chunkKeys: chunkKeys, strict: true };
  },

  openCitationInDb: (citation) => {
    if (!citation) return;
    const fromScreen = App.state.currentScreen || 'chat';
    App.state.returnScreen =
      fromScreen === 'comments' || fromScreen === 'knowledge' ? 'chat' : fromScreen;
    if (citation.kind === 'video_chunk') {
      App.switchScreen('knowledge');
      App.showDbReturnBar('knowledge');
      if (App.elements.knowledgeSearchInput) {
        App.elements.knowledgeSearchInput.value =
          citation.videoTitle || citation.chunkKey || '';
        App.renderKnowledgeTable();
      }
      return;
    }
    App.switchScreen('comments');
    App.showDbReturnBar('comments');
    const commentId = String(citation.commentId || '').trim();
    if (App.elements.commentSearchInput) {
      App.elements.commentSearchInput.value = commentId;
      App.renderCommentTable({ exactCommentId: commentId });
    }
  },

  /**
   * 関連セミナー動画（タイトル単位で集約）＋関連コミュニティ投稿
   */
  renderCitationsPanel: (citations) => {
    if (!citations || !citations.length) return '';

    const videoList = [];
    const commentList = [];
    citations.forEach(function (c) {
      if (c && c.kind === 'video_chunk') videoList.push(c);
      else if (c) commentList.push(c);
    });

    const groups = {};
    const groupOrder = [];
    videoList.forEach(function (c) {
      const title = String(c.videoTitle || '').trim() || '（タイトル不明）';
      if (!groups[title]) {
        groups[title] = {
          title: title,
          secs: [],
          videoUrl: '',
          searchKey: c.chunkKey || title
        };
        groupOrder.push(title);
      }
      const g = groups[title];
      const sec = c.startSec != null ? Number(c.startSec) : NaN;
      if (!isNaN(sec) && g.secs.indexOf(sec) === -1) {
        g.secs.push(sec);
      }
      if (!g.videoUrl && c.videoUrl) g.videoUrl = String(c.videoUrl);
      if (c.chunkKey && g.searchKey === title) g.searchKey = c.chunkKey;
    });
    groupOrder.forEach(function (t) {
      groups[t].secs.sort(function (a, b) {
        return a - b;
      });
    });

    const parts = [];

    const videoLis = groupOrder.map(function (t) {
      const g = groups[t];
      const secLabel = g.secs.map(function (s) {
        return String(s) + '秒';
      }).join(' / ');
      const earliest = g.secs.length ? g.secs[0] : 0;
      const baseUrl = String(g.videoUrl || '')
        .replace(/[?&]t=\d+/g, '')
        .replace(/\?&/, '?')
        .replace(/[?&]$/, '');
      const openUrl = baseUrl ? App.withVideoTimeUrl(baseUrl, earliest) : '';
      const openDb =
        '<button type="button" class="citation-db-link text-blue-700 underline ml-1" data-kind="video_chunk" data-key="' +
        App.escapeHtml(g.title) +
        '">DBで見る</button>';
      const openVideo = openUrl
        ? (' <a class="text-blue-600 underline" target="_blank" rel="noopener noreferrer" href="' +
          App.escapeHtml(openUrl) +
          '">動画を開く</a>')
        : '';
      return (
        '<li class="mb-1">' +
        App.escapeHtml(g.title) +
        (secLabel ? ' — ' + App.escapeHtml(secLabel) : '') +
        openDb +
        openVideo +
        '</li>'
      );
    });
    if (videoLis.length) {
      parts.push(
        '<div class="font-semibold mb-1">関連セミナー動画</div>' +
          '<ul class="citations-list mb-2">' +
          videoLis.join('') +
          '</ul>'
      );
    }

    const commentItemHtml = function (c) {
      return (
        '<li class="mb-1">' +
        App.escapeHtml(c.authorName || '') +
        ' #' +
        App.escapeHtml(c.commentId || '') +
        ' <button type="button" class="citation-db-link text-blue-700 underline" data-kind="comment" data-key="' +
        App.escapeHtml(c.commentId || '') +
        '">DBで見る</button>' +
        '<div class="text-slate-600">' +
        App.escapeHtml(c.snippet || '') +
        '</div></li>'
      );
    };

    // 分類 → 年（新しい年優先）→ 投稿（新しい順）。参照分は全件
    const sortedComments = commentList.slice().sort(function (a, b) {
      const ta = App.postedAtSortKey(a.postedAt);
      const tb = App.postedAtSortKey(b.postedAt);
      return tb - ta;
    });
    const byCategory = {};
    const categoryOrder = [];
    sortedComments.forEach(function (c) {
      const cat = String(c.forumCategory || '未分類').trim() || '未分類';
      if (!byCategory[cat]) {
        byCategory[cat] = [];
        categoryOrder.push(cat);
      }
      byCategory[cat].push(c);
    });
    categoryOrder.sort(function (a, b) {
      if (a === '未分類') return 1;
      if (b === '未分類') return -1;
      return a.localeCompare(b, 'ja');
    });

    let commentBlock = '';
    categoryOrder.forEach(function (cat) {
      const list = byCategory[cat];
      const byYear = {};
      const yearOrder = [];
      list.forEach(function (c) {
        const y = App.parsePostedYear(c.postedAt);
        const key = y != null ? String(y) : 'unknown';
        if (!byYear[key]) {
          byYear[key] = [];
          yearOrder.push(key);
        }
        byYear[key].push(c);
      });
      yearOrder.sort(function (a, b) {
        if (a === 'unknown') return 1;
        if (b === 'unknown') return -1;
        return Number(b) - Number(a);
      });
      commentBlock +=
        '<div class="font-semibold text-slate-800 mt-2 mb-0.5">' +
        App.escapeHtml(cat) +
        '</div>';
      yearOrder.forEach(function (key) {
        const heading = key === 'unknown' ? '日時不明' : key + '年';
        commentBlock +=
          '<div class="font-medium text-slate-600 mt-1 mb-0.5 ml-1">' +
          App.escapeHtml(heading) +
          '</div>' +
          '<ul class="citations-list mb-1 ml-1">' +
          byYear[key].map(commentItemHtml).join('') +
          '</ul>';
      });
    });
    if (commentBlock) {
      parts.push(
        '<div class="font-semibold mb-1">関連コミュニティ投稿</div>' + commentBlock
      );
    }

    if (!parts.length) return '';
    return (
      '<div class="citations-panel mt-3 border-t pt-2 text-xs">' + parts.join('') + '</div>'
    );
  },

  parsePostedYear: (postedAt) => {
    const s = String(postedAt || '').trim();
    if (!s) return null;
    const m = s.match(/(20\d{2}|19\d{2})/);
    if (!m) return null;
    const y = Number(m[1]);
    return isNaN(y) ? null : y;
  },

  postedAtSortKey: (postedAt) => {
    const s = String(postedAt || '').trim();
    if (!s) return 0;
    const t = Date.parse(s);
    if (!isNaN(t)) return t;
    const m = s.match(/(20\d{2}|19\d{2})[\/\-.](\d{1,2})[\/\-.](\d{1,2})/);
    if (m) {
      return Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
    }
    const y = App.parsePostedYear(s);
    return y != null ? Date.UTC(y, 0, 1) : 0;
  },

  formatAssistantHtml: (text) => {
    const raw = String(text || '');
    if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
      const html = marked.parse(raw, { breaks: true, gfm: true });
      return DOMPurify.sanitize(html, {
        ADD_ATTR: ['target', 'rel'],
        ALLOWED_TAGS: [
          'p', 'br', 'strong', 'em', 'ul', 'ol', 'li',
          'h1', 'h2', 'h3', 'h4', 'a', 'code', 'pre', 'blockquote'
        ]
      });
    }
    const escaped = App.escapeHtml(raw).replace(/\n/g, '<br>');
    return escaped.replace(
      /(https?:\/\/[^\s<]+)/g,
      '<a class="text-blue-600 underline" target="_blank" rel="noopener noreferrer" href="$1">$1</a>'
    );
  },

  renderKnowledgeTable: () => {
    const body = App.elements.knowledgeTableBody;
    if (!body) return;
    const keyword = String((App.elements.knowledgeSearchInput && App.elements.knowledgeSearchInput.value) || '')
      .trim()
      .toLowerCase();
    const rows = (App.state.knowledgeChunks || []).filter(function (ch) {
      if (!keyword) return true;
      const src = App.state.knowledgeSources[ch.source_key] || {};
      const hay = [
        ch.chunk_key,
        ch.content,
        ch.search_text,
        ch.source_key,
        src.title,
        src.video_id
      ]
        .join(' ')
        .toLowerCase();
      return hay.indexOf(keyword) !== -1;
    });
    body.innerHTML = '';
    rows.slice(0, 500).forEach(function (ch) {
      const src = App.state.knowledgeSources[ch.source_key] || {};
      const start = ch.start_sec != null ? Number(ch.start_sec) : 0;
      const url = App.withVideoTimeUrl(src.video_url || '', start);
      const tr = document.createElement('tr');
      tr.className = 'border-t align-top';
      tr.innerHTML =
        '<td class="p-2 whitespace-nowrap">' +
        App.escapeHtml(App.formatMmSs(start)) +
        '</td>' +
        '<td class="p-2">WeStudyセミナー動画</td>' +
        '<td class="p-2">' +
        App.escapeHtml(src.title || ch.source_key || '') +
        '</td>' +
        '<td class="p-2">' +
        App.escapeHtml(String(ch.content || '').slice(0, 180)) +
        '</td>' +
        '<td class="p-2">' +
        (url
          ? '<a class="text-blue-600 underline" target="_blank" rel="noopener noreferrer" href="' +
            App.escapeHtml(url) +
            '">開く</a>'
          : '') +
        '</td>';
      body.appendChild(tr);
    });
    if (App.elements.knowledgeListMeta) {
      App.elements.knowledgeListMeta.textContent =
        '表示 ' + Math.min(rows.length, 500) + ' / 全 ' + (App.state.knowledgeChunks || []).length + ' チャンク';
    }
  },

  loadPendingUsers: async () => {
    if (!App.state.currentUser || App.state.currentUser.role !== 'admin') return;
    const res = await App.apiClient('GET', '/admin/users/pending');
    App.state.pendingUsers = (res && res.users) ? res.users : [];
    App.renderPendingUsers();
  },

  renderAll: () => {
    App.renderSessionList();
    App.renderChatMessages();
    App.renderSuggestedQuestions();
    App.renderCommentTable();
    App.renderPendingUsers();
  },

  renderSessionList: () => {
    const list = App.elements.sessionList;
    list.innerHTML = '';
    if (App.state.chatSessions.length === 0) {
      list.innerHTML = '<li class="text-sm text-slate-500">履歴がありません</li>';
      return;
    }

    App.state.chatSessions.forEach(function (s) {
      const li = document.createElement('li');
      const active = App.state.currentSessionId === s.id ? 'active' : '';
      li.className = 'session-item border rounded p-2 cursor-pointer hover:bg-slate-50 ' + active;
      li.innerHTML =
        '<div class="text-sm font-medium">' + App.escapeHtml(s.title || '無題') + '</div>' +
        '<div class="text-xs text-slate-500 mt-1">' + App.escapeHtml(s.created_at || '') + '</div>';
      li.addEventListener('click', function () {
        App.loadSessionDetails(s.id);
        App.switchScreen('chat');
      });
      list.appendChild(li);
    });
  },

  renderChatMessages: () => {
    const area = App.elements.chatMessages;
    area.innerHTML = '';
    if (App.state.chatMessages.length === 0) {
      area.innerHTML = '<p class="text-sm text-slate-500">メッセージはまだありません。質問を送信してください。</p>';
      return;
    }

    const lastAssistantIdx = (function () {
      for (let i = App.state.chatMessages.length - 1; i >= 0; i -= 1) {
        if (App.state.chatMessages[i].role === 'assistant') return i;
      }
      return -1;
    })();

    App.state.chatMessages.forEach(function (m, idx) {
      const wrap = document.createElement('div');
      const bubble = document.createElement('div');
      const role = m.role === 'user' ? 'chat-user' : 'chat-assistant';
      const isLastAssistant = m.role === 'assistant' && idx === lastAssistantIdx;

      bubble.className = 'chat-bubble ' + role;
      bubble.innerHTML =
        '<div class="text-[11px] text-slate-500 mb-1">' +
        App.escapeHtml(m.role) + ' ・ ' + App.escapeHtml(m.created_at || '') +
        '</div>' +
        '<div>' +
        (m.role === 'assistant'
          ? '<div class="md-body">' + App.formatAssistantHtml(m.content || '') + '</div>'
          : App.escapeHtml(m.content || '')) +
        '</div>' +
        (isLastAssistant ? App.renderCitationsPanel(App.state.lastCitations || []) : '');

      wrap.appendChild(bubble);
      area.appendChild(wrap);
    });

    area.querySelectorAll('.citation-db-link').forEach(function (btn) {
      btn.addEventListener('click', function () {
        const kind = btn.getAttribute('data-kind');
        const key = btn.getAttribute('data-key') || '';
        if (kind === 'video_chunk') {
          App.openCitationInDb({ kind: 'video_chunk', videoTitle: key, chunkKey: key });
        } else {
          App.openCitationInDb({ kind: 'comment', commentId: key });
        }
      });
    });

    area.scrollTop = area.scrollHeight;
  },

  renderSuggestedQuestions: () => {
    const box = App.elements.suggestedQuestions;
    box.innerHTML = '';
    if (App.state.suggestedQuestions.length === 0) {
      box.innerHTML = '<span class="text-xs text-slate-400">提案はまだありません</span>';
      return;
    }

    App.state.suggestedQuestions.forEach(function (q) {
      const btn = document.createElement('button');
      btn.className = 'text-xs px-3 py-1 rounded-full border bg-slate-50 hover:bg-blue-50';
      btn.innerHTML = App.escapeHtml(q.question_text || '');
      btn.addEventListener('click', async function () {
        try {
          if (q.id) {
            await App.apiClient('PUT', '/suggested-questions/' + q.id + '/increment');
          }
        } catch (e) {
          console.warn(e);
        }
        await App.sendQuestion(q.question_text, true);
      });
      box.appendChild(btn);
    });
  },

  renderCommentSourceFilterOptions: () => {
    const select = App.elements.commentSourceFilter;
    if (!select) return;
    const current = select.value || '';
    const sources = Array.from(
      new Set(
        (App.state.comments || [])
          .map(function (row) {
            return String(App.commentField(row, 'source_type') || '').trim();
          })
          .filter(Boolean)
      )
    ).sort();
    select.innerHTML = '<option value="">全ソース</option>';
    sources.forEach(function (source) {
      const opt = document.createElement('option');
      opt.value = source;
      opt.textContent = source;
      select.appendChild(opt);
    });
    if (current && sources.indexOf(current) !== -1) {
      select.value = current;
    }
    App.renderCommentCategoryFilterOptions();
  },

  renderCommentCategoryFilterOptions: () => {
    const select = App.elements.commentCategoryFilter;
    if (!select) return;
    const current = select.value || '';
    const cats = Array.from(
      new Set(
        (App.state.comments || [])
          .map(function (row) {
            return (
              String(App.commentField(row, 'forum_category') || '').trim() || '未分類'
            );
          })
          .filter(Boolean)
      )
    ).sort(function (a, b) {
      if (a === '未分類') return 1;
      if (b === '未分類') return -1;
      return a.localeCompare(b, 'ja');
    });
    select.innerHTML = '<option value="">全分類</option>';
    cats.forEach(function (cat) {
      const opt = document.createElement('option');
      opt.value = cat;
      opt.textContent = cat;
      select.appendChild(opt);
    });
    if (current && cats.indexOf(current) !== -1) {
      select.value = current;
    }
  },

  hasPostedAtValue: (row) => {
    return String(App.commentField(row, 'posted_at') || '').trim() !== '';
  },

  renderCommentTable: (opts) => {
    opts = opts || {};
    const body = App.elements.commentTableBody;
    const keywordRaw = String((App.elements.commentSearchInput && App.elements.commentSearchInput.value) || '').trim();
    const keyword = keywordRaw.toLowerCase();
    const exactFromOpts = String(opts.exactCommentId || '').trim();
    // 「DBで見る」または検索欄が数字のみ → comment_id 完全一致
    const exactCommentId =
      exactFromOpts || (/^\d+$/.test(keywordRaw) ? keywordRaw : '');
    const sourceFilter = (App.elements.commentSourceFilter && App.elements.commentSourceFilter.value) || '';
    const categoryFilter =
      (App.elements.commentCategoryFilter && App.elements.commentCategoryFilter.value) || '';
    const dateFilter = (App.elements.commentDateFilter && App.elements.commentDateFilter.value) || '';
    body.innerHTML = '';

    const filtered = App.state.comments.filter(function (row) {
      const cid = String(App.commentField(row, 'comment_id') || '').trim();
      const sourceType = String(App.commentField(row, 'source_type') || '').trim();
      const forumCategory =
        String(App.commentField(row, 'forum_category') || '').trim() || '未分類';
      const hasDate = App.hasPostedAtValue(row);
      let hitKeyword = true;
      if (exactCommentId) {
        hitKeyword = cid === exactCommentId;
      } else if (keyword) {
        const t1 = String(App.commentField(row, 'content')).toLowerCase();
        const t2 = String(App.commentField(row, 'author_name')).toLowerCase();
        const t3 = String(App.commentField(row, 'source_type')).toLowerCase();
        const t4 = cid.toLowerCase();
        const t5 = forumCategory.toLowerCase();
        hitKeyword =
          t1.indexOf(keyword) !== -1 ||
          t2.indexOf(keyword) !== -1 ||
          t3.indexOf(keyword) !== -1 ||
          t4.indexOf(keyword) !== -1 ||
          t5.indexOf(keyword) !== -1;
      }
      const hitSource = !sourceFilter || sourceType === sourceFilter;
      const hitCategory = !categoryFilter || forumCategory === categoryFilter;
      const hitDate =
        !dateFilter ||
        (dateFilter === 'hasDate' && hasDate) ||
        (dateFilter === 'missingDate' && !hasDate);
      return hitKeyword && hitSource && hitCategory && hitDate;
    });

    const totalCount = App.state.comments.length;
    const missingDateCount = App.state.comments.reduce(function (n, row) {
      return n + (App.hasPostedAtValue(row) ? 0 : 1);
    }, 0);
    if (App.elements.commentListMeta) {
      App.elements.commentListMeta.textContent =
        '表示 ' +
        filtered.length +
        ' / 全 ' +
        totalCount +
        ' 件（日時なし ' +
        missingDateCount +
        ' 件）';
    }

    if (filtered.length === 0) {
      body.innerHTML = '<tr><td colspan="6" class="p-3 text-slate-500">該当データがありません</td></tr>';
      return;
    }

    filtered.forEach(function (r) {
      const tr = document.createElement('tr');
      tr.className = 'border-t';
      const postedAt = String(App.commentField(r, 'posted_at') || '').trim();
      const postedAtLabel = postedAt || '（日時なし）';
      const forumCategory =
        String(App.commentField(r, 'forum_category') || '').trim() || '未分類';
      tr.innerHTML =
        '<td class="p-2 whitespace-nowrap">' +
        App.escapeHtml(String(App.commentField(r, 'comment_id') || '')) +
        '</td>' +
        '<td class="p-2 whitespace-nowrap">' +
        App.escapeHtml(forumCategory) +
        '</td>' +
        '<td class="p-2">' +
        App.escapeHtml(postedAtLabel) +
        (postedAt ? '' : ' <span class="text-[10px] text-amber-700">missing</span>') +
        '</td>' +
        '<td class="p-2">' + App.escapeHtml(App.commentField(r, 'source_type')) + '</td>' +
        '<td class="p-2">' + App.escapeHtml(App.commentField(r, 'author_name')) + '</td>' +
        '<td class="p-2">' + App.escapeHtml(String(App.commentField(r, 'content')).slice(0, 180)) + '</td>';
      body.appendChild(tr);
    });
  },

  renderPendingUsers: () => {
    const body = App.elements.pendingUsersTableBody;
    body.innerHTML = '';
    if (App.elements.pendingUsersSelectAll) {
      App.elements.pendingUsersSelectAll.checked = false;
    }
    if (App.state.currentUser && App.state.currentUser.role !== 'admin') {
      App.updateBulkApproveButtonState();
      return;
    }

    if (App.state.pendingUsers.length === 0) {
      body.innerHTML = '<tr><td colspan="5" class="p-3 text-slate-500">承認待ちユーザーはいません</td></tr>';
      App.updateBulkApproveButtonState();
      return;
    }

    App.state.pendingUsers.forEach(function (u) {
      const tr = document.createElement('tr');
      tr.className = 'border-t';
      tr.innerHTML =
        '<td class="p-2">' +
        '<input type="checkbox" class="pending-user-check" data-id="' +
        App.escapeHtml(u.id) +
        '" data-email="' +
        App.escapeHtml(u.email || '') +
        '" aria-label="選択" />' +
        '</td>' +
        '<td class="p-2">' + App.escapeHtml(u.id) + '</td>' +
        '<td class="p-2">' + App.escapeHtml(u.email || '') + '</td>' +
        '<td class="p-2">' + App.escapeHtml(u.status || '') + '</td>' +
        '<td class="p-2">' +
        '<div class="flex flex-wrap gap-2">' +
        '<button type="button" class="approve-btn px-3 py-1 rounded bg-blue-600 text-white text-xs" data-id="' +
        App.escapeHtml(u.id) +
        '" data-email="' +
        App.escapeHtml(u.email || '') +
        '">承認</button>' +
        '<button type="button" class="reject-btn px-3 py-1 rounded bg-red-600 text-white text-xs" data-id="' +
        App.escapeHtml(u.id) +
        '" data-email="' +
        App.escapeHtml(u.email || '') +
        '">却下</button>' +
        '</div></td>';
      body.appendChild(tr);
    });

    body.querySelectorAll('.pending-user-check').forEach(function (cb) {
      cb.addEventListener('change', App.updateBulkApproveButtonState);
    });
    body.querySelectorAll('.approve-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        const id = btn.getAttribute('data-id');
        const email = btn.getAttribute('data-email') || '';
        App.confirmApproveUser(id, email);
      });
    });
    body.querySelectorAll('.reject-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        const id = btn.getAttribute('data-id');
        const email = btn.getAttribute('data-email') || '';
        App.confirmRejectUser(id, email);
      });
    });
    App.updateBulkApproveButtonState();
  },

  updateBulkApproveButtonState: () => {
    const btn = App.elements.bulkApprovePendingUsersBtn;
    if (!btn) return;
    const selected = App.getSelectedPendingUsers();
    btn.disabled = selected.length === 0;
    btn.textContent =
      selected.length > 0
        ? '選択したユーザーを一括承認（' + selected.length + '件）'
        : '選択したユーザーを一括承認';
  },

  getSelectedPendingUsers: () => {
    const body = App.elements.pendingUsersTableBody;
    if (!body) return [];
    const selected = [];
    body.querySelectorAll('.pending-user-check:checked').forEach(function (cb) {
      selected.push({
        id: cb.getAttribute('data-id'),
        email: cb.getAttribute('data-email') || ''
      });
    });
    return selected;
  },

  resolveApplicantEmail: (userId, email) => {
    let applicantEmail = (email || '').trim();
    if (!applicantEmail && App.state.pendingUsers && App.state.pendingUsers.length) {
      const found = App.state.pendingUsers.find(function (u) {
        return String(u.id) === String(userId);
      });
      if (found && found.email) applicantEmail = String(found.email).trim();
    }
    return applicantEmail;
  },

  createNewChatPlaceholder: () => {
    App.state.currentSessionId = null;
    App.state.chatMessages = [];
    App.renderChatMessages();
    App.switchScreen('chat');
    App.showToast('新しいチャットを開始できます', 'info');
  },

  handleSendMessage: async (event) => {
    event.preventDefault();
    const text = App.elements.messageInput.value.trim();
    if (!text) return;
    await App.sendQuestion(text, false);
  },

  sendQuestion: async (questionText, fromSuggested) => {
    if (!questionText) {
      App.showToast('質問内容が空です', 'error');
      return;
    }
    if (!App.state.currentUser || !App.state.currentUser.id) {
      App.showToast('ユーザー情報が取得できません', 'error');
      return;
    }

    App.setButtonLoading(App.elements.sendMessageBtn, true, '送信中');
    App.setLoading(true);
    try {
      let sessionId = App.state.currentSessionId;

      if (!sessionId) {
        const sessionRes = await App.apiClient('POST', '/chat-sessions', {
          user_id: App.state.currentUser.id,
          initial_message: questionText
        });
        sessionId = sessionRes.id;
        if (!sessionId) {
          throw new Error('チャットセッション作成に失敗しました');
        }
        App.state.currentSessionId = sessionId;
        await App.loadChatSessions();
      }

      if (!sessionId) {
        App.showToast('送信先セッションが未確定です', 'error');
        return;
      }

      const msgRes = await App.apiClient('POST', '/chat-sessions/' + sessionId + '/messages', {
        content: questionText
      });
      const used = App.parseUsedSources(
        (msgRes && (msgRes.usedSources || msgRes.used_sources)) || ''
      );
      App.state.lastCitations = App.buildCitationsFromRelated(
        (msgRes && msgRes.relatedComments) || [],
        (msgRes && msgRes.relatedChunks) || [],
        (msgRes && msgRes.relatedSources) || [],
        used.ok
          ? { commentIds: used.commentIds, chunkKeys: used.chunkKeys, strict: true }
          : null
      );
      if (msgRes && Array.isArray(msgRes.citations) && msgRes.citations.length) {
        App.state.lastCitations = msgRes.citations;
      }
      App.saveCitationsForSession(sessionId, App.state.lastCitations);

      if (!fromSuggested) {
        await App.createSuggestedQuestionIfNeeded(questionText);
      }

      await App.loadSessionDetails(sessionId);
      await App.loadSuggestedQuestions();

      App.elements.messageInput.value = '';
      App.showToast('送信しました', 'success');
    } catch (error) {
      App.showToast(error.message || '送信に失敗しました', 'error');
    } finally {
      App.setButtonLoading(App.elements.sendMessageBtn, false);
      App.setLoading(false);
    }
  },

  createSuggestedQuestionIfNeeded: async (questionText) => {
    const normalized = String(questionText || '').trim();
    if (!normalized) return;
    const exists = App.state.suggestedQuestions.some(function (q) {
      return String(q.question_text || '').trim() === normalized;
    });
    if (exists) return;
    try {
      await App.apiClient('POST', '/suggested-questions', {
        question_text: normalized
      });
    } catch (e) {
      console.warn('suggested create skipped', e);
    }
  },

  confirmApproveUser: async (userId, email) => {
    if (!userId) {
      App.showToast('承認対象IDが不正です', 'error');
      return;
    }
    const applicantEmail = App.resolveApplicantEmail(userId, email);
    const ok = await App.openConfirmDialog('ユーザー承認', 'ユーザーID ' + userId + ' を承認しますか？');
    if (!ok) return;

    App.setLoading(true);
    try {
      await App.apiClient('PUT', '/admin/users/' + userId + '/approve');
      if (applicantEmail) {
        await App.notifyApprovalCompleted(applicantEmail);
      } else {
        console.warn('approval notify skipped: applicant email missing');
      }
      App.showToast('ユーザーを承認しました', 'success');
      await App.loadPendingUsers();
    } catch (error) {
      App.showToast(error.message || '承認に失敗しました', 'error');
    } finally {
      App.setLoading(false);
    }
  },

  confirmRejectUser: async (userId, email) => {
    if (!userId) {
      App.showToast('却下対象IDが不正です', 'error');
      return;
    }
    const applicantEmail = App.resolveApplicantEmail(userId, email);
    const ok = await App.openConfirmDialog(
      'ユーザー却下',
      'ユーザーID ' + userId + ' を却下しますか？申請者へ却下メールを送信します。'
    );
    if (!ok) return;

    App.setLoading(true);
    try {
      await App.apiClient('PUT', '/admin/users/' + userId + '/reject');
      if (applicantEmail) {
        await App.notifyRejectionCompleted(applicantEmail);
      } else {
        console.warn('rejection notify skipped: applicant email missing');
      }
      App.showToast('ユーザーを却下しました', 'success');
      await App.loadPendingUsers();
    } catch (error) {
      App.showToast(error.message || '却下に失敗しました', 'error');
    } finally {
      App.setLoading(false);
    }
  },

  confirmBulkApproveUsers: async () => {
    const selected = App.getSelectedPendingUsers();
    if (!selected.length) {
      App.showToast('承認するユーザーを選択してください', 'error');
      return;
    }
    const ok = await App.openConfirmDialog(
      '一括承認',
      '選択した ' + selected.length + ' 件を承認しますか？各申請者へ承認完了メールを送信します。'
    );
    if (!ok) return;

    App.setLoading(true);
    let success = 0;
    let failed = 0;
    try {
      for (let i = 0; i < selected.length; i += 1) {
        const item = selected[i];
        try {
          await App.apiClient('PUT', '/admin/users/' + item.id + '/approve');
          const applicantEmail = App.resolveApplicantEmail(item.id, item.email);
          if (applicantEmail) {
            await App.notifyApprovalCompleted(applicantEmail);
          }
          success += 1;
        } catch (e) {
          failed += 1;
          console.warn('bulk approve failed for', item.id, e);
        }
      }
      if (failed === 0) {
        App.showToast(success + ' 件を一括承認しました', 'success');
      } else {
        App.showToast('一括承認: 成功 ' + success + ' 件 / 失敗 ' + failed + ' 件', 'error');
      }
      await App.loadPendingUsers();
    } finally {
      App.setLoading(false);
    }
  },

  /** Phase 3: 申請者へ承認完了メール。失敗しても throw しない。 */
  notifyApprovalCompleted: async (email) => {
    try {
      await App.apiClient('POST', '/notify/approval', {
        email: email
      });
    } catch (notifyErr) {
      console.warn('approval notify failed (approval still OK):', notifyErr);
    }
  },

  /** Phase 8: 申請者へ却下メール。失敗しても throw しない。 */
  notifyRejectionCompleted: async (email) => {
    try {
      await App.apiClient('POST', '/notify/rejection', {
        email: email
      });
    } catch (notifyErr) {
      console.warn('rejection notify failed (rejection still OK):', notifyErr);
    }
  },

  createSampleComment: async () => {
    if (!App.state.currentUser || App.state.currentUser.role !== 'admin') {
      App.showToast('管理者のみ実行できます', 'error');
      return;
    }
    App.setLoading(true);
    try {
      await App.apiClient('POST', '/admin/comments', {
        source_type: 'WeStudy',
        source_system: 'WeStudy',
        source_kind: 'コミュニティ情報',
        forum_category: '未分類',
        topic_title: '',
        comment_id: 'sample-' + String(Date.now()),
        posted_at: new Date().toISOString().slice(0, 19).replace('T', ' '),
        author_name: 'System',
        author_email: 'system@example.com',
        content: 'サンプルコメントです。',
        parent_comment_id: '',
        ip_address: '127.0.0.1',
        user_agent: navigator.userAgent
      });
      await App.loadComments();
      App.showToast('サンプル登録完了', 'success');
    } catch (error) {
      App.showToast(error.message || '登録に失敗しました', 'error');
    } finally {
      App.setLoading(false);
    }
  },

  deleteComments: async () => {
    if (!App.state.currentUser || App.state.currentUser.role !== 'admin') {
      App.showToast('管理者のみ実行できます', 'error');
      return;
    }
    const sourceType = (App.elements.deleteSourceTypeInput && App.elements.deleteSourceTypeInput.value) || '';
    const commentIdLike =
      (App.elements.deleteCommentIdLikeInput && App.elements.deleteCommentIdLikeInput.value.trim()) || '';
    if (!sourceType && !commentIdLike) {
      App.showToast('全削除防止のため、ソースまたはcomment_id条件を指定してください', 'error');
      return;
    }
    await App.loadComments();
    const candidates = (App.state.comments || []).filter(function (row) {
      const sourceOk = !sourceType || String(App.commentField(row, 'source_type') || '').trim() === sourceType;
      const cid = String(App.commentField(row, 'comment_id') || '').trim();
      const idLikeOk = !commentIdLike || cid.indexOf(commentIdLike) !== -1;
      return sourceOk && idLikeOk;
    });
    const withId = candidates.filter(function (row) {
      return String(row.id || '').trim() !== '';
    });
    if (candidates.length === 0) {
      App.showToast('削除対象が0件でした（条件を確認してください）', 'info');
      return;
    }
    if (withId.length === 0) {
      App.showToast('削除できません（該当行に内部 id がありません。再取得後に再試行してください）', 'error');
      return;
    }
    const label =
      'source=' +
      (sourceType || 'ALL') +
      (commentIdLike ? (' / comment_id like "' + commentIdLike + '"') : '') +
      ' / 削除実行=' +
      withId.length +
      '件（一覧該当 ' +
      candidates.length +
      '件）';
    const ok = await App.openConfirmDialog(
      'コメント削除',
      '以下条件のコメントを削除します。元に戻せません。\n' + label
    );
    if (!ok) return;

    App.setButtonLoading(App.elements.deleteCommentsBtn, true, '削除中');
    App.setLoading(true);
    try {
      let deletedCount = 0;
      const concurrency = 5;
      for (let i = 0; i < withId.length; i += concurrency) {
        const slice = withId.slice(i, i + concurrency);
        await Promise.all(
          slice.map(function (row) {
            const rowId = String(row.id || '').trim();
            return App.apiClient('POST', '/admin/comments/' + rowId + '/delete');
          })
        );
        deletedCount += slice.length;
      }
      await App.loadComments();
      App.showToast('削除完了: ' + deletedCount + ' 件', 'success');
      if (App.elements.importResult) {
        App.elements.importResult.textContent +=
          '[DELETE] source=' +
          (sourceType || 'ALL') +
          ' comment_id_like=' +
          (commentIdLike || '-') +
          ' deleted=' +
          deletedCount +
          '\n';
      }
    } catch (error) {
      App.showToast(error.message || '削除に失敗しました', 'error');
    } finally {
      App.setButtonLoading(App.elements.deleteCommentsBtn, false);
      App.setLoading(false);
    }
  },

  /* CSV 取り込み時の重複判定用（本文の空白正規化） */
  normalizeCommentBodyForDedupe: (text) => {
    return String(text || '')
      .replace(/\r\n/g, '\n')
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, 20000);
  },

  /* 同一コメントの再取り込みを避ける複合キー（本文＋投稿日時＋投稿者名） */
  commentImportCompositeKey: (content, postedAt, authorName) => {
    return (
      App.normalizeCommentBodyForDedupe(content) +
      '\u0001' +
      String(postedAt || '').trim() +
      '\u0001' +
      String(authorName || '').trim()
    );
  },

  buildCommentImportDedupeSets: () => {
    const idSet = new Set();
    const compositeSet = new Set();
    (App.state.comments || []).forEach(function (c) {
      const cid = String(c.comment_id || c.commentId || '').trim();
      if (cid) idSet.add(cid);
      compositeSet.add(
        App.commentImportCompositeKey(
          App.commentField(c, 'content'),
          App.commentField(c, 'posted_at'),
          App.commentField(c, 'author_name')
        )
      );
    });
    return { idSet, compositeSet };
  },

  importCsvComments: async () => {
    if (!App.state.currentUser || App.state.currentUser.role !== 'admin') {
      App.showToast('管理者のみ実行できます', 'error');
      return;
    }
    const file = App.elements.csvFileInput.files[0];
    if (!file) {
      App.showToast('CSVファイルを選択してください', 'error');
      return;
    }

    App.setLoading(true);
    App.elements.importResult.textContent = '';
    try {
      const text = await file.text();
      const rows = App.parseCsv(text);
      if (rows.length === 0) {
        App.showToast('CSVデータが空です', 'error');
        return;
      }

      const headerKeys = Object.keys(rows[0] || {});
      const looksLikeOneColumn =
        headerKeys.length === 1 &&
        (headerKeys[0].indexOf('source_type') !== -1 || headerKeys[0].indexOf('content') !== -1) &&
        (headerKeys[0].indexOf(',') !== -1 || headerKeys[0].indexOf(';') !== -1);
      if (looksLikeOneColumn) {
        App.showToast(
          'CSVの列が分割されていません。Excelは「CSV UTF-8（コンマ区切り）」で保存するか、セミコロン区切りのファイルでも取り込み可能です。',
          'error'
        );
        return;
      }
      const hasContentHeader = ['content', '本文', 'Content', 'コメント内容'].some(function (k) {
        return Object.prototype.hasOwnProperty.call(rows[0], k);
      });
      if (!hasContentHeader) {
        App.showToast(
          '1行目に本文列がありません（content / 本文 / コメント内容 など）。フォーラムエクスポートCSVはそのまま取り込み可能です。',
          'error'
        );
        return;
      }

      await App.loadComments();
      const dedupe = App.buildCommentImportDedupeSets();
      const importBatchTs = Date.now();

      let successCount = 0;
      let skipCount = 0;
      let failCount = 0;

      for (let i = 0; i < rows.length; i += 1) {
        const row = rows[i];
        try {
          const explicitId = App.csvCell(row, 'comment_id', 'commentId', 'コメントID', 'コメントid');
          const commentId = explicitId
            ? String(explicitId).trim()
            : 'csv-' + importBatchTs + '-' + i;

          const contentStr = String(
            App.csvCell(row, 'content', '本文', 'Content', 'コメント内容', 'comment_body') || ''
          );
          const postedAt =
            App.csvCell(row, 'posted_at', 'postedAt', '日時', '投稿日時', '投稿日') || null;
          const authorName =
            App.csvCell(row, 'author_name', 'authorName', '投稿者名', '投稿者', 'author') || null;
          const composite = App.commentImportCompositeKey(contentStr, postedAt, authorName);

          // comment_id が明示されているCSVは ID 優先で判定し、
          // 本文重複（同文・同投稿者）で過去データを取りこぼさないようにする。
          const isDupById = dedupe.idSet.has(commentId);
          const isDupByComposite = !explicitId && dedupe.compositeSet.has(composite);
          if (isDupById || isDupByComposite) {
            skipCount += 1;
            App.elements.importResult.textContent +=
              'SKIP dup row=' + (i + 1) + ' id=' + commentId + '\n';
            continue;
          }

          await App.apiClient('POST', '/admin/comments', {
            source_type:
              App.csvCell(row, 'source_type', 'ソース', 'sourceType', 'データソース') ||
              (Object.prototype.hasOwnProperty.call(row, 'コメントID') &&
              Object.prototype.hasOwnProperty.call(row, 'コメント内容')
                ? '神大家コミュニティ'
                : 'WeStudy'),
            source_system:
              App.csvCell(row, 'source_system', 'ソース系統', 'sourceSystem') || 'WeStudy',
            source_kind:
              App.csvCell(row, 'source_kind', 'ソース種別', 'sourceKind') || 'コミュニティ情報',
            forum_category:
              App.csvCell(row, 'forum_category', '分類', 'forumCategory', 'カテゴリ') || '未分類',
            topic_title:
              App.csvCell(row, 'topic_title', '板タイトル', 'topicTitle', 'トピック名') || null,
            comment_id: commentId,
            posted_at: postedAt,
            author_name: authorName,
            author_email:
              App.csvCell(row, 'author_email', 'authorEmail', '投稿者メール', 'メール') || null,
            content: contentStr,
            parent_comment_id:
              App.csvCell(row, 'parent_comment_id', 'parentCommentId', '親コメントID', '親コメントid') ||
              null,
            ip_address:
              App.csvCell(row, 'ip_address', 'ipAddress', 'IPアドレス', 'IP アドレス', 'IP') || null,
            user_agent:
              App.csvCell(row, 'user_agent', 'userAgent', 'ユーザーエージェント', 'UA') || null
          });
          successCount += 1;
          dedupe.idSet.add(commentId);
          dedupe.compositeSet.add(composite);
          App.elements.importResult.textContent += 'OK row=' + (i + 1) + '\n';
        } catch (e) {
          failCount += 1;
          App.elements.importResult.textContent += 'NG row=' + (i + 1) + ' message=' + e.message + '\n';
        }
      }

      await App.loadComments();
      const summary =
        '新規 ' +
        successCount +
        ' / スキップ(重複) ' +
        skipCount +
        ' / 失敗 ' +
        failCount;
      App.showToast(
        'CSV取込完了 ' + summary,
        failCount === 0 ? (skipCount === 0 ? 'success' : 'info') : 'info'
      );
    } catch (error) {
      App.showToast(error.message || 'CSV取込に失敗しました', 'error');
    } finally {
      App.setLoading(false);
    }
  },

  /* CSV 行から複数候補の列名で最初の非空値を取得 */
  csvCell: (row, ...names) => {
    if (!row || !names.length) return '';
    for (let i = 0; i < names.length; i += 1) {
      const key = names[i];
      if (!Object.prototype.hasOwnProperty.call(row, key)) continue;
      const v = row[key];
      if (v === undefined || v === null) continue;
      if (String(v).trim() === '') continue;
      return v;
    }
    return '';
  },

  /* API / DB により snake_case と camelCase が混在する場合の表示・検索用 */
  commentField: (row, snakeKey) => {
    if (!row || !snakeKey) return '';
    const camel = snakeKey.replace(/_([a-z])/g, function (_, c) {
      return c.toUpperCase();
    });
    const a = row[snakeKey];
    if (a !== undefined && a !== null && String(a) !== '') return a;
    const b = row[camel];
    if (b !== undefined && b !== null) return b;
    return '';
  },

  countDelimiterOutsideQuotes: (line, delim) => {
    if (!line || !delim) return 0;
    let n = 0;
    let inQuote = false;
    for (let i = 0; i < line.length; i += 1) {
      const char = line[i];
      if (char === '"' && line[i + 1] === '"') {
        i += 1;
        continue;
      }
      if (char === '"') {
        inQuote = !inQuote;
        continue;
      }
      if (!inQuote && char === delim) n += 1;
    }
    return n;
  },

  detectCsvDelimiter: (headerLine) => {
    const tabN = App.countDelimiterOutsideQuotes(headerLine, '\t');
    const semiN = App.countDelimiterOutsideQuotes(headerLine, ';');
    const commaN = App.countDelimiterOutsideQuotes(headerLine, ',');
    if (tabN >= semiN && tabN >= commaN && tabN > 0) return '\t';
    if (semiN > commaN) return ';';
    return ',';
  },

  /* 引用内改行を含む1レコードずつに分割（RFC 4180 風。単純な split('\\n') だと本文改行で行が分裂する） */
  splitCsvRecordLines: (normalized) => {
    const records = [];
    let buf = '';
    let inQuote = false;
    for (let i = 0; i < normalized.length; i += 1) {
      const c = normalized[i];
      if (c === '"' && inQuote && normalized[i + 1] === '"') {
        buf += '"';
        i += 1;
        continue;
      }
      if (c === '"') {
        inQuote = !inQuote;
        buf += c;
        continue;
      }
      if (c === '\n' && !inQuote) {
        if (buf.trim() !== '') records.push(buf);
        buf = '';
        continue;
      }
      buf += c;
    }
    if (buf.trim() !== '') records.push(buf);
    return records;
  },

  parseCsv: (text) => {
    const normalized = String(text || '')
      .replace(/^\uFEFF/, '')
      .replace(/\r/g, '');
    const recordLines = App.splitCsvRecordLines(normalized);
    if (recordLines.length < 2) return [];
    const delimiter = App.detectCsvDelimiter(recordLines[0]);
    const headers = App.simpleCsvSplit(recordLines[0], delimiter).map(function (h) {
      return h.trim().replace(/^\uFEFF/, '');
    });

    const rows = [];
    for (let i = 1; i < recordLines.length; i += 1) {
      const values = App.simpleCsvSplit(recordLines[i], delimiter);
      const row = {};
      headers.forEach(function (key, idx) {
        row[key] = values[idx] !== undefined ? values[idx] : '';
      });
      rows.push(row);
    }
    return rows;
  },

  simpleCsvSplit: (line, delimiter) => {
    const delim = delimiter === undefined || delimiter === null ? ',' : delimiter;
    const result = [];
    let current = '';
    let inQuote = false;

    for (let i = 0; i < line.length; i += 1) {
      const char = line[i];
      if (char === '"' && line[i + 1] === '"') {
        current += '"';
        i += 1;
      } else if (char === '"') {
        inQuote = !inQuote;
      } else if (char === delim && !inQuote) {
        result.push(current);
        current = '';
      } else {
        current += char;
      }
    }
    result.push(current);
    return result;
  },

  openConfirmDialog: (title, message) => {
    return new Promise(function (resolve) {
      App.elements.confirmTitle.textContent = title || '確認';
      App.elements.confirmMessage.textContent = message || '';
      const onOk = function () {
        cleanup();
        resolve(true);
      };
      const onCancel = function () {
        cleanup();
        resolve(false);
      };
      const cleanup = function () {
        App.elements.confirmOkBtn.removeEventListener('click', onOk);
        App.elements.confirmCancelBtn.removeEventListener('click', onCancel);
        App.elements.confirmDialog.close();
      };
      App.elements.confirmOkBtn.addEventListener('click', onOk);
      App.elements.confirmCancelBtn.addEventListener('click', onCancel);
      App.elements.confirmDialog.showModal();
    });
  },

  closeConfirmDialog: () => {
    if (App.elements.confirmDialog.open) {
      App.elements.confirmDialog.close();
    }
  }
};

document.addEventListener('DOMContentLoaded', App.init);

