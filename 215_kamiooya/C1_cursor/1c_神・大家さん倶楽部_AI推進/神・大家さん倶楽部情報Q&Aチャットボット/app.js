const App = {
  state: {
    currentUser: null,
    currentSessionId: null,
    chatSessions: [],
    chatMessages: [],
    suggestedQuestions: [],
    comments: [],
    pendingUsers: [],
    loadingCount: 0
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
  },

  /* 改修: 管理者登録クリックでパスワードモーダルを開く */
  bindEvents: () => {
    document.getElementById('showLoginTabBtn').addEventListener('click', App.showLoginTab);
    document.getElementById('showRegisterTabBtn').addEventListener('click', App.showRegisterTab);
    App.elements.loginForm.addEventListener('submit', App.handleLogin);
    App.elements.registerForm.addEventListener('submit', App.handleRegister);
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
    document.getElementById('reloadPendingUsersBtn').addEventListener('click', App.loadPendingUsers);
    document.getElementById('sampleCommentBtn').addEventListener('click', App.createSampleComment);
    document.getElementById('importCsvBtn').addEventListener('click', App.importCsvComments);
    document.getElementById('sidebarToggleBtn').addEventListener('click', App.toggleSidebarMobile);
    document.getElementById('commentSearchInput').addEventListener('input', App.renderCommentTable);
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

  /* 改修: 認証画面表示時に管理者登録専用ビューを隠す */
  showAuthView: () => {
    App.elements.authView.classList.remove('hidden');
    App.elements.mainView.classList.add('hidden');
    if (App.elements.secretAdminRegisterView) {
      App.elements.secretAdminRegisterView.classList.add('hidden');
    }
  },

  showMainView: () => {
    App.elements.authView.classList.add('hidden');
    App.elements.mainView.classList.remove('hidden');
    if (App.elements.secretAdminRegisterView) {
      App.elements.secretAdminRegisterView.classList.add('hidden');
    }
  },

  showSecretAdminRegisterView: () => {
    App.elements.authView.classList.add('hidden');
    App.elements.mainView.classList.add('hidden');
    if (App.elements.secretAdminRegisterView) {
      App.elements.secretAdminRegisterView.classList.remove('hidden');
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
        App.loadComments()
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
    App.renderCommentTable();
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

    App.state.chatMessages.forEach(function (m) {
      const wrap = document.createElement('div');
      const bubble = document.createElement('div');
      const role = m.role === 'user' ? 'chat-user' : 'chat-assistant';

      bubble.className = 'chat-bubble ' + role;
      bubble.innerHTML =
        '<div class="text-[11px] text-slate-500 mb-1">' +
        App.escapeHtml(m.role) + ' ・ ' + App.escapeHtml(m.created_at || '') +
        '</div>' +
        '<div>' + App.escapeHtml(m.content || '') + '</div>';

      wrap.appendChild(bubble);
      area.appendChild(wrap);
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

  renderCommentTable: () => {
    const body = App.elements.commentTableBody;
    const keyword = (App.elements.commentSearchInput.value || '').toLowerCase();
    body.innerHTML = '';

    const filtered = App.state.comments.filter(function (row) {
      if (!keyword) return true;
      const t1 = String(App.commentField(row, 'content')).toLowerCase();
      const t2 = String(App.commentField(row, 'author_name')).toLowerCase();
      const t3 = String(App.commentField(row, 'source_type')).toLowerCase();
      return t1.indexOf(keyword) !== -1 || t2.indexOf(keyword) !== -1 || t3.indexOf(keyword) !== -1;
    });

    if (filtered.length === 0) {
      body.innerHTML = '<tr><td colspan="4" class="p-3 text-slate-500">該当データがありません</td></tr>';
      return;
    }

    filtered.forEach(function (r) {
      const tr = document.createElement('tr');
      tr.className = 'border-t';
      tr.innerHTML =
        '<td class="p-2">' + App.escapeHtml(App.commentField(r, 'posted_at')) + '</td>' +
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
        '<td class="p-2"><button class="approve-btn px-3 py-1 rounded bg-blue-600 text-white text-xs" data-id="' + App.escapeHtml(u.id) + '">承認</button></td>';
      body.appendChild(tr);
    });

    body.querySelectorAll('.approve-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        const id = btn.getAttribute('data-id');
        App.confirmApproveUser(id);
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

      await App.apiClient('POST', '/chat-sessions/' + sessionId + '/messages', {
        content: questionText
      });

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

  confirmApproveUser: async (userId) => {
    if (!userId) {
      App.showToast('承認対象IDが不正です', 'error');
      return;
    }
    const ok = await App.openConfirmDialog('ユーザー承認', 'ユーザーID ' + userId + ' を承認しますか？');
    if (!ok) return;

    App.setLoading(true);
    try {
      await App.apiClient('PUT', '/admin/users/' + userId + '/approve');
      App.showToast('ユーザーを承認しました', 'success');
      await App.loadPendingUsers();
    } catch (error) {
      App.showToast(error.message || '承認に失敗しました', 'error');
    } finally {
      App.setLoading(false);
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

          if (dedupe.idSet.has(commentId) || dedupe.compositeSet.has(composite)) {
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

  parseCsv: (text) => {
    const normalized = String(text || '')
      .replace(/^\uFEFF/, '')
      .replace(/\r/g, '');
    const lines = normalized.split('\n').filter(function (line) {
      return line.trim() !== '';
    });
    if (lines.length < 2) return [];
    const delimiter = App.detectCsvDelimiter(lines[0]);
    const headers = App.simpleCsvSplit(lines[0], delimiter).map(function (h) {
      return h.trim().replace(/^\uFEFF/, '');
    });

    const rows = [];
    for (let i = 1; i < lines.length; i += 1) {
      const values = App.simpleCsvSplit(lines[i], delimiter);
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
