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
    pendingUsers: [],
    loadingCount: 0,
    resetPasswordEmail: ''
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

  /* 改修: シークレットURL時は管理者登録画面を表示 */
  init: () => {
    App.cacheElements();
    App.bindEvents();
    if (App.isSecretAdminRoute()) {
      App.showSecretAdminRegisterView();
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
    App.elements.commentDateFilter = document.getElementById('commentDateFilter');
    App.elements.commentListMeta = document.getElementById('commentListMeta');
    App.elements.knowledgeTableBody = document.getElementById('knowledgeTableBody');
    App.elements.knowledgeSearchInput = document.getElementById('knowledgeSearchInput');
    App.elements.knowledgeListMeta = document.getElementById('knowledgeListMeta');
    App.elements.pendingUsersTableBody = document.getElementById('pendingUsersTableBody');
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
        App.showAuthView();
        App.showLoginTab();
      });
    }
    const resetBackBtn = document.getElementById('resetPasswordBackToLoginBtn');
    if (resetBackBtn) {
      resetBackBtn.addEventListener('click', function () {
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
    if (App.elements.commentDateFilter) {
      App.elements.commentDateFilter.addEventListener('change', App.renderCommentTable);
    }
    if (App.elements.deleteCommentsBtn) {
      App.elements.deleteCommentsBtn.addEventListener('click', App.deleteComments);
    }
    document.getElementById('confirmCancelBtn').addEventListener('click', App.closeConfirmDialog);
    document.querySelectorAll('.screen-tab').forEach(function (btn) {
      btn.addEventListener('click', function () {
        App.switchScreen(btn.getAttribute('data-screen'));
      });
    });
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

  showResetPasswordView: (email) => {
    App.state.resetPasswordEmail = email || '';
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

  handleForgotPasswordEmail: async (event) => {
    event.preventDefault();
    const email = (document.getElementById('forgotPasswordEmail').value || '').trim();
    if (!email) {
      App.showToast('メールアドレスは必須です', 'error');
      return;
    }
    App.setButtonLoading(App.elements.forgotPasswordSubmitBtn, true, '確認中');
    App.setLoading(true);
    try {
      const res = await App.apiClient('POST', '/auth/reset-password/check', { email: email });
      const confirmed = (res && res.email) || email;
      App.showResetPasswordView(confirmed);
    } catch (error) {
      App.showToast(error.message || 'メールアドレスの確認に失敗しました', 'error');
    } finally {
      App.setButtonLoading(App.elements.forgotPasswordSubmitBtn, false);
      App.setLoading(false);
    }
  },

  handleResetPassword: async (event) => {
    event.preventDefault();
    const email = App.state.resetPasswordEmail || '';
    const password = document.getElementById('resetPasswordNewPassword').value;
    const confirm = document.getElementById('resetPasswordConfirmPassword').value;
    if (!email) {
      App.showToast('メールアドレスが確認できません。最初からやり直してください', 'error');
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
      await App.apiClient('POST', '/auth/reset-password', {
        email: email,
        password_hash: password
      });
      App.state.resetPasswordEmail = '';
      App.showToast('パスワードを再設定しました。新しいパスワードでログインしてください', 'success');
      App.showAuthView();
      App.showLoginTab();
      const loginEmail = document.getElementById('loginEmail');
      if (loginEmail) {
        loginEmail.value = email;
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

  switchScreen: (screenName) => {
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
    App.elements.sidebar.classList.remove('mobile-open');
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
    App.state.comments = (res && res.comments) ? res.comments : [];
    App.renderCommentSourceFilterOptions();
    App.renderCommentTable();
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

  buildCitationsFromRelated: (relatedComments, relatedChunks) => {
    const citations = [];
    (relatedComments || []).forEach(function (c) {
      citations.push({
        kind: 'comment',
        sourceType: 'WeStudyコミュニティ',
        commentId: c.comment_id || c.commentId || '',
        authorName: c.author_name || c.authorName || '',
        postedAt: c.posted_at || c.postedAt || '',
        snippet: String(c.content || '').replace(/\s+/g, ' ').slice(0, 220)
      });
    });
    (relatedChunks || []).forEach(function (ch) {
      const sk = ch.source_key || '';
      const src = App.state.knowledgeSources[sk] || {};
      const start = ch.start_sec != null ? Number(ch.start_sec) : 0;
      citations.push({
        kind: 'video_chunk',
        sourceType: 'WeStudyセミナー動画',
        chunkKey: ch.chunk_key || '',
        videoTitle: src.title || sk || '（タイトル不明）',
        videoUrl: App.withVideoTimeUrl(src.video_url || '', start),
        startSec: start,
        startLabel: App.formatMmSs(start),
        snippet: String(ch.content || '').replace(/\s+/g, ' ').slice(0, 220)
      });
    });
    return citations;
  },

  openCitationInDb: (citation) => {
    if (!citation) return;
    if (citation.kind === 'video_chunk') {
      App.switchScreen('knowledge');
      if (App.elements.knowledgeSearchInput) {
        App.elements.knowledgeSearchInput.value = citation.chunkKey || citation.videoTitle || '';
        App.renderKnowledgeTable();
      }
      return;
    }
    App.switchScreen('comments');
    if (App.elements.commentSearchInput) {
      App.elements.commentSearchInput.value = citation.commentId || citation.snippet || '';
      App.renderCommentTable();
    }
  },

  renderCitationsPanel: (citations) => {
    if (!citations || !citations.length) return '';
    const items = citations.slice(0, 8).map(function (c) {
      if (c.kind === 'video_chunk') {
        const when = c.startLabel ? (c.startLabel + '（' + c.startSec + '秒）') : '';
        const openDb =
          '<button type="button" class="citation-db-link text-blue-700 underline ml-1" data-kind="video_chunk" data-key="' +
          App.escapeHtml(c.chunkKey || '') +
          '">DBで見る</button>';
        const openVideo = c.videoUrl
          ? (' <a class="text-blue-600 underline" target="_blank" rel="noopener noreferrer" href="' +
            App.escapeHtml(c.videoUrl) +
            '">動画を開く</a>')
          : '';
        return (
          '<li class="mb-1">' +
          '<span class="font-medium">[WeStudyセミナー動画]</span> ' +
          App.escapeHtml(c.videoTitle || '') +
          (when ? ' — ' + App.escapeHtml(when) : '') +
          openDb +
          openVideo +
          '<div class="text-slate-600">' +
          App.escapeHtml(c.snippet || '') +
          '</div></li>'
        );
      }
      return (
        '<li class="mb-1">' +
        '<span class="font-medium">[WeStudyコミュニティ]</span> ' +
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
    }).join('');
    return (
      '<div class="mt-3 border-t pt-2 text-xs">' +
      '<div class="font-semibold mb-1">準拠データ</div>' +
      '<ul>' +
      items +
      '</ul></div>'
    );
  },

  formatAssistantHtml: (text) => {
    const escaped = App.escapeHtml(text || '').replace(/\n/g, '<br>');
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

    App.state.chatMessages.forEach(function (m, idx) {
      const wrap = document.createElement('div');
      const bubble = document.createElement('div');
      const role = m.role === 'user' ? 'chat-user' : 'chat-assistant';
      const isLastAssistant =
        m.role === 'assistant' && idx === App.state.chatMessages.length - 1;

      bubble.className = 'chat-bubble ' + role;
      bubble.innerHTML =
        '<div class="text-[11px] text-slate-500 mb-1">' +
        App.escapeHtml(m.role) + ' ・ ' + App.escapeHtml(m.created_at || '') +
        '</div>' +
        '<div>' +
        (m.role === 'assistant' ? App.formatAssistantHtml(m.content || '') : App.escapeHtml(m.content || '')) +
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
          App.openCitationInDb({ kind: 'video_chunk', chunkKey: key });
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
  },

  hasPostedAtValue: (row) => {
    return String(App.commentField(row, 'posted_at') || '').trim() !== '';
  },

  renderCommentTable: () => {
    const body = App.elements.commentTableBody;
    const keyword = (App.elements.commentSearchInput.value || '').toLowerCase();
    const sourceFilter = (App.elements.commentSourceFilter && App.elements.commentSourceFilter.value) || '';
    const dateFilter = (App.elements.commentDateFilter && App.elements.commentDateFilter.value) || '';
    body.innerHTML = '';

    const filtered = App.state.comments.filter(function (row) {
      const t1 = String(App.commentField(row, 'content')).toLowerCase();
      const t2 = String(App.commentField(row, 'author_name')).toLowerCase();
      const t3 = String(App.commentField(row, 'source_type')).toLowerCase();
      const sourceType = String(App.commentField(row, 'source_type') || '').trim();
      const hasDate = App.hasPostedAtValue(row);
      const hitKeyword = !keyword || t1.indexOf(keyword) !== -1 || t2.indexOf(keyword) !== -1 || t3.indexOf(keyword) !== -1;
      const hitSource = !sourceFilter || sourceType === sourceFilter;
      const hitDate =
        !dateFilter ||
        (dateFilter === 'hasDate' && hasDate) ||
        (dateFilter === 'missingDate' && !hasDate);
      return hitKeyword && hitSource && hitDate;
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
      body.innerHTML = '<tr><td colspan="4" class="p-3 text-slate-500">該当データがありません</td></tr>';
      return;
    }

    filtered.forEach(function (r) {
      const tr = document.createElement('tr');
      tr.className = 'border-t';
      const postedAt = String(App.commentField(r, 'posted_at') || '').trim();
      const postedAtLabel = postedAt || '（日時なし）';
      tr.innerHTML =
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
    if (App.state.currentUser && App.state.currentUser.role !== 'admin') return;

    if (App.state.pendingUsers.length === 0) {
      body.innerHTML = '<tr><td colspan="4" class="p-3 text-slate-500">承認待ちユーザーはいません</td></tr>';
      return;
    }

    App.state.pendingUsers.forEach(function (u) {
      const tr = document.createElement('tr');
      tr.className = 'border-t';
      tr.innerHTML =
        '<td class="p-2">' + App.escapeHtml(u.id) + '</td>' +
        '<td class="p-2">' + App.escapeHtml(u.email || '') + '</td>' +
        '<td class="p-2">' + App.escapeHtml(u.status || '') + '</td>' +
        '<td class="p-2"><button class="approve-btn px-3 py-1 rounded bg-blue-600 text-white text-xs" data-id="' + App.escapeHtml(u.id) + '" data-email="' + App.escapeHtml(u.email || '') + '">承認</button></td>';
      body.appendChild(tr);
    });

    body.querySelectorAll('.approve-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        const id = btn.getAttribute('data-id');
        const email = btn.getAttribute('data-email') || '';
        App.confirmApproveUser(id, email);
      });
    });
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
      App.state.lastCitations = App.buildCitationsFromRelated(
        (msgRes && msgRes.relatedComments) || [],
        (msgRes && msgRes.relatedChunks) || []
      );
      if (msgRes && Array.isArray(msgRes.citations) && msgRes.citations.length) {
        App.state.lastCitations = msgRes.citations;
      }

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
    let applicantEmail = (email || '').trim();
    if (!applicantEmail && App.state.pendingUsers && App.state.pendingUsers.length) {
      const found = App.state.pendingUsers.find(function (u) {
        return String(u.id) === String(userId);
      });
      if (found && found.email) applicantEmail = String(found.email).trim();
    }
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

  createSampleComment: async () => {
    if (!App.state.currentUser || App.state.currentUser.role !== 'admin') {
      App.showToast('管理者のみ実行できます', 'error');
      return;
    }
    App.setLoading(true);
    try {
      await App.apiClient('POST', '/admin/comments', {
        source_type: 'WeStudy',
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

