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
    // Next.js 側で /auth/* /comments/* などをそのまま提供する
    const url = endpoint;
    const options = {
      method: method,
      headers: { "Content-Type": "application/json" }
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
          (typeof errorData.detail === "string" ? errorData.detail : "") ||
          (errorData._rawBody ? String(errorData._rawBody).trim().slice(0, 280) : "");
        const suffix = response.status ? "（HTTP " + response.status + "）" : "";
        const apiErr = new Error((msg || "APIエラーが発生しました") + suffix);
        const code = errorData.errorCode || errorData.error_code;
        if (code) {
          apiErr.errorCode = code;
        }
        throw apiErr;
      }
      if (response.status === 204) return null;
      return await response.json();
    } catch (error) {
      console.error("API Error:", error);
      throw error;
    }
  },

  escapeHtml: (str) => {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  },

  init: () => {
    App.cacheElements();
    App.bindEvents();
    App.showAuthView();
  },

  cacheElements: () => {
    App.elements.authView = document.getElementById("authView");
    App.elements.mainView = document.getElementById("mainView");
    App.elements.secretAdminRegisterView = document.getElementById("secretAdminRegisterView");
    App.elements.secretAdminRegisterForm = document.getElementById("secretAdminRegisterForm");
    App.elements.secretAdminRegisterSubmitBtn = document.getElementById(
      "secretAdminRegisterSubmitBtn"
    );
    App.elements.adminEntryBtn = document.getElementById("adminEntryBtn");
    App.elements.loginScreenAdminRegisterBtn = document.getElementById(
      "loginScreenAdminRegisterBtn"
    );
    App.elements.adminGateOverlay = document.getElementById("adminGateOverlay");
    App.elements.adminGatePasswordInput = document.getElementById("adminGatePasswordInput");
    App.elements.adminGateError = document.getElementById("adminGateError");
    App.elements.adminGateCancelBtn = document.getElementById("adminGateCancelBtn");
    App.elements.adminGateOkBtn = document.getElementById("adminGateOkBtn");

    App.elements.loginForm = document.getElementById("loginForm");
    App.elements.registerForm = document.getElementById("registerForm");
    App.elements.loginSubmitBtn = document.getElementById("loginSubmitBtn");
    App.elements.registerSubmitBtn = document.getElementById("registerSubmitBtn");
    App.elements.currentUserLabel = document.getElementById("currentUserLabel");
    App.elements.sidebar = document.getElementById("sidebar");
    App.elements.sessionList = document.getElementById("sessionList");
    App.elements.chatMessages = document.getElementById("chatMessages");
    App.elements.messageForm = document.getElementById("messageForm");
    App.elements.messageInput = document.getElementById("messageInput");
    App.elements.sendMessageBtn = document.getElementById("sendMessageBtn");
    App.elements.suggestedQuestions = document.getElementById("suggestedQuestions");
    App.elements.commentTableBody = document.getElementById("commentTableBody");
    App.elements.commentSearchInput = document.getElementById("commentSearchInput");
    App.elements.commentSourceFilter = document.getElementById("commentSourceFilter");
    App.elements.commentDateFilter = document.getElementById("commentDateFilter");
    App.elements.commentListMeta = document.getElementById("commentListMeta");
    App.elements.pendingUsersTableBody = document.getElementById("pendingUsersTableBody");
    App.elements.csvFileInput = document.getElementById("csvFileInput");
    App.elements.importResult = document.getElementById("importResult");
    App.elements.toast = document.getElementById("toast");
    App.elements.loadingOverlay = document.getElementById("loadingOverlay");
    App.elements.confirmDialog = document.getElementById("confirmDialog");
    App.elements.confirmTitle = document.getElementById("confirmTitle");
    App.elements.confirmMessage = document.getElementById("confirmMessage");
    App.elements.confirmOkBtn = document.getElementById("confirmOkBtn");
    App.elements.confirmCancelBtn = document.getElementById("confirmCancelBtn");
    App.elements.deleteSourceTypeInput = document.getElementById("deleteSourceTypeInput");
    App.elements.deleteCommentIdLikeInput = document.getElementById("deleteCommentIdLikeInput");
    App.elements.deleteCommentsBtn = document.getElementById("deleteCommentsBtn");
  },

  bindEvents: () => {
    document.getElementById("showLoginTabBtn").addEventListener("click", App.showLoginTab);
    document
      .getElementById("showRegisterTabBtn")
      .addEventListener("click", App.showRegisterTab);
    App.elements.loginForm.addEventListener("submit", App.handleLogin);
    App.elements.registerForm.addEventListener("submit", App.handleRegister);

    if (App.elements.secretAdminRegisterForm) {
      App.elements.secretAdminRegisterForm.addEventListener(
        "submit",
        App.handleSecretAdminRegister
      );
    }
    const secretBackBtn = document.getElementById("secretAdminBackToLoginBtn");
    if (secretBackBtn) {
      secretBackBtn.addEventListener("click", function () {
        App.showAuthView();
        App.showLoginTab();
      });
    }

    document.addEventListener(
      "click",
      function (ev) {
        const t = ev.target;
        if (!t || typeof t.closest !== "function") return;
        if (t.closest("#adminEntryBtn") || t.closest("#loginScreenAdminRegisterBtn")) {
          ev.preventDefault();
          App.openAdminGateDialog();
        }
      },
      true
    );
    if (App.elements.adminGateOverlay) {
      App.elements.adminGateOverlay.addEventListener("click", function (e) {
        if (e.target === App.elements.adminGateOverlay) {
          App.closeAdminGateDialog();
        }
      });
    }
    if (App.elements.adminGateCancelBtn) {
      App.elements.adminGateCancelBtn.addEventListener("click", App.closeAdminGateDialog);
    }
    if (App.elements.adminGateOkBtn) {
      App.elements.adminGateOkBtn.addEventListener("click", App.handleAdminGateSubmit);
    }
    if (App.elements.adminGatePasswordInput) {
      App.elements.adminGatePasswordInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          e.preventDefault();
          App.handleAdminGateSubmit();
        }
      });
    }

    document.getElementById("logoutBtn").addEventListener("click", App.logout);
    document.getElementById("newChatBtn").addEventListener("click", App.createNewChatPlaceholder);
    App.elements.messageForm.addEventListener("submit", App.handleSendMessage);
    document.getElementById("reloadCommentsBtn").addEventListener("click", App.loadComments);
    document
      .getElementById("reloadPendingUsersBtn")
      .addEventListener("click", App.loadPendingUsers);
    document.getElementById("sampleCommentBtn").addEventListener("click", App.createSampleComment);
    document.getElementById("importCsvBtn").addEventListener("click", App.importCsvComments);
    document.getElementById("sidebarToggleBtn").addEventListener("click", App.toggleSidebarMobile);
    document
      .getElementById("commentSearchInput")
      .addEventListener("input", App.renderCommentTable);
    if (App.elements.commentSourceFilter) {
      App.elements.commentSourceFilter.addEventListener("change", App.renderCommentTable);
    }
    if (App.elements.commentDateFilter) {
      App.elements.commentDateFilter.addEventListener("change", App.renderCommentTable);
    }
    if (App.elements.deleteCommentsBtn) {
      App.elements.deleteCommentsBtn.addEventListener("click", App.deleteComments);
    }
    document.getElementById("confirmCancelBtn").addEventListener("click", App.closeConfirmDialog);
    document.querySelectorAll(".screen-tab").forEach(function (btn) {
      btn.addEventListener("click", function () {
        App.switchScreen(btn.getAttribute("data-screen"));
      });
    });
  },

  setLoading: (isLoading) => {
    if (isLoading) App.state.loadingCount += 1;
    if (!isLoading) App.state.loadingCount = Math.max(0, App.state.loadingCount - 1);
    if (App.state.loadingCount > 0) App.elements.loadingOverlay.classList.add("active");
    if (App.state.loadingCount === 0) App.elements.loadingOverlay.classList.remove("active");
  },

  setButtonLoading: (buttonEl, isLoading, loadingText) => {
    if (!buttonEl) return;
    if (isLoading) {
      buttonEl.disabled = true;
      buttonEl.dataset.originalText = buttonEl.innerHTML;
      buttonEl.innerHTML =
        '<i class="fa-solid fa-spinner fa-spin mr-1"></i>' +
        App.escapeHtml(loadingText || "処理中");
    } else {
      buttonEl.disabled = false;
      if (buttonEl.dataset.originalText) {
        buttonEl.innerHTML = buttonEl.dataset.originalText;
      }
    }
  },

  showToast: (message, type) => {
    App.elements.toast.textContent = message || "";
    App.elements.toast.className = "toast " + (type || "info");
    App.elements.toast.classList.remove("hidden");
    window.setTimeout(function () {
      App.elements.toast.classList.add("hidden");
    }, 2600);
  },

  showAuthView: () => {
    App.elements.authView.classList.remove("hidden");
    App.elements.mainView.classList.add("hidden");
    if (App.elements.secretAdminRegisterView) {
      App.elements.secretAdminRegisterView.classList.add("hidden");
    }
  },

  showMainView: () => {
    App.elements.authView.classList.add("hidden");
    App.elements.mainView.classList.remove("hidden");
    if (App.elements.secretAdminRegisterView) {
      App.elements.secretAdminRegisterView.classList.add("hidden");
    }
  },

  showSecretAdminRegisterView: () => {
    App.elements.authView.classList.add("hidden");
    App.elements.mainView.classList.add("hidden");
    if (App.elements.secretAdminRegisterView) {
      App.elements.secretAdminRegisterView.classList.remove("hidden");
    }
  },

  openAdminGateDialog: () => {
    if (!App.elements.adminGateOverlay) {
      App.showToast("パスワード入力画面を表示できません", "error");
      return;
    }
    if (App.elements.adminGatePasswordInput) {
      App.elements.adminGatePasswordInput.value = "";
    }
    if (App.elements.adminGateError) {
      App.elements.adminGateError.textContent = "";
    }
    App.elements.adminGateOverlay.classList.remove("hidden");
    window.setTimeout(function () {
      if (App.elements.adminGatePasswordInput) {
        App.elements.adminGatePasswordInput.focus();
      }
    }, 0);
  },

  closeAdminGateDialog: () => {
    if (!App.elements.adminGateOverlay) return;
    App.elements.adminGateOverlay.classList.add("hidden");
  },

  handleAdminGateSubmit: () => {
    if (!App.elements.adminGatePasswordInput) return;
    const value = (App.elements.adminGatePasswordInput.value || "").trim();
    if (value !== "1162") {
      if (App.elements.adminGateError) {
        App.elements.adminGateError.textContent = "パスワードが一致しません";
      }
      return;
    }
    App.closeAdminGateDialog();
    App.showSecretAdminRegisterView();
  },

  showLoginTab: () => {
    document.getElementById("showLoginTabBtn").className =
      "w-1/2 py-2 rounded-md bg-blue-900 text-white";
    document.getElementById("showRegisterTabBtn").className =
      "w-1/2 py-2 rounded-md bg-slate-200 text-slate-700";
    App.elements.loginForm.classList.remove("hidden");
    App.elements.registerForm.classList.add("hidden");
  },

  showRegisterTab: () => {
    document.getElementById("showRegisterTabBtn").className =
      "w-1/2 py-2 rounded-md bg-blue-900 text-white";
    document.getElementById("showLoginTabBtn").className =
      "w-1/2 py-2 rounded-md bg-slate-200 text-slate-700";
    App.elements.registerForm.classList.remove("hidden");
    App.elements.loginForm.classList.add("hidden");
  },

  handleRegister: async (event) => {
    event.preventDefault();
    const email = document.getElementById("registerEmail").value.trim();
    const password = document.getElementById("registerPassword").value;
    if (!email || !password) {
      App.showToast("メールアドレスとパスワードは必須です", "error");
      return;
    }
    App.setButtonLoading(App.elements.registerSubmitBtn, true, "登録中");
    App.setLoading(true);
    try {
      await App.apiClient("POST", "/auth/register", {
        email: email,
        password_hash: password
      });
      App.showToast("登録申請を受け付けました（承認待ち）", "success");
      App.showLoginTab();
      App.elements.registerForm.reset();
    } catch (error) {
      App.showToast(error.message || "登録に失敗しました", "error");
    } finally {
      App.setButtonLoading(App.elements.registerSubmitBtn, false);
      App.setLoading(false);
    }
  },

  handleSecretAdminRegister: async (event) => {
    event.preventDefault();
    const email = document.getElementById("secretAdminEmail").value.trim();
    const password = document.getElementById("secretAdminPassword").value;
    const secretKey = document.getElementById("secretAdminSecretKey").value.trim();

    if (!email || !password || !secretKey) {
      App.showToast("メール・パスワード・シークレットキーは必須です", "error");
      return;
    }

    App.setButtonLoading(App.elements.secretAdminRegisterSubmitBtn, true, "登録中");
    App.setLoading(true);
    const adminBody = {
      email: email,
      password_hash: password,
      secret_key: secretKey
    };
    try {
      try {
        await App.apiClient("POST", "/auth/secret-admin-upgrade", adminBody);
      } catch (upgradeErr) {
        const msg = upgradeErr.message || "";
        const isUnregistered =
          upgradeErr.errorCode === "user_not_found" || msg.indexOf("未登録") !== -1;
        const tryRegisterFallback =
          isUnregistered || msg.indexOf("HTTP 404") !== -1 || msg.indexOf("HTTP 5") !== -1;
        if (!tryRegisterFallback) throw upgradeErr;
        await App.apiClient("POST", "/auth/secret-admin-register", adminBody);
      }
      App.showToast("管理者登録が完了しました", "success");
      App.elements.secretAdminRegisterForm.reset();
      App.showAuthView();
      App.showLoginTab();
    } catch (error) {
      App.showToast(error.message || "管理者登録に失敗しました", "error");
    } finally {
      App.setButtonLoading(App.elements.secretAdminRegisterSubmitBtn, false);
      App.setLoading(false);
    }
  },

  handleLogin: async (event) => {
    event.preventDefault();
    const email = document.getElementById("loginEmail").value.trim();
    const password = document.getElementById("loginPassword").value;
    if (!email || !password) {
      App.showToast("メールアドレスとパスワードは必須です", "error");
      return;
    }

    App.setButtonLoading(App.elements.loginSubmitBtn, true, "ログイン中");
    App.setLoading(true);
    try {
      const res = await App.apiClient("POST", "/auth/login", {
        email: email,
        password_hash: password
      });
      App.state.currentUser = res.user;
      App.afterLogin();
      App.showToast("ログインしました", "success");
    } catch (error) {
      App.showToast(error.message || "ログインに失敗しました", "error");
    } finally {
      App.setButtonLoading(App.elements.loginSubmitBtn, false);
      App.setLoading(false);
    }
  },

  afterLogin: async () => {
    App.showMainView();
    App.elements.currentUserLabel.textContent =
      App.state.currentUser.email + " (" + App.state.currentUser.role + ")";

    const isAdmin = App.state.currentUser.role === "admin";
    document.getElementById("adminUsersTabBtn").classList.toggle("hidden", !isAdmin);
    document.getElementById("adminDataTabBtn").classList.toggle("hidden", !isAdmin);

    App.switchScreen("chat");
    await App.refreshInitialData();
  },

  refreshInitialData: async () => {
    App.setLoading(true);
    try {
      await Promise.all([App.loadChatSessions(), App.loadSuggestedQuestions(), App.loadComments()]);
      if (App.state.currentUser.role === "admin") {
        await App.loadPendingUsers();
      }
      App.renderAll();
    } catch (error) {
      App.showToast(error.message || "初期データ取得に失敗しました", "error");
    } finally {
      App.setLoading(false);
    }
  },

  logout: async () => {
    try {
      await App.apiClient("POST", "/auth/logout", {});
    } catch (e) {
      console.warn(e);
    }
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
    App.showToast("ログアウトしました", "info");
  },

  switchScreen: (screenName) => {
    document.querySelectorAll(".screen-view").forEach(function (el) {
      el.classList.add("hidden");
    });
    const map = {
      chat: "chatScreen",
      comments: "commentsScreen",
      adminUsers: "adminUsersScreen",
      adminData: "adminDataScreen"
    };
    const targetId = map[screenName];
    if (targetId) {
      const target = document.getElementById(targetId);
      if (target) target.classList.remove("hidden");
    }
    document.querySelectorAll(".screen-tab").forEach(function (btn) {
      if (btn.getAttribute("data-screen") === screenName) {
        btn.classList.add("bg-slate-100");
      } else {
        btn.classList.remove("bg-slate-100");
      }
    });
    App.elements.sidebar.classList.remove("mobile-open");
  },

  toggleSidebarMobile: () => {
    App.elements.sidebar.classList.toggle("mobile-open");
  },

  loadChatSessions: async () => {
    if (!App.state.currentUser || !App.state.currentUser.id) return;
    const res = await App.apiClient(
      "GET",
      "/users/" + App.state.currentUser.id + "/chat-sessions"
    );
    App.state.chatSessions = res && res.sessions ? res.sessions : [];
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
      App.showToast("セッションIDが未選択です", "error");
      return;
    }
    const res = await App.apiClient("GET", "/chat-sessions/" + sessionId);
    App.state.chatMessages = res && res.messages ? res.messages : [];
    App.renderChatMessages();
    App.state.currentSessionId = sessionId;
    App.renderSessionList();
  },

  loadSuggestedQuestions: async () => {
    const res = await App.apiClient("GET", "/suggested-questions");
    App.state.suggestedQuestions = res && res.questions ? res.questions : [];
    App.renderSuggestedQuestions();
  },

  loadComments: async () => {
    const res = await App.apiClient("GET", "/comments");
    App.state.comments = res && res.comments ? res.comments : [];
    App.renderCommentSourceFilterOptions();
    App.renderCommentTable();
  },

  loadPendingUsers: async () => {
    if (!App.state.currentUser || App.state.currentUser.role !== "admin") return;
    const res = await App.apiClient("GET", "/admin/users/pending");
    App.state.pendingUsers = res && res.users ? res.users : [];
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
    list.innerHTML = "";
    if (App.state.chatSessions.length === 0) {
      list.innerHTML = '<li class="text-sm text-slate-500">履歴がありません</li>';
      return;
    }
    App.state.chatSessions.forEach(function (s) {
      const li = document.createElement("li");
      const active = App.state.currentSessionId === s.id ? "active" : "";
      li.className =
        "session-item border rounded p-2 cursor-pointer hover:bg-slate-50 " + active;
      li.innerHTML =
        '<div class="text-sm font-medium">' +
        App.escapeHtml(s.title || "無題") +
        "</div>" +
        '<div class="text-xs text-slate-500 mt-1">' +
        App.escapeHtml(s.created_at || "") +
        "</div>";
      li.addEventListener("click", function () {
        App.loadSessionDetails(s.id);
        App.switchScreen("chat");
      });
      list.appendChild(li);
    });
  },

  renderChatMessages: () => {
    const area = App.elements.chatMessages;
    area.innerHTML = "";
    if (App.state.chatMessages.length === 0) {
      area.innerHTML =
        '<p class="text-sm text-slate-500">メッセージはまだありません。質問を送信してください。</p>';
      return;
    }
    App.state.chatMessages.forEach(function (m) {
      const wrap = document.createElement("div");
      const bubble = document.createElement("div");
      const role = m.role === "user" ? "chat-user" : "chat-assistant";
      bubble.className = "chat-bubble " + role;
      bubble.innerHTML =
        '<div class="text-[11px] text-slate-500 mb-1">' +
        App.escapeHtml(m.role) +
        " ・ " +
        App.escapeHtml(m.created_at || "") +
        "</div>" +
        "<div>" +
        App.escapeHtml(m.content || "") +
        "</div>";
      wrap.appendChild(bubble);
      area.appendChild(wrap);
    });
    area.scrollTop = area.scrollHeight;
  },

  renderSuggestedQuestions: () => {
    const box = App.elements.suggestedQuestions;
    box.innerHTML = "";
    if (App.state.suggestedQuestions.length === 0) {
      box.innerHTML = '<span class="text-xs text-slate-400">提案はまだありません</span>';
      return;
    }
    App.state.suggestedQuestions.forEach(function (q) {
      const btn = document.createElement("button");
      btn.className = "text-xs px-3 py-1 rounded-full border bg-slate-50 hover:bg-blue-50";
      btn.innerHTML = App.escapeHtml(q.question_text || "");
      btn.addEventListener("click", async function () {
        try {
          if (q.id) await App.apiClient("PUT", "/suggested-questions/" + q.id + "/increment");
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
    const current = select.value || "";
    const sources = Array.from(
      new Set(
        (App.state.comments || [])
          .map(function (row) {
            return String(row.source_type || row.sourceType || "").trim();
          })
          .filter(Boolean)
      )
    ).sort();
    select.innerHTML = '<option value="">全ソース</option>';
    sources.forEach(function (source) {
      const opt = document.createElement("option");
      opt.value = source;
      opt.textContent = source;
      select.appendChild(opt);
    });
    if (current && sources.indexOf(current) !== -1) select.value = current;
  },

  hasPostedAtValue: (row) => {
    const v = row.posted_at || row.postedAt;
    return String(v || "").trim() !== "";
  },

  renderCommentTable: () => {
    const body = App.elements.commentTableBody;
    const keyword = (App.elements.commentSearchInput.value || "").toLowerCase();
    const sourceFilter =
      (App.elements.commentSourceFilter && App.elements.commentSourceFilter.value) || "";
    const dateFilter = (App.elements.commentDateFilter && App.elements.commentDateFilter.value) || "";
    body.innerHTML = "";

    const filtered = App.state.comments.filter(function (row) {
      const t1 = String(row.content || "").toLowerCase();
      const t2 = String(row.author_name || row.authorName || "").toLowerCase();
      const t3 = String(row.source_type || row.sourceType || "").toLowerCase();
      const sourceType = String(row.source_type || row.sourceType || "").trim();
      const hasDate = App.hasPostedAtValue(row);
      const hitKeyword =
        !keyword || t1.indexOf(keyword) !== -1 || t2.indexOf(keyword) !== -1 || t3.indexOf(keyword) !== -1;
      const hitSource = !sourceFilter || sourceType === sourceFilter;
      const hitDate =
        !dateFilter ||
        (dateFilter === "hasDate" && hasDate) ||
        (dateFilter === "missingDate" && !hasDate);
      return hitKeyword && hitSource && hitDate;
    });

    const totalCount = App.state.comments.length;
    const missingDateCount = App.state.comments.reduce(function (n, row) {
      return n + (App.hasPostedAtValue(row) ? 0 : 1);
    }, 0);
    if (App.elements.commentListMeta) {
      App.elements.commentListMeta.textContent =
        "表示 " + filtered.length + " / 全 " + totalCount + " 件（日時なし " + missingDateCount + " 件）";
    }

    if (filtered.length === 0) {
      body.innerHTML = '<tr><td colspan="4" class="p-3 text-slate-500">該当データがありません</td></tr>';
      return;
    }

    filtered.forEach(function (r) {
      const tr = document.createElement("tr");
      tr.className = "border-t";
      const postedAt = String(r.posted_at || r.postedAt || "").trim();
      const postedAtLabel = postedAt || "（日時なし）";
      tr.innerHTML =
        '<td class="p-2">' +
        App.escapeHtml(postedAtLabel) +
        (postedAt ? "" : ' <span class="text-[10px] text-amber-700">missing</span>') +
        "</td>" +
        '<td class="p-2">' + App.escapeHtml(r.source_type || r.sourceType || "") + "</td>" +
        '<td class="p-2">' + App.escapeHtml(r.author_name || r.authorName || "") + "</td>" +
        '<td class="p-2">' + App.escapeHtml(String(r.content || "").slice(0, 180)) + "</td>";
      body.appendChild(tr);
    });
  },

  renderPendingUsers: () => {
    const body = App.elements.pendingUsersTableBody;
    body.innerHTML = "";
    if (App.state.currentUser && App.state.currentUser.role !== "admin") return;
    if (App.state.pendingUsers.length === 0) {
      body.innerHTML = '<tr><td colspan="4" class="p-3 text-slate-500">承認待ちユーザーはいません</td></tr>';
      return;
    }
    App.state.pendingUsers.forEach(function (u) {
      const tr = document.createElement("tr");
      tr.className = "border-t";
      tr.innerHTML =
        '<td class="p-2">' + App.escapeHtml(u.id) + "</td>" +
        '<td class="p-2">' + App.escapeHtml(u.email || "") + "</td>" +
        '<td class="p-2">' + App.escapeHtml(u.status || "") + "</td>" +
        '<td class="p-2"><button class="approve-btn px-3 py-1 rounded bg-blue-600 text-white text-xs" data-id="' +
        App.escapeHtml(u.id) +
        '">承認</button></td>';
      body.appendChild(tr);
    });
    body.querySelectorAll(".approve-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const id = btn.getAttribute("data-id");
        App.confirmApproveUser(id);
      });
    });
  },

  createNewChatPlaceholder: () => {
    App.state.currentSessionId = null;
    App.state.chatMessages = [];
    App.renderChatMessages();
    App.switchScreen("chat");
    App.showToast("新しいチャットを開始できます", "info");
  },

  handleSendMessage: async (event) => {
    event.preventDefault();
    const text = App.elements.messageInput.value.trim();
    if (!text) return;
    await App.sendQuestion(text, false);
  },

  sendQuestion: async (questionText, fromSuggested) => {
    if (!questionText) {
      App.showToast("質問内容が空です", "error");
      return;
    }
    if (!App.state.currentUser || !App.state.currentUser.id) {
      App.showToast("ユーザー情報が取得できません", "error");
      return;
    }
    App.setButtonLoading(App.elements.sendMessageBtn, true, "送信中");
    App.setLoading(true);
    try {
      let sessionId = App.state.currentSessionId;
      if (!sessionId) {
        const sessionRes = await App.apiClient("POST", "/chat-sessions", {
          user_id: App.state.currentUser.id,
          initial_message: questionText
        });
        sessionId = sessionRes.id;
        App.state.currentSessionId = sessionId;
        await App.loadChatSessions();
      }
      await App.apiClient("POST", "/chat-sessions/" + sessionId + "/messages", {
        content: questionText
      });
      if (!fromSuggested) {
        await App.createSuggestedQuestionIfNeeded(questionText);
      }
      await App.loadSessionDetails(sessionId);
      await App.loadSuggestedQuestions();
      App.elements.messageInput.value = "";
      App.showToast("送信しました", "success");
    } catch (error) {
      App.showToast(error.message || "送信に失敗しました", "error");
    } finally {
      App.setButtonLoading(App.elements.sendMessageBtn, false);
      App.setLoading(false);
    }
  },

  createSuggestedQuestionIfNeeded: async (questionText) => {
    const normalized = String(questionText || "").trim();
    if (!normalized) return;
    const exists = App.state.suggestedQuestions.some(function (q) {
      return String(q.question_text || "").trim() === normalized;
    });
    if (exists) return;
    try {
      await App.apiClient("POST", "/suggested-questions", { question_text: normalized });
    } catch (e) {
      console.warn("suggested create skipped", e);
    }
  },

  confirmApproveUser: async (userId) => {
    const ok = await App.openConfirmDialog("ユーザー承認", "ユーザーID " + userId + " を承認しますか？");
    if (!ok) return;
    App.setLoading(true);
    try {
      await App.apiClient("PUT", "/admin/users/" + userId + "/approve", {});
      App.showToast("ユーザーを承認しました", "success");
      await App.loadPendingUsers();
    } catch (error) {
      App.showToast(error.message || "承認に失敗しました", "error");
    } finally {
      App.setLoading(false);
    }
  },

  // admin data ops (CSV/import/delete) はサーバAPI実装後に有効化される
  createSampleComment: async () => {
    if (!App.state.currentUser || App.state.currentUser.role !== "admin") {
      App.showToast("管理者のみ実行できます", "error");
      return;
    }
    App.setLoading(true);
    try {
      await App.apiClient("POST", "/admin/comments", {
        source_type: "WeStudy",
        comment_id: "sample-" + String(Date.now()),
        posted_at: new Date().toISOString(),
        author_name: "System",
        author_email: "system@example.com",
        content: "サンプルコメントです。",
        parent_comment_id: "",
        ip_address: "127.0.0.1",
        user_agent: navigator.userAgent
      });
      await App.loadComments();
      App.showToast("サンプル登録完了", "success");
    } catch (error) {
      App.showToast(error.message || "登録に失敗しました", "error");
    } finally {
      App.setLoading(false);
    }
  },

  importCsvComments: async () => {
    App.showToast("CSV取込は次のステップで有効化します", "info");
  },

  deleteComments: async () => {
    App.showToast("削除は次のステップで有効化します", "info");
  },

  openConfirmDialog: (title, message) => {
    return new Promise(function (resolve) {
      App.elements.confirmTitle.textContent = title || "確認";
      App.elements.confirmMessage.textContent = message || "";
      const onOk = function () {
        cleanup();
        resolve(true);
      };
      const onCancel = function () {
        cleanup();
        resolve(false);
      };
      const cleanup = function () {
        App.elements.confirmOkBtn.removeEventListener("click", onOk);
        App.elements.confirmCancelBtn.removeEventListener("click", onCancel);
        App.elements.confirmDialog.close();
      };
      App.elements.confirmOkBtn.addEventListener("click", onOk);
      App.elements.confirmCancelBtn.addEventListener("click", onCancel);
      App.elements.confirmDialog.showModal();
    });
  },

  closeConfirmDialog: () => {
    if (App.elements.confirmDialog.open) App.elements.confirmDialog.close();
  }
};

document.addEventListener("DOMContentLoaded", App.init);

