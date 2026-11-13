const App = {
  // Offline repair candidate: stay on the existing backend until an approved cutover.
  authGatewayBase: '', // Release publisher sets the verified gateway URL.
  // 公開 Edge URL（シークレットは /semantic-search-config から取得）
  semanticEdgeUrl: 'https://mwubzgefkkjjbingrmqu.supabase.co/functions/v1/semantic-search',
  _semanticSecret: null,

  state: {
    currentUser: null,
    // 段階公開スイッチ: サーバーが「この人に見えている」と返した機能だけ（/features）
    features: {},
    feedbackByMessage: {},
    featureViewNew: true,
    viewAsMember: false,
    authToken: '',
    attachmentToken: '',
    attachmentIndex: {},
    referenceComments: {},
    attachmentLoading: false,
    attachmentStatus: '',
    attachmentGeneration: 0,
    attachmentDetailCommentId: '',
    currentSessionId: null,
    chatSessions: [],
    chatMessages: [],
    suggestedQuestions: [],
    comments: [],
    knowledgeChunks: [],
    knowledgeSources: {},
    lastCitations: [],
    citationsByMessageId: {},
    openchatLogs: [],
    // 取得元正本 open_chat_routes.yaml の全37ルーム。直近200投稿から選択肢を作らない。
    openchatRooms: [
      '01運営より全体周知G【神大家】', '02初心者G【神大家】', '03 YouTube集中学習【神大家】',
      '10-1関東信越_物件紹介G【神大家】', '10-2関東信越_相談G【神大家】',
      '11-1関西_物件紹介G【神大家】', '11-2関西_相談G【神大家】',
      '12-1東海北陸_物件紹介G【神大家】', '12-2東海北陸_相談G【神大家】',
      '13-1九州沖縄_物件紹介G【神大家】', '13-2九州沖縄_相談G【神大家】',
      '14-1北海道_物件紹介G【神大家】', '14-2北海道_相談G【神大家】',
      '15-1東北_物件紹介G【神大家】', '15-2東北_相談G【神大家】',
      '16-1中国/四国_物件紹介G【神大家】', '16-2中国/四国_相談G【神大家】',
      '20戸建にチャレンジ!G【神大家】', '21中古APにチャレンジ!G【神大家】',
      '22新築APにチャレンジ!G【神大家】', '23再生AP/MSにチャレンジ!!【神大家】',
      '24DIYにチャレンジ!G【神大家】', '25神コンセプト物件にチャレンジ!【神大家】',
      '26RC鉄骨など大規模物件G【神大家】', '30空室相談G【神大家】', '31修繕相談G【神大家】',
      '32売却相談G【神大家】', '33融資相談G【神大家】', '34保険相談G【神大家】',
      '35税金/確定申告G【神大家】', '39その他相談/共有G【神大家】', '50相続対策G【神大家】',
      '51多法人スキーム情報共有【神大家】', '52障害者GH情報交換【神大家】',
      '53海外不動産 情報交換【神大家】', '54太陽光 共有G【神大家】', '55自営業/事業者G【神大家】'
    ].map(function (title) { return { chat_title: title }; }),
    forumCategoryLookup: null,
    pendingUsers: [],
    approvedUsers: [],
    roleRequestUsers: [],
    members: [],
    analyticsOverview: null,
    currentScreen: 'chat',
    returnScreen: null,
    semanticMode: false,
    deepMode: false,
    semanticForced: false,
    loadingCount: 0,
    sendAbortController: null,
    pendingAnswerRequest: null,
    answerJobStatus: '',
    pendingQuestionText: '',
    preferFastSummary: false,
    resetPasswordEmail: '',
    resetPasswordToken: '',
    masterTransferToken: '',
    masterTransferInfo: null
  },

  elements: {},

  apiClient: async (method, endpoint, body = null, fetchOptions = null) => {
    const url = (App.authGatewayBase || '/miniAppApi/be_nXbcTm3EumRbotHtAwGGXb45raHz0') + endpoint;
    const options = {
      method: method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (App.authGatewayBase && App.state.authToken) options.headers.Authorization = 'Bearer ' + App.state.authToken;
    if (body) options.body = JSON.stringify(body);
    if (fetchOptions && fetchOptions.signal) options.signal = fetchOptions.signal;
    try {
      const response = await fetch(url, options);
      if (!response.ok) {
        if (response.status === 401 && App.authGatewayBase && App.state.authToken) {
          App.state.authToken = ''; App.state.attachmentToken = ''; App.state.currentUser = null; App.showAuthView();
        }
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
        apiErr.httpStatus=response.status;
        const code = errorData.errorCode || errorData.error_code || errorData.error;
        if (code) {
          apiErr.errorCode = code;
        }
        throw apiErr;
      }
      if (response.status === 204) return null;
      return await response.json();
    } catch (error) {
      if (error && error.name === 'AbortError') throw error;
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

  /* Phase4: #reset-password?token= / マスター移譲: #master-transfer?token= */
  init: () => {
    App.cacheElements();
    App.bindEvents();
    // この端末で配色が見えていた人は、ログイン画面のタブから新しいアイコンにする
    if (document.documentElement.classList.contains('theme-a')) App.applyAppIcon(true);
    App.hydrateSemanticMode();
    const resetToken = App.parseResetPasswordTokenFromHash();
    if (resetToken) {
      App.openResetPasswordFromToken(resetToken);
      return;
    }
    const xferToken = App.parseMasterTransferTokenFromHash();
    if (xferToken) {
      App.openMasterTransferFromToken(xferToken);
      return;
    }
    try {
      const saved = sessionStorage.getItem('master_xfer_token') || '';
      if (saved) {
        App.openMasterTransferFromToken(saved);
        return;
      }
    } catch (e) {
      /* ignore */
    }
    App.showAuthView();
  },

  // 改善機能の段階公開（2026-11-10）。判定の正本はサーバー。ここは表示の切り替えだけ。
  featureLabels: { cost_saving: '(1)使用量の削減', answer_feedback: '(2)回答の評価', auto_approval: '(3)自動承認', design_theme: '(5)デザイン', change_log: '改善履歴', conversation_signals: 'うまくいかなかった会話', chat_context: '前の質問の引き継ぎ', keyword_all: 'キーワード検索（全データ）', ranking_themes: '(4)質問ランキング・講座テーマ案' },
  featureOn: (name) => !!(App.state.features && App.state.features[name] && App.state.featureViewNew),
  loadFeatures: async () => {
    App.state.features = {};
    if (!App.authGatewayBase) return; // 旧バックエンドには /features が無い → 全部オフ
    try {
      const r = await App.apiClient('GET', '/features');
      if (r && r.features && typeof r.features === 'object') App.state.features = r.features;
    } catch (e) {
      App.state.features = {};
    }
    try {
      App.state.featureViewNew = localStorage.getItem('qa_feature_view_new') !== '0';
      App.state.viewAsMember = localStorage.getItem('qa_view_as_member') === '1';
    } catch (e) { /* ignore */ }
  },
  // (5) ロゴに合わせた配色（案A）。見た目だけなので画面側の切り替えで足りる（色は index.html と style.css の html.theme-a）。
  // ログイン前の画面にも出せるよう、この端末で一度見えた人は覚えておく（見えない人がログインしたら消す）。
  applyTheme: () => {
    const on = App.featureOn('design_theme');
    if (document.documentElement) document.documentElement.classList.toggle('theme-a', on);
    // アプリ名「神大家AIナビ」（2026-11-11 目黒さん「一旦これで」）。配色と同じスイッチの人だけ。
    document.title = on ? '神大家AIナビ' : '神・大家さん倶楽部Q&Aチャットボット';
    App.applyAppIcon(on);
    try { if (on) localStorage.setItem('qa_design_theme', '1'); else localStorage.removeItem('qa_design_theme'); } catch (e) { /* ignore */ }
  },
  // タブのアイコン（2026-11-11 松野さん「ラ」の字は LINE っぽいので変えたい）。配色と同じスイッチの人だけ。
  // 案1「神」の字 / 案2 家マーク。APP_ICON_CHOICE で切り替え。
  APP_ICON_CHOICE: 'kami',
  APP_ICONS: {
    kami: "data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22%3E%3Crect width=%2264%22 height=%2264%22 rx=%2214%22 fill=%22%2311366A%22/%3E%3Crect x=%2210%22 y=%2252%22 width=%2244%22 height=%225%22 rx=%222.5%22 fill=%22%23FE910B%22/%3E%3Ctext x=%2232%22 y=%2245%22 text-anchor=%22middle%22 font-family=%22'Noto Sans JP','Hiragino Sans','Yu Gothic',sans-serif%22 font-weight=%22700%22 font-size=%2240%22 fill=%22%23fff%22%3E%E7%A5%9E%3C/text%3E%3C/svg%3E",
    ie: "data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22%3E%3Crect width=%2264%22 height=%2264%22 rx=%2214%22 fill=%22%2311366A%22/%3E%3Cpath d=%22M32 11 L56 32 H49 V54 H15 V32 H8 Z%22 fill=%22%23FE910B%22/%3E%3Crect x=%2227%22 y=%2238%22 width=%2210%22 height=%2216%22 rx=%221.5%22 fill=%22%2311366A%22/%3E%3Crect x=%2219%22 y=%2236%22 width=%226%22 height=%226%22 fill=%22%23fff%22/%3E%3Crect x=%2239%22 y=%2236%22 width=%226%22 height=%226%22 fill=%22%23fff%22/%3E%3C/svg%3E",
  },
  applyAppIcon: (on) => {
    const head = document.head;
    if (!head) return;
    let link = document.getElementById('appIconLink');
    if (!on) { if (link) link.remove(); document.querySelectorAll('link[data-app-icon-hidden]').forEach((l) => { l.rel = l.getAttribute('data-app-icon-hidden'); l.removeAttribute('data-app-icon-hidden'); }); return; }
    document.querySelectorAll('link[rel~="icon"]').forEach((l) => { if (l.id !== 'appIconLink') { l.setAttribute('data-app-icon-hidden', l.rel); l.rel = 'x-icon-off'; } });
    if (!link) { link = document.createElement('link'); link.id = 'appIconLink'; link.rel = 'icon'; link.type = 'image/svg+xml'; head.appendChild(link); }
    link.href = App.APP_ICONS[App.APP_ICON_CHOICE] || App.APP_ICONS.kami;
  },
  // 文字の大きさ（標準/大/特大）。年配の会員にも読みやすく（2026-11-11 松野さん）。端末ごとに覚える。
  applyTextSize: (size) => {
    const v = (size === 'l' || size === 'xl') ? size : 'm';
    const root = document.documentElement;
    if (root) { if (v === 'm') root.removeAttribute('data-text-size'); else root.setAttribute('data-text-size', v); }
    try { if (v === 'm') localStorage.removeItem('qa_text_size'); else localStorage.setItem('qa_text_size', v); } catch (e) { /* ignore */ }
    document.querySelectorAll('[data-text-size-btn]').forEach((b) => b.setAttribute('aria-pressed', b.getAttribute('data-text-size-btn') === v ? 'true' : 'false'));
  },
  initTextSize: () => {
    let cur = 'm';
    try { cur = localStorage.getItem('qa_text_size') || 'm'; } catch (e) { /* ignore */ }
    App.applyTextSize(cur);
    document.addEventListener('click', (ev) => {
      const b = ev.target && ev.target.closest ? ev.target.closest('[data-text-size-btn]') : null;
      if (b) App.applyTextSize(b.getAttribute('data-text-size-btn'));
    });
  },
  renderFeaturePreviewBar: () => {
    const bar = document.getElementById('featurePreviewBar');
    if (!bar) return;
    const names = Object.keys(App.state.features || {});
    bar.classList.toggle('hidden', names.length === 0);
    if (!names.length) return;
    const viewNew = document.getElementById('featureViewNewToggle');
    const asMember = document.getElementById('featureAsMemberToggle');
    viewNew.checked = !!App.state.featureViewNew;
    asMember.checked = !!App.state.viewAsMember;
    document.getElementById('featurePreviewList').textContent = names.map(function (n) {
      return (App.featureLabels[n] || n) + (App.state.features[n].members ? '（会員にも公開中）' : '（会員には未公開）');
    }).join(' / ');
    if (!bar.dataset.bound) {
      bar.dataset.bound = '1';
      viewNew.addEventListener('change', function () {
        App.state.featureViewNew = viewNew.checked;
        try { localStorage.setItem('qa_feature_view_new', viewNew.checked ? '1' : '0'); } catch (e) { /* ignore */ }
        App.afterLogin();
      });
      asMember.addEventListener('change', function () {
        App.state.viewAsMember = asMember.checked;
        try { localStorage.setItem('qa_view_as_member', asMember.checked ? '1' : '0'); } catch (e) { /* ignore */ }
        App.afterLogin();
      });
    }
  },

  isStaffAdmin: () => {
    if (App.state.viewAsMember && Object.keys(App.state.features || {}).length) return false;
    const role = App.state.currentUser && App.state.currentUser.role;
    return role === 'admin' || role === 'master_admin';
  },

  isMasterAdmin: () => {
    if (App.state.viewAsMember && Object.keys(App.state.features || {}).length) return false;
    return !!(App.state.currentUser && App.state.currentUser.role === 'master_admin');
  },

  cacheElements: () => {
    App.elements.authView = document.getElementById('authView');
    App.elements.mainView = document.getElementById('mainView');
    App.elements.forgotPasswordView = document.getElementById('forgotPasswordView');
    App.elements.resetPasswordView = document.getElementById('resetPasswordView');
    App.elements.forgotPasswordForm = document.getElementById('forgotPasswordForm');
    App.elements.resetPasswordForm = document.getElementById('resetPasswordForm');
    App.elements.forgotPasswordSubmitBtn = document.getElementById('forgotPasswordSubmitBtn');
    App.elements.resetPasswordSubmitBtn = document.getElementById('resetPasswordSubmitBtn');
    App.elements.masterTransferView = document.getElementById('masterTransferView');
    App.elements.masterTransferAcceptBtn = document.getElementById('masterTransferAcceptBtn');
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
    App.elements.semanticModeToggle = document.getElementById('semanticModeToggle');
    App.elements.semanticSearchWarningDialog = document.getElementById('semanticSearchWarningDialog');
    App.elements.semanticWarningOkBtn = document.getElementById('semanticWarningOkBtn');
    App.elements.semanticWarningCancelBtn = document.getElementById('semanticWarningCancelBtn');
    App.elements.semanticWarningCloseBtn = document.getElementById('semanticWarningCloseBtn');
    App.elements.suggestedQuestions = document.getElementById('suggestedQuestions');
    App.elements.commentTableBody = document.getElementById('commentTableBody');
    App.elements.commentSearchInput = document.getElementById('commentSearchInput');
    App.elements.commentAttachmentsOnly = document.getElementById('commentAttachmentsOnly');
    App.elements.commentCategoryFilter = document.getElementById('commentCategoryFilter');
    App.elements.commentDateFilter = document.getElementById('commentDateFilter');
    App.elements.commentListMeta = document.getElementById('commentListMeta');
    App.elements.lessonTableBody = document.getElementById('lessonTableBody');
    App.elements.lessonSearchInput = document.getElementById('lessonSearchInput');
    App.elements.lessonCourseTabFilter = document.getElementById('lessonCourseTabFilter');
    App.elements.lessonListMeta = document.getElementById('lessonListMeta');
    App.elements.lessonsBackBar = document.getElementById('lessonsBackBar');
    App.elements.lessonsBackBtn = document.getElementById('lessonsBackBtn');
    App.elements.openchatTableBody = document.getElementById('openchatTableBody');
    App.elements.openchatSearchInput = document.getElementById('openchatSearchInput');
    App.elements.openchatTitleFilter = document.getElementById('openchatTitleFilter');
    App.elements.openchatAttachmentsOnly = document.getElementById('openchatAttachmentsOnly');
    App.elements.openchatListMeta = document.getElementById('openchatListMeta');
    App.elements.openchatBackBar = document.getElementById('openchatBackBar');
    App.elements.openchatBackBtn = document.getElementById('openchatBackBtn');
    App.elements.openchatBackLabel = document.getElementById('openchatBackLabel');
    App.elements.reloadOpenchatBtn = document.getElementById('reloadOpenchatBtn');
    App.elements.lessonsBackLabel = document.getElementById('lessonsBackLabel');
    App.elements.knowledgeTableBody = document.getElementById('knowledgeTableBody');
    App.elements.knowledgeSearchInput = document.getElementById('knowledgeSearchInput');
    App.elements.knowledgeListMeta = document.getElementById('knowledgeListMeta');
    App.elements.allSearchForm = document.getElementById('allSearchForm');
    App.elements.allSearchInput = document.getElementById('allSearchInput');
    App.elements.allSearchMeta = document.getElementById('allSearchMeta');
    App.elements.allSearchResults = document.getElementById('allSearchResults');
    App.elements.pendingUsersTableBody = document.getElementById('pendingUsersTableBody');
    App.elements.pendingUsersSelectAll = document.getElementById('pendingUsersSelectAll');
    App.elements.bulkApprovePendingUsersBtn = document.getElementById('bulkApprovePendingUsersBtn');
    App.elements.approvedUsersTableBody = document.getElementById('approvedUsersTableBody');
    App.elements.adminsTableBody = document.getElementById('adminsTableBody');
    App.elements.roleRequestsTableBody = document.getElementById('roleRequestsTableBody');
    App.elements.membersTableBody = document.getElementById('membersTableBody');
    App.elements.membersListMeta = document.getElementById('membersListMeta');
    App.elements.membersCsvFileInput = document.getElementById('membersCsvFileInput');
    App.elements.membersImportResult = document.getElementById('membersImportResult');
    App.elements.csvFileInput = document.getElementById('csvFileInput');
    App.elements.importResult = document.getElementById('importResult');
    App.elements.toast = document.getElementById('toast');
    App.elements.loadingOverlay = document.getElementById('loadingOverlay');
    App.elements.fastSummaryLink = document.getElementById('fastSummaryLink');
    App.elements.confirmDialog = document.getElementById('confirmDialog');
    App.elements.confirmTitle = document.getElementById('confirmTitle');
    App.elements.confirmMessage = document.getElementById('confirmMessage');
    App.elements.confirmOkBtn = document.getElementById('confirmOkBtn');
    App.elements.confirmCancelBtn = document.getElementById('confirmCancelBtn');
    App.elements.commentDetailDialog = document.getElementById('commentDetailDialog');
    App.elements.commentDetailTitle = document.getElementById('commentDetailTitle');
    App.elements.commentDetailMeta = document.getElementById('commentDetailMeta');
    App.elements.commentDetailBody = document.getElementById('commentDetailBody');
    App.elements.commentDetailCloseBtn = document.getElementById('commentDetailCloseBtn');
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
    if (App.elements.masterTransferAcceptBtn) {
      App.elements.masterTransferAcceptBtn.addEventListener('click', App.acceptMasterTransfer);
    }
    const xferBackBtn = document.getElementById('masterTransferBackToLoginBtn');
    if (xferBackBtn) {
      xferBackBtn.addEventListener('click', function () {
        App.persistMasterTransferToken(App.state.masterTransferToken || '');
        App.clearMasterTransferHash();
        App.showAuthView();
        App.showLoginTab();
      });
    }
    const cancelXferBtn = document.getElementById('cancelMasterTransferBtn');
    if (cancelXferBtn) {
      cancelXferBtn.addEventListener('click', App.cancelMasterTransfer);
    }
    const resumeAnswerBtn=document.getElementById('resumeAnswerBtn');
    if(resumeAnswerBtn)resumeAnswerBtn.addEventListener('click',()=>App.resumePendingAnswer());
    const retryAttachmentsBtn=document.getElementById('retryAttachmentsBtn');
    if(retryAttachmentsBtn)retryAttachmentsBtn.addEventListener('click',()=>{if(!App.state.attachmentLoading&&App.state.currentUser)void App.initializeAttachments('','',App.state.attachmentGeneration);});
    App.initTextSize();
    document.getElementById('logoutBtn').addEventListener('click', App.logout);
    document.getElementById('newChatBtn').addEventListener('click', App.createNewChatPlaceholder);
    App.elements.messageForm.addEventListener('submit', App.handleSendMessage);
    if (App.elements.semanticModeToggle) {
      App.elements.semanticModeToggle.addEventListener('click', App.handleSemanticModeToggle);
    }
    if (App.elements.fastSummaryLink) {
      App.elements.fastSummaryLink.addEventListener('click', App.handleFastSummaryClick);
    }
    if (App.elements.semanticWarningOkBtn) {
      App.elements.semanticWarningOkBtn.addEventListener('click', App.confirmSemanticModeWarning);
    }
    if (App.elements.semanticWarningCancelBtn) {
      App.elements.semanticWarningCancelBtn.addEventListener('click', App.closeSemanticSearchWarningDialog);
    }
    if (App.elements.semanticWarningCloseBtn) {
      App.elements.semanticWarningCloseBtn.addEventListener('click', App.closeSemanticSearchWarningDialog);
    }
    if (App.elements.semanticSearchWarningDialog) {
      App.elements.semanticSearchWarningDialog.addEventListener('click', function (ev) {
        if (ev.target === App.elements.semanticSearchWarningDialog) {
          App.closeSemanticSearchWarningDialog();
        }
      });
    }
    document.getElementById('reloadCommentsBtn').addEventListener('click', App.loadComments);
    const reloadLessonsBtn = document.getElementById('reloadLessonsBtn');
    if (reloadLessonsBtn) reloadLessonsBtn.addEventListener('click', App.loadComments);
    const reloadKnowledgeBtn = document.getElementById('reloadKnowledgeBtn');
    if (reloadKnowledgeBtn) reloadKnowledgeBtn.addEventListener('click', App.loadKnowledge);
    document.getElementById('reloadPendingUsersBtn').addEventListener('click', App.loadPendingUsers);
    const reloadApprovedUsersBtn = document.getElementById('reloadApprovedUsersBtn');
    if (reloadApprovedUsersBtn) reloadApprovedUsersBtn.addEventListener('click', App.loadApprovedUsers);
    const reloadAdminsBtn = document.getElementById('reloadAdminsBtn');
    if (reloadAdminsBtn) reloadAdminsBtn.addEventListener('click', App.loadAdminLists);
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
    const importMembersCsvBtn = document.getElementById('importMembersCsvBtn');
    if (importMembersCsvBtn) importMembersCsvBtn.addEventListener('click', App.importMembersCsv);
    const downloadMembersCsvTemplateBtn = document.getElementById('downloadMembersCsvTemplateBtn');
    if (downloadMembersCsvTemplateBtn) {
      downloadMembersCsvTemplateBtn.addEventListener('click', App.downloadMembersCsvTemplate);
    }
    const reloadMembersBtn = document.getElementById('reloadMembersBtn');
    if (reloadMembersBtn) reloadMembersBtn.addEventListener('click', App.loadMembers);
    const importSrtBtn = document.getElementById('importSrtBtn');
    if (importSrtBtn) importSrtBtn.addEventListener('click', App.importSrtTranscript);
    const reloadAnalyticsBtn = document.getElementById('reloadAnalyticsBtn');
    if (reloadAnalyticsBtn) {
      reloadAnalyticsBtn.addEventListener('click', function () {
        App.loadAnalytics();
      });
    }
    const analyticsDaysSelect = document.getElementById('analyticsDaysSelect');
    if (analyticsDaysSelect) {
      analyticsDaysSelect.addEventListener('change', function () {
        App.loadAnalytics();
      });
    }
    document.getElementById('sidebarToggleBtn').addEventListener('click', App.toggleSidebarMobile);
    document.getElementById('commentSearchInput').addEventListener('input', App.renderCommentTable);
    if (App.elements.lessonSearchInput) {
      App.elements.lessonSearchInput.addEventListener('input', App.renderLessonTable);
    }
    if (App.elements.lessonCourseTabFilter) {
      App.elements.lessonCourseTabFilter.addEventListener('change', function () { App.changeReferenceFilter('lesson', 0); });
    }
    ['lesson', 'knowledge'].forEach(function (prefix) {
      ['CourseTab', 'Section', 'Title'].forEach(function (name, index) {
        const select = document.getElementById(prefix + name + 'Filter');
        if (select && !(prefix === 'lesson' && index === 0)) {
          select.addEventListener('change', function () { App.changeReferenceFilter(prefix, index); });
        }
      });
    });
    if (App.elements.knowledgeSearchInput) {
      App.elements.knowledgeSearchInput.addEventListener('input', App.renderKnowledgeTable);
    }
    if (App.elements.commentAttachmentsOnly) {
      App.elements.commentAttachmentsOnly.addEventListener('change', App.renderCommentTable);
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
    if (App.elements.commentDetailCloseBtn) {
      App.elements.commentDetailCloseBtn.addEventListener('click', App.closeCommentDetailDialog);
    }
    if (App.elements.commentDetailDialog) {
      App.elements.commentDetailDialog.addEventListener('click', function (ev) {
        if (ev.target === App.elements.commentDetailDialog) App.closeCommentDetailDialog();
      });
    }
    if (App.elements.allSearchForm) {
      App.elements.allSearchForm.addEventListener('submit', function (ev) {
        ev.preventDefault();
        void App.runAllSearch();
      });
    }
    if (App.elements.allSearchResults) {
      App.elements.allSearchResults.addEventListener('click', App.onAllSearchResultClick);
    }
    const allSearchBox = document.getElementById('allSearchBox');
    if (allSearchBox) {
      allSearchBox.addEventListener('click', function (ev) {
        const ex = ev.target && ev.target.closest ? ev.target.closest('.all-search-example') : null;
        if (!ex || !App.elements.allSearchInput) return;
        App.elements.allSearchInput.value = ex.getAttribute('data-q') || '';
        void App.runAllSearch();
      });
    }
    document.querySelectorAll('.screen-tab').forEach(function (btn) {
      btn.addEventListener('click', function () {
        App.switchScreen(btn.getAttribute('data-screen'), { fromNav: true });
      });
    });
    if (App.elements.commentsBackBtn) {
      App.elements.commentsBackBtn.addEventListener('click', App.goBackFromDbScreen);
    }
    if (App.elements.lessonsBackBtn) {
      App.elements.lessonsBackBtn.addEventListener('click', App.goBackFromDbScreen);
    }
    if (App.elements.knowledgeBackBtn) {
      App.elements.knowledgeBackBtn.addEventListener('click', App.goBackFromDbScreen);
    }
    if (App.elements.openchatBackBtn) {
      App.elements.openchatBackBtn.addEventListener('click', App.goBackFromDbScreen);
    }
    if (App.elements.reloadOpenchatBtn) {
      App.elements.reloadOpenchatBtn.addEventListener('click', function () {
        App.loadOpenchatLogs().catch(function (err) {
          App.showToast((err && err.message) || 'LINEオプチャの取得に失敗しました', 'error');
        });
      });
    }
    if (App.elements.openchatSearchInput) {
      App.elements.openchatSearchInput.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter') {
          ev.preventDefault();
          App.loadOpenchatLogs().catch(function (err) {
            App.showToast((err && err.message) || 'LINEオプチャの取得に失敗しました', 'error');
          });
        }
      });
    }
    if (App.elements.openchatTitleFilter) {
      App.elements.openchatTitleFilter.addEventListener('change', function () {
        App.loadOpenchatLogs().catch(function (err) {
          App.showToast((err && err.message) || 'LINEオプチャの取得に失敗しました', 'error');
        });
      });
    }
    if (App.elements.openchatAttachmentsOnly) App.elements.openchatAttachmentsOnly.addEventListener('change', function () {
      App.loadOpenchatLogs().catch(function(err){App.showToast(err.message || 'LINE添付の取得に失敗しました','error');});
    });
  },

  isLessonCommentRow: (row) => {
    if (!row || typeof row !== 'object') return false;
    const src = String(
      App.commentField
        ? App.commentField(row, 'source_system')
        : row.source_system || row.sourceSystem || ''
    ).trim();
    const cid = String(
      App.commentField
        ? App.commentField(row, 'comment_id')
        : row.comment_id || row.commentId || ''
    ).trim();
    return src === 'lesson' || cid.indexOf('lesson_desc_') === 0;
  },

  setLoading: (isLoading) => {
    if (isLoading) App.state.loadingCount += 1;
    if (!isLoading) App.state.loadingCount = Math.max(0, App.state.loadingCount - 1);
    if(App.state.loadingCount>0 && !(App.authGatewayBase&&App.state.pendingQuestionText))App.elements.loadingOverlay.classList.add('active');
    else App.elements.loadingOverlay.classList.remove('active');
    if (App.elements.fastSummaryLink) {
      if (App.state.loadingCount > 0 && App.state.pendingQuestionText) {
        App.elements.fastSummaryLink.classList.remove('hidden');
      } else {
        App.elements.fastSummaryLink.classList.add('hidden');
      }
    }
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
    const kind = type || 'info';
    App.elements.toast.textContent = message || '';
    App.elements.toast.className = 'toast ' + (kind === 'success_long' ? 'success' : kind);
    App.elements.toast.classList.remove('hidden');
    if (App._toastHideTimer) {
      window.clearTimeout(App._toastHideTimer);
      App._toastHideTimer = null;
    }
    // エラー／登録成功案内は長め、それ以外は従来どおり短め
    const ms = kind === 'error' || kind === 'success_long' ? 10000 : 2600;
    App._toastHideTimer = window.setTimeout(function () {
      App.elements.toast.classList.add('hidden');
      App._toastHideTimer = null;
    }, ms);
  },

  showRegisterSuccessNotice: (message) => {
    const el = document.getElementById('registerSuccessNotice');
    if (!el) return;
    el.textContent = message || '';
    el.classList.remove('hidden');
  },

  clearRegisterSuccessNotice: () => {
    const el = document.getElementById('registerSuccessNotice');
    if (!el) return;
    el.textContent = '';
    el.classList.add('hidden');
  },

  /* 改修: 認証画面表示時に管理者登録・再設定ビューを隠す */
  showAuthView: () => {
    App.elements.authView.classList.remove('hidden');
    App.elements.mainView.classList.add('hidden');
    if (App.elements.forgotPasswordView) {
      App.elements.forgotPasswordView.classList.add('hidden');
    }
    if (App.elements.resetPasswordView) {
      App.elements.resetPasswordView.classList.add('hidden');
    }
    if (App.elements.masterTransferView) {
      App.elements.masterTransferView.classList.add('hidden');
    }
  },

  showMainView: () => {
    App.elements.authView.classList.add('hidden');
    App.elements.mainView.classList.remove('hidden');
    if (App.elements.forgotPasswordView) {
      App.elements.forgotPasswordView.classList.add('hidden');
    }
    if (App.elements.resetPasswordView) {
      App.elements.resetPasswordView.classList.add('hidden');
    }
    if (App.elements.masterTransferView) {
      App.elements.masterTransferView.classList.add('hidden');
    }
  },


  showForgotPasswordView: () => {
    App.state.resetPasswordEmail = '';
    App.state.resetPasswordToken = '';
    App.elements.authView.classList.add('hidden');
    App.elements.mainView.classList.add('hidden');
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

  parseMasterTransferTokenFromHash: () => {
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
    if (path !== 'master-transfer') return '';
    const params = new URLSearchParams(query);
    return (params.get('token') || '').trim();
  },

  clearMasterTransferHash: () => {
    if (!App.parseMasterTransferTokenFromHash()) return;
    const url = window.location.pathname + window.location.search;
    window.history.replaceState(null, '', url);
  },

  buildMasterTransferUrl: (token) => {
    const base = (window.location.origin + window.location.pathname).replace(/\/+$/, '') + '/';
    return base + '#master-transfer?token=' + encodeURIComponent(token);
  },

  persistMasterTransferToken: (token) => {
    try {
      if (token) sessionStorage.setItem('master_xfer_token', token);
      else sessionStorage.removeItem('master_xfer_token');
    } catch (e) {
      /* ignore */
    }
  },

  showMasterTransferView: () => {
    if (App.elements.authView) App.elements.authView.classList.add('hidden');
    if (App.elements.mainView) App.elements.mainView.classList.add('hidden');
    if (App.elements.forgotPasswordView) App.elements.forgotPasswordView.classList.add('hidden');
    if (App.elements.resetPasswordView) App.elements.resetPasswordView.classList.add('hidden');
    if (App.elements.masterTransferView) App.elements.masterTransferView.classList.remove('hidden');
  },

  openMasterTransferFromToken: async (token) => {
    App.state.masterTransferToken = String(token || '').trim();
    App.persistMasterTransferToken(App.state.masterTransferToken);
    App.setLoading(true);
    try {
      const res = await App.apiClient('POST', '/admin/master-transfer/validate', {
        token: App.state.masterTransferToken
      });
      const expiresAt = (res && res.expires_at) || '';
      if (expiresAt && Date.parse(expiresAt) <= Date.now()) {
        throw new Error('移譲リンクの有効期限が切れています。現マスターに再依頼してください');
      }
      App.state.masterTransferInfo = res || null;
      App.showMasterTransferView();
      const fromEl = document.getElementById('masterTransferFromEmail');
      const toEl = document.getElementById('masterTransferToEmail');
      const expEl = document.getElementById('masterTransferExpires');
      if (fromEl) fromEl.textContent = (res && res.from_email) || '—';
      if (toEl) toEl.textContent = (res && (res.to_email || res.to_user_email)) || '—';
      if (expEl) expEl.textContent = expiresAt || '—';
      const hint = document.getElementById('masterTransferLoginHint');
      const btn = App.elements.masterTransferAcceptBtn;
      const user = App.state.currentUser;
      const toId = String((res && res.to_user_id) || '');
      const isNominee = !!(user && String(user.id) === toId);
      if (hint) hint.classList.toggle('hidden', isNominee);
      if (btn) {
        btn.disabled = !isNominee;
        btn.textContent = isNominee
          ? 'マスター管理者として承認する'
          : '指名アカウントでログインが必要です';
      }
    } catch (error) {
      App.persistMasterTransferToken('');
      App.state.masterTransferToken = '';
      App.state.masterTransferInfo = null;
      App.clearMasterTransferHash();
      App.showAuthView();
      App.showToast((error && error.message) || '移譲リンクが無効です', 'error');
    } finally {
      App.setLoading(false);
    }
  },

  startMasterTransfer: async (userId, email) => {
    if (!App.isMasterAdmin()) {
      App.showToast('マスター管理者のみ移譲できます', 'error');
      return;
    }
    if (String(userId) === String(App.state.currentUser.id)) {
      App.showToast('自分自身への移譲はできません', 'error');
      return;
    }
    const ok = await App.openConfirmDialog(
      'マスターを移譲する',
      (email || 'この管理者') +
        ' にマスター管理者の移譲依頼メールを送ります。相手が承認するまで、あなたがマスターのままです。よろしいですか？'
    );
    if (!ok) return;
    App.setLoading(true);
    try {
      const token =
        window.crypto && typeof window.crypto.randomUUID === 'function'
          ? window.crypto.randomUUID()
          : 'mx-' + Date.now() + '-' + Math.random().toString(36).slice(2, 12);
      const expiry = App.buildPasswordResetExpiry();
      await App.apiClient('POST', '/admin/master-transfer/cancel', {
        actor_user_id: String(App.state.currentUser.id)
      }).catch(function () { /* 未作成でも続行 */ });
      await App.apiClient('POST', '/admin/master-transfer/start', {
        actor_user_id: String(App.state.currentUser.id),
        target_user_id: String(userId),
        target_email: email || '',
        from_email: App.state.currentUser.email || '',
        token: token,
        expires_at: expiry.commentsAt,
        comment_id: 'admin_master_xfer_pending'
      });
      const approvalUrl = App.buildMasterTransferUrl(token);
      try {
        await App.apiClient('POST', '/notify/master-transfer', {
          email: email,
          approval_url: approvalUrl,
          from_email: App.state.currentUser.email || '',
          expires_at: expiry.display
        });
      } catch (notifyErr) {
        console.warn('master-transfer notify failed', notifyErr);
        App.showToast(
          '移譲依頼は作成しましたが、メール送信に失敗しました。URLを手動共有してください: ' + approvalUrl,
          'error'
        );
        await App.loadAdminLists();
        return;
      }
      App.showToast('マスター移譲の承認依頼メールを送信しました', 'success');
      await App.loadAdminLists();
    } catch (error) {
      App.showToast((error && error.message) || '移譲の開始に失敗しました', 'error');
    } finally {
      App.setLoading(false);
    }
  },

  acceptMasterTransfer: async () => {
    const info = App.state.masterTransferInfo;
    const token = App.state.masterTransferToken;
    if (!info || !token || !App.state.currentUser) {
      App.showToast('移譲情報が不足しています。リンクから開き直してください', 'error');
      return;
    }
    if (String(App.state.currentUser.id) !== String(info.to_user_id)) {
      App.showToast('指名された管理者アカウントでログインしてください', 'error');
      return;
    }
    const ok = await App.openConfirmDialog(
      'マスター管理者の承認',
      '承認すると、あなたが新しいマスター管理者になり、現マスターは一般の管理者になります。よろしいですか？'
    );
    if (!ok) return;
    App.setLoading(true);
    try {
      await App.apiClient('POST', '/admin/master-transfer/accept', {
        actor_user_id: String(App.state.currentUser.id),
        from_user_id: String(info.from_user_id),
        token: token
      });
      App.state.currentUser.role = 'master_admin';
      App.persistMasterTransferToken('');
      App.state.masterTransferToken = '';
      App.state.masterTransferInfo = null;
      App.clearMasterTransferHash();
      App.showToast('マスター管理者への移譲が完了しました', 'success');
      App.afterLogin();
    } catch (error) {
      App.showToast((error && error.message) || '承認に失敗しました', 'error');
    } finally {
      App.setLoading(false);
    }
  },

  cancelMasterTransfer: async () => {
    if (!App.isMasterAdmin()) return;
    const ok = await App.openConfirmDialog('移譲をキャンセル', '進行中のマスター移譲依頼を取り消します。よろしいですか？');
    if (!ok) return;
    try {
      await App.apiClient('POST', '/admin/master-transfer/cancel', {
        actor_user_id: String(App.state.currentUser.id)
      });
      App.showToast('マスター移譲をキャンセルしました', 'info');
      await App.loadAdminLists();
    } catch (error) {
      App.showToast((error && error.message) || 'キャンセルに失敗しました', 'error');
    }
  },

  loadPendingMasterTransfer: async () => {
    const note = document.getElementById('masterTransferPendingNote');
    const cancelBtn = document.getElementById('cancelMasterTransferBtn');
    if (!App.isMasterAdmin()) {
      if (note) note.classList.add('hidden');
      if (cancelBtn) cancelBtn.classList.add('hidden');
      App.state.pendingMasterTransfer = null;
      return;
    }
    try {
      const res = await App.apiClient('GET', '/admin/master-transfer/pending');
      const req = res && res.request ? res.request : null;
      App.state.pendingMasterTransfer = req;
      if (req && note) {
        note.textContent =
          'マスター移譲の承認待ち: ' +
          (req.author_email || req.parent_comment_id || '') +
          '（有効期限: ' +
          (req.posted_at || '—') +
          '）';
        note.classList.remove('hidden');
      } else if (note) {
        note.classList.add('hidden');
      }
      if (cancelBtn) cancelBtn.classList.toggle('hidden', !req);
    } catch (e) {
      App.state.pendingMasterTransfer = null;
      if (note) note.classList.add('hidden');
      if (cancelBtn) cancelBtn.classList.add('hidden');
    }
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
   * iso … users.reset_expires_at 用（Z可）
   * commentsAt … comments.posted_at 用（Z不可。+09:00）
   * display … メール表記用
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
    const mm = m < 10 ? '0' + m : String(m);
    const dd = d < 10 ? '0' + d : String(d);
    return {
      iso: expires.toISOString(),
      commentsAt: y + '-' + mm + '-' + dd + 'T23:59:59+09:00',
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

  showLoginTab: () => {
    document.getElementById('showLoginTabBtn').className = 'w-1/2 py-2 rounded-md bg-blue-900 text-white';
    document.getElementById('showRegisterTabBtn').className = 'w-1/2 py-2 rounded-md bg-slate-200 text-slate-700';
    App.elements.loginForm.classList.remove('hidden');
    App.elements.registerForm.classList.add('hidden');
  },

  showRegisterTab: () => {
    App.clearRegisterSuccessNotice();
    document.getElementById('showRegisterTabBtn').className = 'w-1/2 py-2 rounded-md bg-blue-900 text-white';
    document.getElementById('showLoginTabBtn').className = 'w-1/2 py-2 rounded-md bg-slate-200 text-slate-700';
    App.elements.registerForm.classList.remove('hidden');
    App.elements.loginForm.classList.add('hidden');
  },

  handleRegister: async (event) => {
    event.preventDefault();
    const name = (document.getElementById('registerName').value || '').trim();
    const email = document.getElementById('registerEmail').value.trim().toLowerCase();
    const memberNo = (document.getElementById('registerMemberNo').value || '').trim();
    const prefecture = (document.getElementById('registerPrefecture').value || '').trim();
    const password = document.getElementById('registerPassword').value;
    if (!memberNo) {
      App.showToast('会員番号は必須です', 'error');
      return;
    }
    if (!name) {
      App.showToast('氏名は必須です', 'error');
      return;
    }
    if (!prefecture) {
      App.showToast('在住都道府県を選択してください', 'error');
      return;
    }
    if (!email || !password) {
      App.showToast('メールアドレスとパスワードは必須です', 'error');
      return;
    }

    App.setButtonLoading(App.elements.registerSubmitBtn, true, '登録中');
    App.setLoading(true);
    try {
      const payload = {
        email: email,
        password_hash: password,
        member_no: memberNo,
        name: name,
        prefecture: prefecture
      };
      const isNotOnRoster = function (err) {
        const code = err && err.errorCode;
        const msg = String((err && err.message) || '');
        return (
          code === 'not_on_roster' ||
          msg.indexOf('名簿に一致') !== -1 ||
          msg.indexOf('not_on_roster') !== -1
        );
      };
      const isReregisterCandidate = function (err) {
        const code = err && err.errorCode;
        const msg = String((err && err.message) || '');
        return (
          code === 'email_taken' ||
          msg.indexOf('既に登録') !== -1 ||
          msg.indexOf('退会') !== -1 ||
          msg.indexOf('処理中にエラー') !== -1
        );
      };

      let autoApproved = false;
      let registered = false;

      try {
        await App.apiClient('POST', '/auth/register-roster', payload);
        autoApproved = true;
        registered = true;
      } catch (rosterErr) {
        if (isNotOnRoster(rosterErr)) {
          // (3) 名簿（目標設定・合格状況）と番号＋氏名が合えば、サーバーがその場で承認する（auto_approved）
          try {
            const reg = await App.apiClient('POST', '/auth/register', payload);
            registered = true;
            if (reg && String(reg.auto_approved) === 'true') autoApproved = true;
          } catch (regErr) {
            if (isReregisterCandidate(regErr)) {
              const rereg = await App.apiClient('POST', '/auth/reregister', payload);
              registered = true;
              if (rereg && String(rereg.auto_approved) === 'true') autoApproved = true;
            } else {
              throw regErr;
            }
          }
          if (registered && !autoApproved) {
            await App.notifyRegistrationPending(email, '新規登録（アプリ）', memberNo, name, prefecture);
          }
        } else if (isReregisterCandidate(rosterErr)) {
          try {
            await App.apiClient('POST', '/auth/reregister-roster', payload);
            autoApproved = true;
            registered = true;
          } catch (rrErr) {
            if (isNotOnRoster(rrErr)) {
              const rereg = await App.apiClient('POST', '/auth/reregister', payload);
              registered = true;
              if (rereg && String(rereg.auto_approved) === 'true') autoApproved = true;
              else await App.notifyRegistrationPending(email, '再登録（アプリ）', memberNo, name, prefecture);
            } else {
              throw rrErr;
            }
          }
        } else {
          throw rosterErr;
        }
      }

      const notice = autoApproved
        ? '新規登録が完了しました。ログイン画面からメールアドレスとパスワードでログインしてください。'
        : '管理者にメールを送信しました。管理者承認後にメールが届くので、しばらくお待ちください';
      App.showToast(notice, 'success_long');
      App.showLoginTab();
      App.showRegisterSuccessNotice(notice);
      App.elements.registerForm.reset();
    } catch (error) {
      App.showToast(error.message || '登録に失敗しました', 'error');
    } finally {
      App.setButtonLoading(App.elements.registerSubmitBtn, false);
      App.setLoading(false);
    }
  },

  /** Phase 2: 承認依頼メール。失敗しても throw しない。 */
  notifyRegistrationPending: async (email, note, memberNo, name, prefecture) => {
    try {
      const registeredAt =
        new Date().toLocaleString('ja-JP', { timeZone: 'Asia/Tokyo' }) + ' JST';
      let noteWithName = name
        ? (note || '') + (note ? ' / ' : '') + '氏名: ' + name
        : note || '';
      if (prefecture) {
        noteWithName += (noteWithName ? ' / ' : '') + '都道府県: ' + prefecture;
      }
      await App.apiClient('POST', '/notify/registration', {
        email: email,
        member_no: memberNo || '',
        registered_at: registeredAt,
        note: noteWithName
      });
    } catch (notifyErr) {
      console.warn('registration notify failed (registration still OK):', notifyErr);
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
      App.state.authToken = App.authGatewayBase ? String(res.auth_token || '') : '';
      App.state.currentUser = res.user;
      document.getElementById('loginPassword').value = '';
      App.state.attachmentGeneration += 1;
      App.state.attachmentToken = '';
      App.state.attachmentIndex = {};
      Promise.resolve(App.afterLogin()).then(()=>App.resumePendingAnswer()).catch(()=>{});
      void App.initializeAttachments(email, password, App.state.attachmentGeneration);
      void App.loadReferenceMetadata(App.state.attachmentGeneration);
      App.showToast('ログインしました', 'success');
    } catch (error) {
      App.showToast(error.message || 'ログインに失敗しました', 'error');
    } finally {
      App.setButtonLoading(App.elements.loginSubmitBtn, false);
      App.setLoading(false);
    }
  },

  afterLogin: async () => {
    const pendingXfer = App.state.masterTransferToken || (function () {
      try {
        return sessionStorage.getItem('master_xfer_token') || '';
      } catch (e) {
        return '';
      }
    })();
    if (pendingXfer) {
      await App.openMasterTransferFromToken(pendingXfer);
      return;
    }
    App.showMainView();
    await App.loadFeatures();
    App.applyTheme();
    App.renderFeaturePreviewBar();
    App.applySearchModeUi();
    App.elements.currentUserLabel.textContent = App.state.currentUser.email + ' (' + (App.isStaffAdmin() || !App.state.viewAsMember ? App.state.currentUser.role : 'user として表示中') + ')';

    const changeLogTab = document.getElementById('changeLogTabBtn');
    if (changeLogTab) changeLogTab.classList.toggle('hidden', !App.featureOn('change_log'));
    const allSearchTab = document.getElementById('allSearchTabBtn');
    if (allSearchTab) allSearchTab.classList.toggle('hidden', !App.featureOn('keyword_all'));
    if (!App.featureOn('keyword_all') && App.state.currentScreen === 'allSearch') App.switchScreen('chat');
    const isAdmin = App.isStaffAdmin();
    const adminNav = document.getElementById('adminNavSection');
    if (adminNav) adminNav.classList.toggle('hidden', !isAdmin);
    document.getElementById('adminUsersTabBtn').classList.toggle('hidden', !isAdmin);
    const userListTab = document.getElementById('adminUserListTabBtn');
    if (userListTab) userListTab.classList.toggle('hidden', !isAdmin);
    const adminListTab = document.getElementById('adminAdminListTabBtn');
    if (adminListTab) adminListTab.classList.toggle('hidden', !isAdmin);
    document.getElementById('adminDataTabBtn').classList.toggle('hidden', !isAdmin);
    const membersTab = document.getElementById('adminMembersTabBtn');
    if (membersTab) membersTab.classList.toggle('hidden', !isAdmin);
    const analyticsTab = document.getElementById('adminAnalyticsTabBtn');
    if (analyticsTab) analyticsTab.classList.toggle('hidden', !isAdmin);

    App.switchScreen('chat');
    await App.refreshInitialData();
  },

  refreshInitialData: async () => {
    App.setLoading(true);
    try {
      await Promise.all([
        App.loadChatSessions(),
        App.loadSuggestedQuestions()
      ]);
      if (App.isStaffAdmin()) {
        await App.loadPendingUsers();
        await App.loadApprovedUsers();
        await App.loadRoleRequests();
      }
      App.renderAll();
    } catch (error) {
      App.showToast(error.message || '初期データ取得に失敗しました', 'error');
    } finally {
      App.setLoading(false);
    }
  },

  logout: () => {
    if (App.authGatewayBase && App.state.authToken) void App.apiClient('POST', '/auth/logout', {}).catch(() => {});
    App.state.authToken = '';
    if(App.state.sendAbortController)App.state.sendAbortController.abort();
    App.state.pendingAnswerRequest=null;App.state.answerJobStatus='';App.renderAnswerJobStatus();
    App.state.attachmentGeneration += 1;
    App.state.attachmentToken = '';
    App.state.attachmentIndex = {};
    App.state.referenceComments={};App.state.attachmentStatus='';App.state.attachmentLoading=false;App.renderAttachmentStatus();
    App.state.attachmentDetailCommentId = '';
    App.state.features = {};
    App.state.feedbackByMessage = {};
    // ログアウト後のログイン画面は、この端末で配色が見えていた人だけ案Aのまま（applyTheme で覚えた分）
    let keepTheme = false;
    try { keepTheme = localStorage.getItem('qa_design_theme') === '1'; } catch (e) { /* ignore */ }
    if (document.documentElement) document.documentElement.classList.toggle('theme-a', keepTheme);
    const featureBar = document.getElementById('featurePreviewBar');
    if (featureBar) featureBar.classList.add('hidden');
    App.state.currentUser = null;
    App.state.currentSessionId = null;
    App.state.chatSessions = [];
    App.state.chatMessages = [];
    App.state.suggestedQuestions = [];
    App.state.comments = [];App.state.referenceReady={};App.state.referenceLoads={};
    App.state.pendingUsers = [];
    App.state.rosterMatches = {};
    App.state.approvedUsers = [];
    App.state.roleRequestUsers = [];
    App.state.members = [];
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
      lessons: 'lessonsScreen',
      knowledge: 'knowledgeScreen',
      openchat: 'openchatScreen',
      adminUsers: 'adminUsersScreen',
      adminUserList: 'adminUserListScreen',
      adminAdminList: 'adminAdminListScreen',
      adminMembers: 'adminMembersScreen',
      adminData: 'adminDataScreen',
      adminAnalytics: 'adminAnalyticsScreen',
      changeLog: 'changeLogScreen',
      allSearch: 'allSearchScreen'
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
    if(['comments','lessons','knowledge'].includes(screenName))void App.ensureReferenceData(screenName);
    App.elements.sidebar.classList.remove('mobile-open');
    // サイドバー手動遷移・戻る完了時は citation 用戻るバーを隠す
    if (opts.fromNav || opts.fromBack) {
      App.clearDbReturnBar();
    }
    if (screenName === 'adminUserList') {
      App.loadApprovedUsers().catch(function (err) {
        App.showToast((err && err.message) || 'ユーザ一覧の取得に失敗しました', 'error');
      });
    }
    if (screenName === 'adminAdminList') {
      App.loadAdminLists().catch(function (err) {
        App.showToast((err && err.message) || '管理者一覧の取得に失敗しました', 'error');
      });
    }
    if (screenName === 'adminMembers') {
      App.loadMembers().catch(function (err) {
        App.showToast((err && err.message) || '会員名簿の取得に失敗しました', 'error');
      });
    }
    if (screenName === 'changeLog') void App.loadChangeLog();
    if (screenName === 'allSearch' && App.elements.allSearchInput) setTimeout(function () { App.elements.allSearchInput.focus(); }, 0);
    // キーワード検索（全データ）を開いたら、言葉を入れている間に一覧データを先に読み込んでおく（初回の待ち時間を減らす）
    if (screenName === 'allSearch' && App.featureOn('keyword_all')) { void App.ensureReferenceData('comments'); void App.ensureReferenceData('knowledge'); }
    if (screenName === 'adminAnalytics') {
      App.loadAnalytics().catch(function (err) {
        App.showToast((err && err.message) || '分析データの取得に失敗しました', 'error');
      });
    }
    if (screenName === 'openchat') {
      App.loadOpenchatLogs().catch(function (err) {
        App.showToast((err && err.message) || 'LINEオプチャの取得に失敗しました', 'error');
      });
    }
  },

  screenLabel: (screenName) => {
    const labels = {
      chat: 'Q&Aチャット',
      comments: 'westudy コミュニティコメント',
      lessons: 'westudy 講座ページ説明文',
      knowledge: 'westudy 動画文字起こし',
      openchat: 'LINEオプチャ',
      allSearch: 'キーワード検索（全データ）',
      adminUsers: 'ユーザ承認',
      adminUserList: 'ユーザ一覧',
      adminAdminList: '管理者一覧',
      adminMembers: '会員名簿',
      adminData: 'データ取込',
      adminAnalytics: '運営分析'
    };
    return labels[screenName] || '前の画面';
  },

  clearDbReturnBar: () => {
    App.state.returnScreen = null;
    if (App.elements.commentsBackBar) {
      App.elements.commentsBackBar.classList.add('hidden');
    }
    if (App.elements.lessonsBackBar) {
      App.elements.lessonsBackBar.classList.add('hidden');
    }
    if (App.elements.knowledgeBackBar) {
      App.elements.knowledgeBackBar.classList.add('hidden');
    }
    if (App.elements.openchatBackBar) {
      App.elements.openchatBackBar.classList.add('hidden');
    }
  },

  showDbReturnBar: (targetScreen) => {
    const returnTo = App.state.returnScreen || 'chat';
    const label = App.screenLabel(returnTo) + 'に戻る';
    const hideAll = function () {
      if (App.elements.commentsBackBar) App.elements.commentsBackBar.classList.add('hidden');
      if (App.elements.lessonsBackBar) App.elements.lessonsBackBar.classList.add('hidden');
      if (App.elements.knowledgeBackBar) App.elements.knowledgeBackBar.classList.add('hidden');
      if (App.elements.openchatBackBar) App.elements.openchatBackBar.classList.add('hidden');
    };
    hideAll();
    if (targetScreen === 'comments' && App.elements.commentsBackBar) {
      if (App.elements.commentsBackLabel) {
        App.elements.commentsBackLabel.textContent = label;
      }
      App.elements.commentsBackBar.classList.remove('hidden');
    } else if (targetScreen === 'lessons' && App.elements.lessonsBackBar) {
      if (App.elements.lessonsBackLabel) {
        App.elements.lessonsBackLabel.textContent = label;
      }
      App.elements.lessonsBackBar.classList.remove('hidden');
    } else if (targetScreen === 'knowledge' && App.elements.knowledgeBackBar) {
      if (App.elements.knowledgeBackLabel) {
        App.elements.knowledgeBackLabel.textContent = label;
      }
      App.elements.knowledgeBackBar.classList.remove('hidden');
    } else if (targetScreen === 'openchat' && App.elements.openchatBackBar) {
      if (App.elements.openchatBackLabel) {
        App.elements.openchatBackLabel.textContent = label;
      }
      App.elements.openchatBackBar.classList.remove('hidden');
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
    App.state.chatSessions = App.sortSessionsForDisplay((res && res.sessions) ? res.sessions : []);
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

  sessionOrderStorageKey: 'qa_session_order_v1',

  loadSessionOrder: () => {
    try {
      const raw = localStorage.getItem(App.sessionOrderStorageKey);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed.map(String) : [];
    } catch (e) {
      return [];
    }
  },

  bumpSessionToTop: async (sessionId) => {
    const id = String(sessionId || '').trim();
    if (!id) return;
    const order = App.loadSessionOrder().filter(function (x) {
      return x !== id;
    });
    order.unshift(id);
    try {
      localStorage.setItem(App.sessionOrderStorageKey, JSON.stringify(order.slice(0, 200)));
    } catch (e) {
      /* ignore */
    }
    try {
      await App.apiClient('PUT', '/chat-sessions/' + id + '/touch', {});
    } catch (e) {
      console.warn('session touch skipped', e);
    }
    App.state.chatSessions = App.sortSessionsForDisplay(App.state.chatSessions || []);
    App.renderSessionList();
  },

  sortSessionsForDisplay: (sessions) => {
    const list = Array.isArray(sessions) ? sessions.slice() : [];
    const order = App.loadSessionOrder();
    const rank = {};
    order.forEach(function (sid, i) {
      rank[sid] = i;
    });
    list.sort(function (a, b) {
      const aid = String((a && a.id) || '');
      const bid = String((b && b.id) || '');
      const ra = Object.prototype.hasOwnProperty.call(rank, aid) ? rank[aid] : null;
      const rb = Object.prototype.hasOwnProperty.call(rank, bid) ? rank[bid] : null;
      if (ra != null && rb != null) return ra - rb;
      if (ra != null) return -1;
      if (rb != null) return 1;
      const aUp = String((a && (a.updated_at || a.created_at)) || '');
      const bUp = String((b && (b.updated_at || b.created_at)) || '');
      return bUp.localeCompare(aUp);
    });
    return list;
  },

  hydrateHistoricalReferences: async (sessionId, loadGeneration) => {
    if(!App.authGatewayBase)return;
    const assistants=(App.state.chatMessages||[]).filter(m=>m.role==='assistant'&&m.id!=null);
    if(!assistants.some(m=>{const refs=(App.state.citationsByMessageId||{})[String(m.id)]||[];return !refs.length||refs.some(c=>!c.citationLabel);}))return;
    const uid=String((App.state.currentUser||{}).id||'');
    const current=()=>String((App.state.currentUser||{}).id||'')===uid&&App.state.messageLoadGeneration===loadGeneration&&String(App.state.currentSessionId)===String(sessionId);
    try{
      const data=await App.apiClient('GET','/chat-sessions/'+sessionId+'/reference-events');if(!current())return;
      const messages=App.state.chatMessages||[];
      (data.sources||[]).forEach(row=>{if(row.source_key)App.state.knowledgeSources[row.source_key]=row;});
      let changed=false;
      messages.forEach((message,index)=>{
        if(message.role!=='assistant'||message.id==null)return;
        const old=(App.state.citationsByMessageId||{})[String(message.id)]||[];
        if(old.length&&old.every(c=>c.citationLabel))return;
        const user=messages.slice(0,index).reverse().find(m=>m.role==='user');if(!user)return;
        const posted=App.referenceDateParts(message.created_at);if(!posted)return;
        const completed=(data.jobs||[]).filter(job=>{const date=App.referenceDateParts(job.finished_at);return date&&Math.abs(date.ms-posted.ms)<10000&&String(job.query||'').trim()===String(user.content||'').trim();});
        if(completed.length===1&&completed[0].result){
          const r=completed[0].result,used=App.parseUsedSources(r.usedSources||'');
          const refs=App.buildCitationsFromRelated([].concat(r.relatedComments||[],r.relatedLessonComments||[]),r.relatedChunks||[],r.relatedSources||[],used.ok?{commentIds:used.commentIds,chunkKeys:used.chunkKeys,openchatIds:used.openchatIds,strict:true}:null,r.relatedOpenchat||[],r.referenceSelection);
          if(refs.length){App.saveCitationsForMessage(sessionId,String(message.id),refs);changed=true;return;}
        }
        const candidates=(data.events||[]).filter(event=>{
          const date=App.referenceDateParts(event.created_at);
          return date&&Math.abs(date.ms-posted.ms)<10000&&String(event.query_text||'').trim()===String(user.content||'').trim();
        });
        // Ambiguous or missing history never gets a guessed number assignment.
        if(candidates.length!==1)return;
        let used=candidates[0].used_sources;try{if(typeof used==='string')used=JSON.parse(used);}catch(error){return;}
        if(!used||!Array.isArray(used.chunk_keys)||!Array.isArray(used.comment_ids))return;
        const labels={};
        (used.comment_ids||[]).forEach((key,i)=>{labels['comment:'+key]='コミュニティ'+(i+1);labels['lesson:'+key]='コミュニティ'+(i+1);});
        (used.chunk_keys||[]).forEach((key,i)=>{labels['video_chunk:'+key]='セミナー'+(i+1);});
        (used.openchat_ids||[]).forEach((key,i)=>{labels['openchat:'+key]='LINEオプチャ'+(i+1);});
        const next=old.map(c=>Object.assign({},c,{citationLabel:labels[c.kind+':'+String(c.commentId||c.chunkKey||c.openchatId)]||c.citationLabel||''}));
        for(const key of used.chunk_keys){
          if(next.some(c=>c.chunkKey===key))continue;
          const chunk=(data.chunks||[]).find(row=>row.chunk_key===key);if(!chunk)continue;
          const extra=App.buildCitationsFromRelated([], [Object.assign({},chunk,{citation_label:labels['video_chunk:'+key]})],data.sources||[],null,[]);
          next.push(...extra);
        }
        if(next.length){App.saveCitationsForMessage(sessionId,String(message.id),next);App.state.citationsByMessageId[String(message.id)]=next;changed=true;}
      });
      if(changed&&current())App.renderChatMessages();
    }catch(error){}
  },

  loadSessionDetails: async (sessionId) => {
    if (!sessionId) {
      App.showToast('セッションIDが未選択です', 'error');
      return;
    }
    const owner=String((App.state.currentUser||{}).id||'');const generation=(App.state.messageLoadGeneration||0)+1;App.state.messageLoadGeneration=generation;
    const res = await App.apiClient('GET', '/chat-sessions/' + sessionId);
    if(generation!==App.state.messageLoadGeneration||owner!==String((App.state.currentUser||{}).id||''))return;
    App.state.chatMessages = (res && res.messages) ? res.messages : [];
    App.restoreCitationsForSession(sessionId);
    App.renderChatMessages();
    App.state.currentSessionId = sessionId;
    App.renderSessionList();
    void App.hydrateHistoricalReferences(sessionId,generation);
  },

  loadSuggestedQuestions: async () => {
    const res = await App.apiClient('GET', '/suggested-questions');
    App.state.suggestedQuestions = (res && res.questions) ? res.questions : [];
    App.renderSuggestedQuestions();
  },

  looksLikeOpenchatId: (value) => {
    return /^oc_[0-9a-f]{16,64}$/i.test(String(value || '').trim());
  },

  loadOpenchatLogs: async (opts) => {
    const options = opts && typeof opts === 'object' ? opts : {};
    const generation=App.state.attachmentGeneration,userId=String((App.state.currentUser||{}).id||'');
    const sequence=(App.state.openchatRequestSequence||0)+1;
    App.state.openchatRequestSequence=sequence;
    const current=()=>generation===App.state.attachmentGeneration&&userId===String((App.state.currentUser||{}).id||'')&&sequence===App.state.openchatRequestSequence;
    const cfg = await App.resolveSemanticConfig();
    if(!current())return;
    const q = (App.elements.openchatSearchInput && App.elements.openchatSearchInput.value) || '';
    const title =
      (App.elements.openchatTitleFilter && App.elements.openchatTitleFilter.value) || '';
    const openchatId = String(
      options.openchatId ||
        (App.looksLikeOpenchatId(q) ? String(q).trim() : '') ||
        ''
    ).trim();
    const body = {
      list_openchat: true,
      only_attachments: !openchatId && !!(App.elements.openchatAttachmentsOnly && App.elements.openchatAttachmentsOnly.checked),
      query: openchatId ? openchatId : String(q || '').trim(),
      chat_title: openchatId ? undefined : String(title || '').trim() || undefined,
      openchat_limit: 40,
      session_id: App.state.currentSessionId || undefined,
      user_id: (App.state.currentUser && App.state.currentUser.id) || undefined
    };
    if (openchatId) {
      body.openchat_id = openchatId;
    }
    const response = await fetch(cfg.url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Semantic-Shared-Secret': cfg.secret
      },
      body: JSON.stringify(body)
    });
    const text = await response.text();
    if(!current())return;
    let data = {};
    if (text) {
      try {
        data = JSON.parse(text);
      } catch (e) {
        data = { _rawBody: text };
      }
    }
    if (!response.ok) {
      throw new Error(
        data.errorMessage || data.message || data.error || 'LINEオプチャ一覧の取得に失敗しました'
      );
    }
    if(!current())return;
    App.state.openchatLogs = App.normalizeRelatedList(data.relatedOpenchat || []);
    if (Array.isArray(data.openchatRooms)) App.state.openchatRooms = data.openchatRooms;
    App.state.openchatHighlightId = openchatId || '';
    App.renderOpenchatTitleFilterOptions();
    App.renderOpenchatTable({ exactOpenchatId: openchatId || undefined });
  },

  renderOpenchatTitleFilterOptions: () => {
    const select = App.elements.openchatTitleFilter;
    if (!select) return;
    const current = select.value || '';
    const titles = Array.from(
      new Set(
        (App.state.openchatRooms.length ? App.state.openchatRooms : App.state.openchatLogs || [])
          .map(function (row) {
            return String(row.chat_title || row.chatTitle || '').trim();
          })
          .filter(Boolean)
      )
    ).sort(function (a, b) {
      return a.localeCompare(b, 'ja');
    });
    select.innerHTML = '<option value="">全オプチャ</option>';
    titles.forEach(function (t) {
      const opt = document.createElement('option');
      opt.value = t;
      opt.textContent = t;
      select.appendChild(opt);
    });
    if (current) select.value = current;
  },

  renderOpenchatTable: (opts) => {
    const options = opts && typeof opts === 'object' ? opts : {};
    const tbody = App.elements.openchatTableBody;
    if (!tbody) return;
    const exactId = String(
      options.exactOpenchatId || App.state.openchatHighlightId || ''
    ).trim();
    const q = String(
      (App.elements.openchatSearchInput && App.elements.openchatSearchInput.value) || ''
    )
      .trim()
      .toLowerCase();
    const titleFilter = String(
      (App.elements.openchatTitleFilter && App.elements.openchatTitleFilter.value) || ''
    ).trim();
    let rows = App.state.openchatLogs || [];
    if (exactId) {
      const hit = rows.filter(function (r) {
        return String(r.id || '').trim() === exactId;
      });
      if (hit.length) {
        rows = hit;
      }
    } else {
      if (titleFilter) {
        rows = rows.filter(function (r) {
          return String(r.chat_title || r.chatTitle || '').trim() === titleFilter;
        });
      }
      if (q) {
        rows = rows.filter(function (r) {
          const blob = [
            r.id,
            r.chat_title,
            r.chat_name,
            r.stream_type,
            r.thread_title,
            r.sender_name,
            r.content,
            r.posted_at,
            r.post_date
          ]
            .map(function (x) {
              return String(x || '').toLowerCase();
            })
            .join(' ');
          return blob.indexOf(q) !== -1;
        });
      }
    }
    if (App.elements.openchatListMeta) {
      App.elements.openchatListMeta.textContent = exactId
        ? rows.length
          ? '該当メッセージ 1 件（id: ' + exactId + '）'
          : '該当メッセージなし（id: ' + exactId + '）'
        : '表示 ' + rows.length + ' 件（ready・取得元／日時つき）';
    }
    const streamLabel = function (st) {
      if (st === 'thread') return 'スレッド';
      if (st === 'thread_reply') return 'スレッド返信';
      return 'メイン';
    };
    tbody.innerHTML = rows
      .map(function (r) {
        const when = String(r.posted_at || r.postedAt || r.post_date || r.postDate || '').trim();
        const snippet = App.cleanOpenchatDisplayText(r.content)
          .replace(/\s+/g, ' ')
          .trim()
          .slice(0, 180);
        const rowId = String(r.id || '').trim();
        const highlight =
          exactId && rowId === exactId ? ' bg-amber-50 ring-1 ring-amber-200' : '';
        return (
          '<tr class="border-t align-top' +
          highlight +
          '" data-openchat-id="' +
          App.escapeHtml(rowId) +
          '">' +
          '<td class="p-2 whitespace-nowrap text-xs">' +
          App.escapeHtml(String(r.chat_title || r.chatTitle || '')) +
          '</td>' +
          '<td class="p-2 whitespace-nowrap text-xs">' +
          App.escapeHtml(streamLabel(String(r.stream_type || r.streamType || ''))) +
          '</td>' +
          '<td class="p-2 whitespace-nowrap text-xs">' +
          App.escapeHtml(App.formatOpenchatDateTime(when)) +
          '</td>' +
          '<td class="p-2 whitespace-nowrap text-xs">' +
          '<span class="openchat-sender">' + App.escapeHtml(String(r.sender_name || r.senderName || '')) + '</span>' +
          '</td>' +
          '<td class="p-2 text-xs text-slate-700">' +
          App.escapeHtml(snippet) + '<span class="openchat-attachment-slot" data-openchat-source-id="'+App.escapeHtml(rowId)+'" data-when="'+App.escapeHtml(when)+'" data-who="'+App.escapeHtml(String(r.sender_name || r.senderName || ''))+'"></span>' +
          '</td></tr>'
        );
      })
      .join('');
    tbody.querySelectorAll('.openchat-attachment-slot').forEach(function(container){
      App.appendAttachmentLinks(container,container.getAttribute('data-openchat-source-id'),'添付：','openchat',App.attachmentMetaFromElement(container));
    });
  },

  ensureReferenceData: async (screen) => {
    const key=screen==='knowledge'?'knowledge':'comments';
    const ready=App.state.referenceReady||(App.state.referenceReady={});
    const loads=App.state.referenceLoads||(App.state.referenceLoads={});
    if(ready[key])return;
    if(loads[key])return loads[key];
    const generation=App.state.attachmentGeneration;
    if(key==='comments'&&App.elements.commentListMeta)App.elements.commentListMeta.textContent='コメント一覧を取得中…';
    const task=(key==='comments'?App.loadComments():App.loadKnowledge()).then(()=>{if(App.state.attachmentGeneration===generation)ready[key]=true;}).catch(error=>{if(App.state.attachmentGeneration===generation)App.showToast(error.message||'参照一覧の取得に失敗しました。メニューを開き直して再試行してください。','error');}).finally(()=>{delete loads[key];if(key==='comments'&&App.state.attachmentGeneration===generation&&App.elements.commentTableBody)App.renderCommentTable();});
    loads[key]=task;return task;
  },

  loadComments: async () => {
    const generation=App.state.attachmentGeneration;
    const uid=String((App.state.currentUser||{}).id||'');
    const current=()=>App.state.attachmentGeneration===generation&&String((App.state.currentUser||{}).id||'')===uid;
    let rows=[];
    if(App.authGatewayBase){
      let after=0;
      for(let page=0;page<100;page++){
        const res=await App.retryRead(()=>App.apiClient('POST','/comments-page',{after_id:after}),current);
        if(!current())return;
        const part=res&&res.comments;
        if(!Array.isArray(part)||part.length>500)throw new Error('コメント一覧の取得結果を確認できませんでした');
        let previous=after;
        for(const row of part){const id=Number(row.id);if(!Number.isSafeInteger(id)||id<=previous)throw new Error('コメント一覧の順序を確認できませんでした');previous=id;}
        rows.push(...part);
        App.state.commentsLoadedCount=rows.length;
        if(part.length<500)break;
        after=previous;
        if(page===99)throw new Error('コメント一覧の上限を超えました');
      }
    }else{const res=await App.apiClient('GET','/comments');rows=(res&&res.comments)||[];}
    if(!current())return;
    rows.sort((a,b)=>String(b.posted_at||'').localeCompare(String(a.posted_at||''))||Number(b.id)-Number(a.id));
    App.state.comments = rows.map(App.enrichCommentCategory);
    try{localStorage.setItem('qa_comments_total',String(rows.length));}catch(e){/* ignore */}
    App.renderCommentCategoryFilterOptions();
    App.renderCommentTable();
    App.renderLessonCourseTabFilterOptions();
    App.renderLessonTable();
  },

  ensureForumCategoryLookup: () => {
    if (App.state.forumCategoryLookup) return App.state.forumCategoryLookup;
    let fromWindow = null;
    if (typeof window !== 'undefined') {
      // publish 注入は FORUM_CATEGORY_LOOKUP。旧名 __FORUM_CATEGORY_LOOKUP__ も許容
      fromWindow =
        window.FORUM_CATEGORY_LOOKUP ||
        window.__FORUM_CATEGORY_LOOKUP__ ||
        null;
    }
    App.state.forumCategoryLookup = fromWindow && typeof fromWindow === 'object' ? fromWindow : {};
    return App.state.forumCategoryLookup;
  },

  normalizeCommentIdForLookup: (raw) => {
    let cid = String(raw || '').trim();
    if (!cid) return '';
    if (cid.indexOf('comment-') === 0) cid = cid.slice(8).trim();
    return cid;
  },

  lookupForumCategory: (commentId) => {
    const lookup = App.ensureForumCategoryLookup();
    const cid = App.normalizeCommentIdForLookup(commentId);
    if (!cid) return '';
    let hit = lookup[cid];
    if (hit == null && lookup[commentId] != null) hit = lookup[commentId];
    if (hit == null && lookup['comment-' + cid] != null) hit = lookup['comment-' + cid];
    if (hit == null) return '';
    if (typeof hit === 'string') return hit.trim();
    if (typeof hit === 'object') {
      return String(hit.forum_category || hit.forumCategory || '').trim();
    }
    return String(hit).trim();
  },

  enrichCommentCategory: (row) => {
    if (!row || typeof row !== 'object') return row;
    const referenceMeta=(App.state.referenceComments||{})[String(row.comment_id||row.commentId||'')]||{};
    if(!row.forum_category && referenceMeta.forum_category)row.forum_category=referenceMeta.forum_category;
    const existing = String(row.forum_category || row.forumCategory || '').trim();
    if (existing && existing !== '未分類') {
      row.forum_category = existing;
      return row;
    }
    const cidRaw = row.comment_id || row.commentId || '';
    const mapped = App.lookupForumCategory(cidRaw);
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

  resolveCommentPostedAt: (row) => {
    if (!row) return '';
    const direct = String(row.posted_at || row.postedAt || '').trim();
    if (direct) return direct;
    const cid = String(row.comment_id || row.commentId || '').trim();
    if (!cid) return '';
    const metadata = (App.state.referenceComments || {})[cid];
    if(metadata && metadata.posted_at)return String(metadata.posted_at);
    const hit = (App.state.comments || []).find(function (c) {
      return String(App.commentField(c, 'comment_id') || '').trim() === cid;
    });
    return hit ? String(App.commentField(hit, 'posted_at') || '').trim() : '';
  },

  loadKnowledge: async () => {
    const generation=App.state.attachmentGeneration;
    try {
      const [srcRes, chunkRes] = await Promise.all([
        App.apiClient('GET', '/knowledge-sources'),
        App.apiClient('GET', '/knowledge-chunks')
      ]);
      if(App.state.attachmentGeneration!==generation)return;
      const sources = (srcRes && srcRes.sources) ? srcRes.sources : [];
      const map = {};
      sources.forEach(function (s) {
        if (s && s.source_key) map[s.source_key] = s;
      });
      App.state.knowledgeSources = map;
      App.state.knowledgeChunks = (chunkRes && chunkRes.chunks) ? chunkRes.chunks : [];
    } catch (e) {
      console.warn('knowledge load skipped', e);
      throw e;
    }
    App.renderKnowledgeTable();
  },

  /** 取込経路の識別ラベル（例: 【Vimeo自動字幕・暫定】）は利用者に見せない */
  displaySourceTitle: (title) => {
    return String(title || '')
      .replace(/^\s*【[^】]*(?:暫定|自動字幕)[^】]*】\s*/, '')
      // 取込時に付けた Vimeo の番号「（動画1106455203）」は会員には不要なので出さない（11/11 松野さん）
      .replace(/\s*[（(]動画\s*[0-9０-９]+[）)]/g, '')
      .trim();
  },

  formatMmSs: (sec) => {
    const s = Math.max(0, Math.floor(Number(sec) || 0));
    const m = Math.floor(s / 60);
    const ss = s % 60;
    return String(m).padStart(2, '0') + ':' + String(ss).padStart(2, '0');
  },

  withVideoTimeUrl: (url, startSec) => {
    if(!url)return '';
    try {
      const u=new URL(url);if(!['http:','https:'].includes(u.protocol))return '';
      const sec=Math.max(0,Math.floor(Number(startSec)||0));
      if(u.hostname==='vimeo.com'||u.hostname.endsWith('.vimeo.com')){u.searchParams.delete('t');u.hash='t='+sec+'s';}
      else {u.searchParams.set('t',String(sec));}
      return u.href;
    }catch(e){return '';}
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

  citationsStorageRootKey: 'qa_citations_v1',
  // 意味検索はデフォルトOFF。ログイン／再読込でONを引き継がない（必要なときだけ手動ON）
  semanticModeStorageKey: 'qa_semantic_mode_v1',

  loadBooleanStorage: (key) => {
    try {
      return localStorage.getItem(key) === '1';
    } catch (e) {
      return false;
    }
  },

  saveBooleanStorage: (key, value) => {
    try {
      localStorage.setItem(key, value ? '1' : '0');
    } catch (e) {
      /* ignore */
    }
  },

  hydrateSemanticMode: () => {
    App.state.semanticMode = false;
    try {
      localStorage.removeItem(App.semanticModeStorageKey);
    } catch (e) {
      /* ignore */
    }
    App.updateSemanticModeButton();
  },

  // (1) 使用量の削減が見える人は、意味検索がふだんの検索。ボタンは「より詳しく調べる」（上位のAI・使い回しなし）。2026-11-11
  semanticBase: () => !!App.authGatewayBase && App.featureOn('cost_saving'),
  semanticHintOld: '',
  applySearchModeUi: () => {
    const hint = document.getElementById('semanticModeHint');
    if (hint && !App.semanticHintOld) App.semanticHintOld = hint.textContent;
    if (App.semanticBase()) {
      if (!App.state.semanticMode) App.state.semanticForced = true;
      App.state.semanticMode = true;
      if (hint) hint.textContent = 'ふだんは意味検索で、言い換えや関連事例まで探して手早く答えます。比較・手順・計算など詳しく知りたいときは「より詳しく調べる」をONにすると、上位のAIで時間をかけて答えます。';
    } else {
      if (App.state.semanticForced) App.state.semanticMode = false;
      App.state.semanticForced = false;
      App.state.deepMode = false;
      if (hint && App.semanticHintOld) hint.textContent = App.semanticHintOld;
    }
    App.updateSemanticModeButton();
  },
  currentAnswerMode: (fast) => fast ? 'fast' : App.semanticBase() ? (App.state.deepMode ? 'deep' : 'semantic') : App.state.semanticMode ? 'semantic' : 'normal',

  updateSemanticModeButton: () => {
    const btn = App.elements.semanticModeToggle;
    if (!btn) return;
    const base = App.semanticBase();
    const on = base ? !!App.state.deepMode : !!App.state.semanticMode;
    btn.textContent = (base ? 'より詳しく調べる: ' : '意味検索モード: ') + (on ? 'ON' : 'OFF');
    btn.title = base ? 'ONにすると、上位のAIで時間をかけて答えます（このタブのあいだだけ）' : '';
    btn.className =
      'shrink-0 px-3 py-1 rounded-full border ' +
      (on
        ? 'border-blue-900 bg-blue-900 text-white'
        : 'border-slate-300 text-slate-700 hover:bg-slate-50');
  },

  openSemanticSearchWarningDialog: () => {
    if (!App.elements.semanticSearchWarningDialog) return;
    if (typeof App.elements.semanticSearchWarningDialog.showModal === 'function') {
      App.elements.semanticSearchWarningDialog.showModal();
    } else {
      App.elements.semanticSearchWarningDialog.setAttribute('open', 'open');
    }
  },

  closeSemanticSearchWarningDialog: () => {
    if (!App.elements.semanticSearchWarningDialog) return;
    if (typeof App.elements.semanticSearchWarningDialog.close === 'function') {
      App.elements.semanticSearchWarningDialog.close();
    } else {
      App.elements.semanticSearchWarningDialog.removeAttribute('open');
    }
  },

  confirmSemanticModeWarning: () => {
    App.state.semanticMode = true;
    App.updateSemanticModeButton();
    App.closeSemanticSearchWarningDialog();
    App.showToast('意味検索モードを有効化しました（このタブのみ・再読込でOFF）', 'success');
  },

  handleSemanticModeToggle: () => {
    if (App.semanticBase()) {
      App.state.deepMode = !App.state.deepMode;
      App.updateSemanticModeButton();
      App.showToast(App.state.deepMode ? 'より詳しく調べる: ON（上位のAIで時間をかけて答えます。このタブのみ）' : 'より詳しく調べる: OFF（ふだんの意味検索に戻しました）', App.state.deepMode ? 'success' : 'info');
      return;
    }
    const nextValue = !App.state.semanticMode;
    // オンにするたびに注意ダイアログを表示（了承後に有効化）
    if (nextValue) {
      App.openSemanticSearchWarningDialog();
      return;
    }
    App.state.semanticMode = false;
    App.updateSemanticModeButton();
    App.showToast('意味検索モードを無効にしました', 'info');
  },

  loadCitationsStore: () => {
    try {
      const raw = localStorage.getItem(App.citationsStorageRootKey);
      const parsed = raw ? JSON.parse(raw) : {};
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch (e) {
      return {};
    }
  },

  saveCitationsStore: (store) => {
    try {
      localStorage.setItem(App.citationsStorageRootKey, JSON.stringify(store || {}));
    } catch (e) {
      console.warn('citations store save skipped', e);
    }
  },

  citationsStorageKey: (sessionId) => 'qa_citations_' + String(sessionId || ''),

  loadCitationsMapForSession: (sessionId) => {
    const sid = String(sessionId || '').trim();
    if (!sid) return {};
    const store = App.loadCitationsStore();
    const map = store[sid];
    return map && typeof map === 'object' ? map : {};
  },

  saveCitationsForMessage: (sessionId, messageId, citations) => {
    const sid = String(sessionId || '').trim();
    const mid = String(messageId || '').trim();
    if (!sid || !mid) return;
    const store = App.loadCitationsStore();
    const sessionMap = store[sid] && typeof store[sid] === 'object' ? store[sid] : {};
    sessionMap[mid] = citations || [];
    store[sid] = sessionMap;
    App.saveCitationsStore(store);
    if (String(App.state.currentSessionId || '') === sid) {
      App.state.citationsByMessageId = Object.assign({}, sessionMap);
      const lastId = App.findLastAssistantMessageId(App.state.chatMessages || []);
      App.state.lastCitations =
        lastId && sessionMap[lastId] ? sessionMap[lastId] : App.state.lastCitations || [];
    }
  },

  findLastAssistantMessageId: (messages) => {
    const list = Array.isArray(messages) ? messages : [];
    for (let i = list.length - 1; i >= 0; i -= 1) {
      if (list[i] && list[i].role === 'assistant') {
        const id = list[i].id != null ? String(list[i].id).trim() : '';
        if (id) return id;
      }
    }
    return '';
  },

  migrateLegacySessionCitations: (sessionId, messages) => {
    const sid = String(sessionId || '').trim();
    if (!sid) return;
    const existing = App.loadCitationsMapForSession(sid);
    if (Object.keys(existing).length > 0) return;
    let legacy = [];
    try {
      const raw = sessionStorage.getItem(App.citationsStorageKey(sid));
      legacy = raw ? JSON.parse(raw) : [];
      if (!Array.isArray(legacy)) legacy = [];
    } catch (e) {
      legacy = [];
    }
    if (!legacy.length) return;
    const msgId = App.findLastAssistantMessageId(messages);
    if (!msgId) return;
    App.saveCitationsForMessage(sid, msgId, legacy);
    try {
      sessionStorage.removeItem(App.citationsStorageKey(sid));
    } catch (e) {
      /* ignore */
    }
  },

  saveCitationsForSession: (sessionId, citations) => {
    const sid = String(sessionId || '').trim();
    if (!sid) return;
    const msgId = App.findLastAssistantMessageId(App.state.chatMessages || []);
    if (!msgId) {
      App.state.lastCitations = citations || [];
      return;
    }
    App.saveCitationsForMessage(sid, msgId, citations);
  },

  restoreCitationsForSession: (sessionId) => {
    if (!sessionId) {
      App.state.citationsByMessageId = {};
      App.state.lastCitations = [];
      return;
    }
    App.migrateLegacySessionCitations(sessionId, App.state.chatMessages || []);
    const map = App.loadCitationsMapForSession(sessionId);
    App.state.citationsByMessageId = Object.assign({}, map);
    const lastId = App.findLastAssistantMessageId(App.state.chatMessages || []);
    App.state.lastCitations =
      lastId && map[lastId] ? map[lastId] : [];
  },

  buildCitationsFromRelated: (relatedComments, relatedChunks, relatedSources, usedFilter, relatedOpenchat, selection) => {
    const citations = [];
    const sourcesMap = Object.assign({}, App.state.knowledgeSources || {});
    const sourcesById = {};
    Object.keys(sourcesMap).forEach(function (k) {
      const s = sourcesMap[k];
      if (s && s.id != null) sourcesById[String(s.id)] = s;
    });
    App.normalizeRelatedList(relatedSources).forEach(function (s) {
      if (s && s.source_key) sourcesMap[s.source_key] = s;
      if (s && s.id != null) sourcesById[String(s.id)] = s;
    });

    const filter = usedFilter || null;
    const commentIdSet = filter && filter.commentIds ? filter.commentIds : null;
    const chunkKeySet = filter && filter.chunkKeys ? filter.chunkKeys : null;
    const openchatIdSet = filter && filter.openchatIds ? filter.openchatIds : null;
    const strict = !!(filter && filter.strict);

    App.normalizeRelatedList(relatedComments).forEach(function (c) {
      const enriched = App.enrichCommentCategory(Object.assign({}, c));
      const cid = String(enriched.comment_id || enriched.commentId || '').trim();
      if (strict && commentIdSet) {
        if (!cid || !commentIdSet[cid]) return;
      }
      const srcSystem = String(enriched.source_system || enriched.sourceSystem || '').trim();
      const isLesson = srcSystem === 'lesson' || String(cid).startsWith('lesson_desc_');
      citations.push({
        kind: isLesson ? 'lesson' : 'comment',
        citationLabel: enriched.citation_label || '',
        sourceType: isLesson ? 'WeStudy基礎動画' : 'WeStudyコミュニティ',
        commentId: cid,
        authorName: enriched.author_name || enriched.authorName || '',
        postedAt: App.resolveCommentPostedAt(enriched),
        inferredYear: Number(((App.state.referenceComments||{})[cid]||{}).inferred_year)||null,
        forumCategory:
          String(enriched.forum_category || enriched.forumCategory || '').trim() || '未分類',
        topicTitle: String(enriched.topic_title || enriched.topicTitle || '').trim(),
        sourceKind: isLesson
          ? String(enriched.course_tab || enriched.courseTab || '基礎動画').trim()
          : String(enriched.source_kind || enriched.sourceKind || 'コミュニティ情報').trim(),
        lessonTitle: isLesson
          ? String(enriched.lesson_title || enriched.lessonTitle || '').trim()
          : '',
        lessonUrl: isLesson ? String(enriched.lesson_url || enriched.lessonUrl || '').trim() : '',
        snippet: String(enriched.content || '').replace(/\s+/g, ' ').slice(0, 220)
      });
    });
    App.normalizeRelatedList(relatedChunks).forEach(function (ch) {
      const chunkKey = String(ch.chunk_key || ch.chunkKey || '').trim();
      if (strict && chunkKeySet) {
        if (!chunkKey || !chunkKeySet[chunkKey]) return;
      }
      const sk = ch.source_key || '';
      let src = sourcesMap[sk] || {};
      if (!src.title && ch.source_id != null) {
        src = sourcesById[String(ch.source_id)] || src;
      }
      const start = ch.start_sec != null ? Number(ch.start_sec) : 0;
      citations.push({
        kind: 'video_chunk',
        citationLabel: ch.citation_label || '',
        sourceType: 'WeStudyセミナー動画',
        chunkKey: chunkKey,
        sourceKey: sk,
        sourceId: ch.source_id,
        videoTitle: App.displaySourceTitle(src.title || sk || '（タイトル不明）'),
        videoUrl: App.withVideoTimeUrl(src.video_url || '', start),
        videoPageUrl: App.knowledgeVideoPageUrl(src,App.knowledgeSourceMeta(src)),
        startSec: start,
        startLabel: App.formatMmSs(start),
        snippet: String(ch.content || '').replace(/\s+/g, ' ').slice(0, 220)
      });
    });
    App.normalizeRelatedList(relatedOpenchat).forEach(function (o) {
      const oid = String(o.id || o.openchat_id || o.openchatId || '').trim();
      if (strict && openchatIdSet) {
        if (!oid || !openchatIdSet[oid]) return;
      }
      const stream = String(o.stream_type || o.streamType || '').trim();
      const streamLabel =
        stream === 'thread'
          ? 'スレッド'
          : stream === 'thread_reply'
            ? 'スレッド返信'
            : 'メイン';
      citations.push({
        kind: 'openchat',
        citationLabel: o.citation_label || '',
        sourceType: 'LINEオプチャ',
        openchatId: oid,
        chatTitle: String(o.chat_title || o.chatTitle || o.chat_name || o.chatName || '').trim(),
        streamLabel: streamLabel,
        threadTitle: String(o.thread_title || o.threadTitle || '').trim(),
        authorName: o.sender_name || o.senderName || '',
        postedAt: o.posted_at || o.postedAt || o.post_date || o.postDate || '',
        snippet: String(o.content || '').replace(/\s+/g, ' ').slice(0, 220)
      });
    });
    return citations.map(c=>Object.assign({},c,{referenceSelection:selection||'unknown'}));
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
    const openchatIds = {};
    const cList = obj.comment_ids || obj.commentIds || [];
    const kList = obj.chunk_keys || obj.chunkKeys || [];
    const oList = obj.openchat_ids || obj.openchatIds || [];
    if (!Array.isArray(cList) || !Array.isArray(kList)) return { ok: false };
    if (!Array.isArray(oList)) return { ok: false };
    cList.forEach(function (id) {
      const s = String(id == null ? '' : id).trim();
      if (s) commentIds[s] = 1;
    });
    kList.forEach(function (k) {
      const s = String(k == null ? '' : k).trim();
      if (s) chunkKeys[s] = 1;
    });
    oList.forEach(function (id) {
      const s = String(id == null ? '' : id).trim();
      if (s) openchatIds[s] = 1;
    });
    return { ok: true, commentIds: commentIds, chunkKeys: chunkKeys, openchatIds: openchatIds, strict: true };
  },

  openCitationInDb: (citation) => {
    if (!citation) return;
    const fromScreen = App.state.currentScreen || 'chat';
    App.state.returnScreen =
      fromScreen === 'comments' ||
      fromScreen === 'lessons' ||
      fromScreen === 'knowledge' ||
      fromScreen === 'openchat'
        ? 'chat'
        : fromScreen;
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
    const commentId = String(citation.commentId || '').trim();
    const isLesson =
      citation.kind === 'lesson' ||
      citation.sourceType === 'WeStudy学習動画' ||
      commentId.indexOf('lesson_desc_') === 0;
    if (isLesson) {
      App.switchScreen('lessons');
      App.showDbReturnBar('lessons');
      if (App.elements.lessonSearchInput) {
        App.elements.lessonSearchInput.value = commentId;
        App.renderLessonTable({ exactCommentId: commentId });
      }
      return;
    }
    if (citation.kind === 'openchat') {
      App.switchScreen('openchat');
      App.showDbReturnBar('openchat');
      const oid = String(citation.openchatId || '').trim();
      if (App.elements.openchatSearchInput) {
        App.elements.openchatSearchInput.value = oid || String(citation.chatTitle || '').trim();
      }
      if (App.elements.openchatTitleFilter) {
        App.elements.openchatTitleFilter.value = '';
      }
      App.loadOpenchatLogs({ openchatId: oid || undefined }).catch(function (err) {
        App.showToast((err && err.message) || 'LINEオプチャの取得に失敗しました', 'error');
      });
      return;
    }
    App.switchScreen('comments');
    App.showDbReturnBar('comments');
    if (App.elements.commentSearchInput) {
      if (App.elements.commentAttachmentsOnly) App.elements.commentAttachmentsOnly.checked = false;
      App.elements.commentSearchInput.value = commentId;
      App.renderCommentTable({ exactCommentId: commentId });
    }
  },

  /**
   * 関連セミナー動画（タイトル単位で集約）＋関連コミュニティ投稿＋関連動画ページ説明
   */
  citationDateLabel: (c) => {
    const date=App.referenceDateParts(c.postedAt);
    return date?date.label:c.inferredYear?c.inferredYear+'年（IDから推定・月日不明）':'日時未記録';
  },

  renderCitationsPanel: (citations, messageId, answer) => {
    if(!citations||!citations.length)return '';
    const esc=App.escapeHtml;
    const badge=c=>c.citationLabel?'<strong class="text-blue-900">['+esc(c.citationLabel)+']</strong> ':'';
    // 根拠を開いたら判断ログに残すため、どの根拠かを li に持たせる（(2) answer_feedback が見える人だけ送る）
    const src=c=>{const key=c.kind==='video_chunk'?(c.chunkKey||c.videoTitle):c.kind==='openchat'?c.openchatId:c.commentId;
      const title=c.kind==='video_chunk'?(c.videoTitle||'動画')+' ・ '+App.formatMmSs(c.startSec||0):c.kind==='lesson'?(c.lessonTitle||c.topicTitle||'講座ページ'):c.kind==='openchat'?[c.chatTitle||'LINEオプチャ',c.threadTitle].filter(Boolean).join(' / '):'コミュニティ投稿 #'+(c.commentId||'')+(c.postedAt?'（'+App.citationDateLabel(c)+'）':'');
      return key?' data-src-kind="'+esc(c.kind)+'" data-src-key="'+esc(key)+'" data-src-title="'+esc(title)+'" data-src-label="'+esc(c.citationLabel||'')+'"':'';};
    const attrs=c=>' id="'+esc(App.citationAnchor(c,messageId))+'" class="mb-2 scroll-mt-4"'+src(c);
    const db=(kind,key)=>' <button type="button" class="citation-db-link text-blue-700 underline" data-kind="'+esc(kind)+'" data-key="'+esc(key||'')+'">本文を見る</button>';
    const dated=(list,item)=>App.groupReferencesByDate(list).map(g=>'<div class="font-medium text-slate-700 mt-2">'+esc(g.label)+'</div><ul class="citations-list mb-2">'+g.items.map(item).join('')+'</ul>').join('');
    const comments=citations.filter(c=>c.kind==='comment');
    const lines=citations.filter(c=>c.kind==='openchat');
    const lessons=citations.filter(c=>c.kind==='lesson');
    const videos=citations.filter(c=>c.kind==='video_chunk');
    const parts=[];
    const expanded=String(answer||'').replace(/(LINEオプチャ|コミュニティ|セミナー)(\d+(?:\s*[、,]\s*\d+)+)/g,(_,p,ns)=>ns.split(/[、,]/).map(n=>p+Number(n.trim())).join('、'));
    const mentioned=Array.from(new Set(expanded.match(/(?:LINEオプチャ|コミュニティ|セミナー)\d+/g)||[]));
    const cited=mentioned.map(label=>citations.find(c=>c.citationLabel===label)).filter(Boolean);
    if(cited.length)parts.push('<div class="font-semibold mb-1">本文で引用した根拠（登場順）</div><ul class="mb-3">'+cited.map(c=>{
      const anchor='<a class="text-blue-700 underline" href="#'+esc(App.citationAnchor(c,messageId))+'">'+esc(c.citationLabel)+'</a>';
      if(c.kind==='video_chunk'){
        const page=App.safeReferenceUrl(c.videoPageUrl),u=page||App.safeReferenceUrl(App.withVideoTimeUrl(c.videoUrl,c.startSec||0));const title=esc(c.videoTitle||'動画タイトル未登録')+' ・ '+esc(App.formatMmSs(c.startSec||0));
        return '<li class="mb-1"'+src(c)+'>'+anchor+' ・ '+(u?'<a class="text-blue-700 underline" target="_blank" rel="noopener noreferrer" href="'+esc(u)+'">'+title+(page?' 元動画ページを開く':' から再生')+'</a>':title)+'</li>';
      }
      if(c.kind==='lesson')return '<li class="mb-1"'+src(c)+'>'+anchor+' ・ '+esc(c.lessonTitle||c.topicTitle||'講座ページ')+db('lesson',c.commentId)+'</li>';
      return '<li class="mb-1"'+src(c)+'>'+anchor+' ・ '+esc(App.citationDateLabel(c))+db(c.kind,c.commentId||c.openchatId)+'</li>';
    }).join('')+'</ul>');
    if(videos.length){
      const rows=videos.map(c=>{
        const page=App.safeReferenceUrl(c.videoPageUrl),url=page||App.safeReferenceUrl(App.withVideoTimeUrl(c.videoUrl||'',c.startSec||0));
        const label=esc(c.videoTitle||'動画タイトル未登録')+' ・ '+esc(App.formatMmSs(c.startSec||0));
        return '<li'+attrs(c)+'>'+badge(c)+(url?'<a class="text-blue-700 underline" target="_blank" rel="noopener noreferrer" href="'+esc(url)+'">'+label+(page?' 元動画ページを開く':' から再生')+'</a>':label+'（動画URL未登録）')+db('video_chunk',c.chunkKey||c.videoTitle)+'<div class="text-slate-600">'+esc(c.snippet||'')+'</div></li>';
      }).join('');
      parts.push('<div class="font-semibold mb-1">動画の根拠（タイトル・再生位置）</div>'+(videos.some(c=>c.videoPageUrl)?'<p class="text-slate-600 mb-2">元動画ページでは、表示された時刻へ移動してください。</p>':'')+'<ul class="citations-list mb-2">'+rows+'</ul>');
    }
    if(comments.length)parts.push('<div class="font-semibold mb-1">コミュニティの根拠</div>'+dated(comments,c=>{
      const d=App.referenceDateParts(c.postedAt),cat=c.forumCategory&&c.forumCategory!=='未分類'?' ・ '+esc(c.forumCategory):'';
      return '<li'+attrs(c)+'>'+badge(c)+esc(App.citationDateLabel(c))+' ・ '+esc(App.formatAuthorForDisplay(c.authorName||''))+cat+' #'+esc(c.commentId||'')+db('comment',c.commentId)+'<div class="text-slate-600">'+esc(c.snippet||'')+'</div><span class="citation-attachments" data-comment-id="'+esc(c.commentId||'')+'" data-when="'+esc(c.postedAt||'')+'" data-who="'+esc(c.authorName||'')+'"></span></li>';
    }));
    if(lines.length)parts.push('<div class="font-semibold mb-1">LINEオプチャの根拠</div>'+dated(lines,c=>{
      const d=App.referenceDateParts(c.postedAt);
      return '<li'+attrs(c)+'>'+badge(c)+(d?esc(d.label)+' ・ ':'')+esc(c.chatTitle||'オプチャ名未登録')+(c.streamLabel?' / '+esc(c.streamLabel):'')+(c.threadTitle?' / '+esc(c.threadTitle):'')+db('openchat',c.openchatId)+'<div class="text-slate-600">'+esc(c.snippet||'')+'</div><div class="openchat-citation-attachments" data-openchat-source-id="'+esc(c.openchatId||'')+'" data-when="'+esc(c.postedAt||'')+'" data-who="'+esc(c.authorName||'')+'"></div></li>';
    }));
    if(lessons.length)parts.push('<div class="font-semibold mb-1">講座ページの根拠</div><ul class="citations-list mb-2">'+lessons.map(c=>{
      const url=App.safeReferenceUrl(c.lessonUrl);
      return '<li'+attrs(c)+'>'+badge(c)+esc(c.lessonTitle||c.topicTitle||c.commentId||'講座')+db('lesson',c.commentId)+(url?' <a class="text-blue-700 underline" target="_blank" rel="noopener noreferrer" href="'+esc(url)+'">講座を開く</a>':'')+'<div class="text-slate-600">'+esc(c.snippet||'')+'</div></li>';
    }).join('')+'</ul>');
    const note=citations.some(c=>c.referenceSelection==='provided-context')?'<p class="text-slate-600 mb-2">回答作成時の参考候補です。本文中の使用箇所が明示されていない情報も含みます。</p>':'';
    return '<div class="citations-panel mt-3 border-t pt-2 text-xs" data-message-id="'+esc(messageId||'')+'">'+note+parts.join('')+'</div>';
  },

  cleanOpenchatDisplayText: (value) => {
    return String(value || '')
      .replace(/\[relatedMessageId\][ \t]*\d+/gi, '')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  },

  formatOpenchatDateTime: (value) => {
    const raw = String(value || '').trim();
    if (!raw) return '';
    if (/^\d{4}[-/]\d{2}[-/]\d{2}$/.test(raw)) return raw.replace(/-/g, '/');
    // タイムゾーンなしの既存日時は日本時間として扱い、UTC日時はJSTへ変換。
    const local = raw.match(/^(\d{4})[-/](\d{2})[-/](\d{2})[ T](\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?$/);
    if (local) return local[1] + '/' + local[2] + '/' + local[3] + ' ' + local[4] + ':' + local[5];
    const date = new Date(raw);
    if (isNaN(date.getTime())) return raw;
    const parts = new Intl.DateTimeFormat('ja-JP', {
      timeZone: 'Asia/Tokyo', year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
    }).formatToParts(date);
    const fields = {};
    parts.forEach(function (p) { fields[p.type] = p.value; });
    return fields.year + '/' + fields.month + '/' + fields.day + ' ' + fields.hour + ':' + fields.minute;
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

  knowledgeSourceMeta: (src) => {
    let meta = src.meta_json || {};
    if (typeof meta === 'string') {
      try { meta = JSON.parse(meta); } catch (e) { meta = {}; }
    }
    return meta && typeof meta === 'object' ? meta : {};
  },

  referenceLabel: (value) => String(value || '').replace(/\s+/g, ' ').trim(),

  referenceLessonInfo: (url) => {
    const key = String(url || '').split('#')[0].replace(/\/$/, '');
    return (window.WESTUDY_COURSE_CATALOG || {})[key] || {};
  },

  knowledgeReferenceInfo: (src) => {
    const meta = App.knowledgeSourceMeta(src);
    const lesson = App.referenceLessonInfo(App.knowledgeVideoPageUrl(src, meta));
    return {
      course: App.referenceLabel(meta.course || meta.course_tab || lesson.course || '未分類'),
      section: App.referenceLabel(meta.section_name || meta.section || lesson.section || '目次未設定'),
      title: lesson.title || App.referenceLabel(App.displaySourceTitle(src.title)).replace(/\s*[（(]動画\s*\d+[）)]\s*$/, '') || src.source_key || '',
      // 選択肢は講座単位。個別動画IDは一覧行の順序・開始秒管理にのみ使う。
      key: App.knowledgeVideoPageUrl(src, meta).split('#')[0] ||
        App.referenceLabel(App.displaySourceTitle(src.title)).replace(/\s*[（(]動画\s*\d+[）)]\s*$/, '') || src.source_key || ''
    };
  },

  referenceCompare: (a, b) => String(a || '').localeCompare(String(b || ''), 'ja', { numeric: true }),

  referenceFilterRows: (prefix) => {
    if (prefix === 'knowledge') return Object.values(App.state.knowledgeSources || {}).map(App.knowledgeReferenceInfo);
    return App.lessonCommentRows().map(function (row) {
      const url = App.commentField(row, 'lesson_url');
      const catalog = App.referenceLessonInfo(url);
      return {
        course: App.referenceLabel(App.commentField(row, 'course_tab') || catalog.course || '未分類'),
        section: App.referenceLabel(App.commentField(row, 'section_name') || catalog.section || '目次未設定'),
        title: catalog.title || App.referenceLabel(App.commentField(row, 'lesson_title') || App.commentField(row, 'topic_title')),
        key: String(url || App.commentField(row, 'comment_id') || '')
      };
    });
  },

  renderReferenceFilters: (prefix) => {
    const rows = App.referenceFilterRows(prefix);
    const names = ['CourseTab', 'Section', 'Title'];
    const fields = ['course', 'section', 'key'];
    const labels = ['全コースタブ', '全目次', prefix === 'knowledge' ? '全動画タイトル' : '全レッスン'];
    let candidates = rows;
    names.forEach(function (name, i) {
      const select = document.getElementById(prefix + name + 'Filter');
      if (!select) return;
      const current = select.value;
      const values = new Map();
      candidates.forEach(function (r) { if (r[fields[i]]) values.set(r[fields[i]], i === 2 ? r.title : r[fields[i]]); });
      select.innerHTML = '';
      select.add(new Option(labels[i], ''));
      Array.from(values.entries()).sort(function (a,b) { return App.referenceCompare(a[1], b[1]); }).forEach(function (entry) {
        select.add(new Option(entry[1], entry[0]));
      });
      select.value = values.has(current) ? current : '';
      if (select.value) candidates = candidates.filter(function (r) { return r[fields[i]] === select.value; });
    });
  },

  changeReferenceFilter: (prefix, index) => {
    ['CourseTab', 'Section', 'Title'].forEach(function (name, i) {
      const select = document.getElementById(prefix + name + 'Filter');
      if (select && i > index) select.value = '';
    });
    App.renderReferenceFilters(prefix);
    if (prefix === 'knowledge') App.renderKnowledgeTable(); else App.renderLessonTable();
  },

  matchesReferenceFilters: (prefix, info) => {
    return ['CourseTab', 'Section', 'Title'].every(function (name, i) {
      const select = document.getElementById(prefix + name + 'Filter');
      return !select || !select.value || info[['course', 'section', 'key'][i]] === select.value;
    });
  },

  knowledgeVideoPageUrl: (src, meta) => {
    const page = String(meta.lesson_url || src.lesson_url || '').trim();
    if (/^https:\/\/westudy\.co\.jp\/lesson\//.test(page)) return page;
    const slug = meta.lesson_slug || (String(src.source_key || '').match(/westudy:([^:]+):vimeo:/) || [])[1];
    if (slug) return 'https://westudy.co.jp/lesson/' + encodeURIComponent(slug);
    const existing = String(src.video_url || '');
    return /^https:\/\/westudy\.co\.jp\/lesson\//.test(existing) ? existing : '';
  },

  renderKnowledgeTable: () => {
    const body = App.elements.knowledgeTableBody;
    if (!body) return;
    App.renderReferenceFilters('knowledge');
    const keyword = String((App.elements.knowledgeSearchInput && App.elements.knowledgeSearchInput.value) || '')
      .trim()
      .toLowerCase();
    const rows = (App.state.knowledgeChunks || []).filter(function (ch) {
      const src = App.state.knowledgeSources[ch.source_key] || {};
      const info = App.knowledgeReferenceInfo(src);
      if (!App.matchesReferenceFilters('knowledge', info)) return false;
      if (!keyword) return true;
      const hay = [
        ch.chunk_key,
        ch.content,
        ch.search_text,
        ch.source_key,
        src.title,
        info.course,
        info.section,
        src.video_id
      ]
        .join(' ')
        .toLowerCase();
      return hay.indexOf(keyword) !== -1;
    }).sort(function (a, b) {
      const sa = App.knowledgeReferenceInfo(App.state.knowledgeSources[a.source_key] || {});
      const sb = App.knowledgeReferenceInfo(App.state.knowledgeSources[b.source_key] || {});
      return App.referenceCompare(sa.course, sb.course) || App.referenceCompare(sa.title, sb.title) ||
        App.referenceCompare(a.source_key, b.source_key) || Number(a.start_sec || 0) - Number(b.start_sec || 0);
    });
    body.innerHTML = '';
    rows.slice(0, 500).forEach(function (ch) {
      const src = App.state.knowledgeSources[ch.source_key] || {};
      const start = ch.start_sec != null ? Number(ch.start_sec) : 0;
      const meta = App.knowledgeSourceMeta(src);
      const info = App.knowledgeReferenceInfo(src);
      // Vimeoの限定公開は直URLだと再生できない。正規のWeStudy埋込ページを開く。
      const url = App.knowledgeVideoPageUrl(src, meta) || App.withVideoTimeUrl(src.video_url || '', start);
      const tr = document.createElement('tr');
      tr.className = 'border-t align-top';
      tr.innerHTML =
        '<td class="p-2 whitespace-nowrap">' +
        App.escapeHtml(info.course) +
        '</td>' +
        '<td class="p-2">' +
        App.escapeHtml(App.displaySourceTitle(src.title) || ch.source_key || '') +
        '</td>' +
        '<td class="p-2">' + App.escapeHtml(info.section) + '</td>' +
        '<td class="p-2 whitespace-nowrap">' + App.escapeHtml(App.formatMmSs(start)) + '</td>' +
        '<td class="p-2 whitespace-nowrap">' + (ch.end_sec != null ? App.escapeHtml(App.formatMmSs(ch.end_sec)) : '—') + '</td>' +
        '<td class="p-2">' +
        App.escapeHtml(String(ch.content || '').slice(0, 180)) +
        '</td>' +
        '<td class="p-2">' +
        (url
          ? '<a class="text-blue-600 underline" target="_blank" rel="noopener noreferrer" href="' +
            App.escapeHtml(url) +
            '" title="WeStudyにログインして講座ページの動画を再生">開く</a>'
          : '') +
        '</td>';
      body.appendChild(tr);
    });
    if (App.elements.knowledgeListMeta) {
      App.elements.knowledgeListMeta.textContent =
        '表示 ' + Math.min(rows.length, 500) + ' / 該当 ' + rows.length + ' / 全 ' + (App.state.knowledgeChunks || []).length + ' 件（動画ごと・開始時刻順）';
    }
  },


  loadApprovedUsers: async () => {
    if (!App.isStaffAdmin()) return;
    const res = await App.apiClient('GET', '/admin/users');
    App.state.approvedUsers = (res && res.users) ? res.users : [];
    App.renderApprovedUsers();
    App.renderAdmins();
  },

  loadRoleRequests: async () => {
    if (!App.isStaffAdmin()) return;
    try {
      const res = await App.apiClient('GET', '/admin/role-requests/pending');
      App.state.roleRequestUsers = (res && res.requests) ? res.requests : [];
    } catch (e) {
      App.state.roleRequestUsers = [];
      console.warn('role requests load failed', e);
    }
    App.renderRoleRequests();
  },

  loadAdminLists: async () => {
    await Promise.all([App.loadApprovedUsers(), App.loadRoleRequests(), App.loadPendingMasterTransfer()]);
  },


  pendingActionForUser: (userId) => {
    const want = 'admin_role_req_' + String(userId || '');
    const list = App.state.roleRequestUsers || [];
    for (let i = 0; i < list.length; i += 1) {
      if (String(list[i].comment_id || '') === want) {
        return String(list[i].parent_comment_id || list[i].topic_title || '').trim();
      }
    }
    return '';
  },

  generalUsers: () => {
    return (App.state.approvedUsers || []).filter(function (u) {
      return (u.role || 'user') === 'user';
    });
  },

  adminUsersOnly: () => {
    return (App.state.approvedUsers || []).filter(function (u) {
      const r = u.role || '';
      return r === 'admin' || r === 'master_admin';
    });
  },

  renderApprovedUsers: () => {
    const body = App.elements.approvedUsersTableBody;
    if (!body) return;
    body.innerHTML = '';
    if (!App.isStaffAdmin()) return;
    const list = App.generalUsers();
    if (!list.length) {
      body.innerHTML = '<tr><td colspan="6" class="p-3 text-slate-500">一般ユーザはいません</td></tr>';
      return;
    }
    const isMaster = App.isMasterAdmin();
    list.forEach(function (u) {
      const tr = document.createElement('tr');
      tr.className = 'border-t';
      const req = App.pendingActionForUser(u.id);
      const reqNote = req ? '<div class="text-xs text-amber-700 mt-1">申請中: ' + App.escapeHtml(req) + '</div>' : '';
      let actions = '';
      if (isMaster) {
        actions +=
          '<button type="button" class="grant-admin-btn px-3 py-1 rounded bg-blue-600 text-white text-xs" data-id="' +
          App.escapeHtml(u.id) +
          '">管理者にする</button>';
      } else {
        actions +=
          '<button type="button" class="request-grant-btn px-3 py-1 rounded bg-blue-600 text-white text-xs" data-id="' +
          App.escapeHtml(u.id) +
          '"' +
          (req ? ' disabled' : '') +
          '>管理者申請</button>';
      }
      actions +=
        '<button type="button" class="withdraw-user-btn px-3 py-1 rounded bg-red-600 text-white text-xs" data-id="' +
        App.escapeHtml(u.id) +
        '" data-email="' +
        App.escapeHtml(u.email || '') +
        '">退会削除</button>';
      tr.innerHTML =
        '<td class="p-2">' +
        App.escapeHtml(u.id) +
        '</td>' +
        '<td class="p-2">' +
        App.escapeHtml(u.name || '') +
        '</td>' +
        '<td class="p-2">' +
        App.escapeHtml(u.email || '') +
        reqNote +
        '</td>' +
        '<td class="p-2">' +
        App.escapeHtml(u.member_no || '') +
        '</td>' +
        '<td class="p-2">' +
        App.escapeHtml(u.prefecture || '') +
        '</td>' +
        '<td class="p-2"><div class="flex flex-wrap gap-2">' +
        actions +
        '</div></td>';
      body.appendChild(tr);
    });
    body.querySelectorAll('.grant-admin-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        App.setUserRoleInstant(btn.getAttribute('data-id'), 'admin');
      });
    });
    body.querySelectorAll('.request-grant-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        App.createRoleRequest(btn.getAttribute('data-id'), 'grant');
      });
    });
    body.querySelectorAll('.withdraw-user-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        App.confirmWithdrawUser(btn.getAttribute('data-id'), btn.getAttribute('data-email'));
      });
    });
  },

  renderAdmins: () => {
    const body = App.elements.adminsTableBody;
    if (!body) return;
    body.innerHTML = '';
    if (!App.isStaffAdmin()) return;
    const list = App.adminUsersOnly();
    if (!list.length) {
      body.innerHTML = '<tr><td colspan="6" class="p-3 text-slate-500">管理者はいません</td></tr>';
      return;
    }
    const isMaster = App.isMasterAdmin();
    const selfId = String((App.state.currentUser && App.state.currentUser.id) || '');
    list.forEach(function (u) {
      const tr = document.createElement('tr');
      tr.className = 'border-t';
      const role = u.role || '';
      const roleLabel =
        role === 'master_admin'
          ? '<span class="inline-block px-2 py-0.5 rounded bg-amber-100 text-amber-900 text-xs">マスター</span>'
          : '<span class="inline-block px-2 py-0.5 rounded bg-slate-100 text-slate-700 text-xs">管理者</span>';
      const req = App.pendingActionForUser(u.id);
      const reqNote = req ? '<div class="text-xs text-amber-700 mt-1">申請中: ' + App.escapeHtml(req) + '</div>' : '';
      let actions = '—';
      if (role !== 'master_admin' && String(u.id) !== selfId) {
        if (isMaster) {
          actions =
            '<button type="button" class="transfer-master-btn px-3 py-1 rounded bg-amber-700 text-white text-xs" data-id="' +
            App.escapeHtml(u.id) +
            '" data-email="' +
            App.escapeHtml(u.email || '') +
            '">マスターを移譲する</button>';
          actions +=
            '<button type="button" class="revoke-admin-btn ml-2 px-3 py-1 rounded bg-slate-700 text-white text-xs" data-id="' +
            App.escapeHtml(u.id) +
            '">管理者から外す</button>';
          actions +=
            '<button type="button" class="withdraw-admin-btn ml-2 px-3 py-1 rounded bg-red-600 text-white text-xs" data-id="' +
            App.escapeHtml(u.id) +
            '" data-email="' +
            App.escapeHtml(u.email || '') +
            '">退会削除</button>';
        } else {
          actions =
            '<button type="button" class="request-revoke-btn px-3 py-1 rounded bg-slate-700 text-white text-xs" data-id="' +
            App.escapeHtml(u.id) +
            '"' +
            (req ? ' disabled' : '') +
            '>除外申請</button>';
        }
      }
      tr.innerHTML =
        '<td class="p-2">' +
        App.escapeHtml(u.id) +
        '</td>' +
        '<td class="p-2">' +
        App.escapeHtml(u.name || '') +
        '</td>' +
        '<td class="p-2">' +
        App.escapeHtml(u.email || '') +
        reqNote +
        '</td>' +
        '<td class="p-2">' +
        App.escapeHtml(u.member_no || '') +
        '</td>' +
        '<td class="p-2">' +
        roleLabel +
        '</td>' +
        '<td class="p-2">' +
        actions +
        '</td>';
      body.appendChild(tr);
    });
    body.querySelectorAll('.transfer-master-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        App.startMasterTransfer(btn.getAttribute('data-id'), btn.getAttribute('data-email'));
      });
    });
    body.querySelectorAll('.revoke-admin-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        App.setUserRoleInstant(btn.getAttribute('data-id'), 'user');
      });
    });
    body.querySelectorAll('.request-revoke-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        App.createRoleRequest(btn.getAttribute('data-id'), 'revoke');
      });
    });
    body.querySelectorAll('.withdraw-admin-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        App.confirmWithdrawUser(btn.getAttribute('data-id'), btn.getAttribute('data-email'));
      });
    });
  },

  renderRoleRequests: () => {
    const body = App.elements.roleRequestsTableBody;
    if (!body) return;
    body.innerHTML = '';
    const list = App.state.roleRequestUsers || [];
    if (!list.length) {
      body.innerHTML = '<tr><td colspan="5" class="p-3 text-slate-500">承認待ちの権限申請はありません</td></tr>';
      return;
    }
    const isMaster = App.isMasterAdmin();
    const usersById = {};
    (App.state.approvedUsers || []).forEach(function (u) {
      usersById[String(u.id)] = u;
    });
    list.forEach(function (req) {
      const cid = String(req.comment_id || '');
      const targetId = cid.indexOf('admin_role_req_') === 0 ? cid.slice('admin_role_req_'.length) : '';
      const target = usersById[targetId] || {};
      const action = String(req.parent_comment_id || req.topic_title || '').trim();
      const actionLabel = action === 'grant' ? '管理者に昇格' : action === 'revoke' ? '管理者から除外' : action;
      let ops = '—';
      if (isMaster && targetId) {
        ops =
          '<button type="button" class="approve-role-req-btn px-3 py-1 rounded bg-blue-600 text-white text-xs" data-id="' +
          App.escapeHtml(targetId) +
          '" data-action="' +
          App.escapeHtml(action) +
          '">承認</button>' +
          '<button type="button" class="reject-role-req-btn ml-2 px-3 py-1 rounded bg-slate-500 text-white text-xs" data-id="' +
          App.escapeHtml(targetId) +
          '">却下</button>';
      }
      const tr = document.createElement('tr');
      tr.className = 'border-t';
      const targetLabel = target.name
        ? target.name + '（' + (target.email || '') + '）'
        : target.email || req.content || '';
      tr.innerHTML =
        '<td class="p-2">' +
        App.escapeHtml(targetLabel) +
        ' <span class="text-xs text-slate-400">#' +
        App.escapeHtml(targetId) +
        '</span></td>' +
        '<td class="p-2">' +
        App.escapeHtml(actionLabel) +
        '</td>' +
        '<td class="p-2">' +
        App.escapeHtml(req.author_name || '') +
        '</td>' +
        '<td class="p-2">' +
        App.escapeHtml(req.posted_at || '') +
        '</td>' +
        '<td class="p-2">' +
        ops +
        '</td>';
      body.appendChild(tr);
    });
    body.querySelectorAll('.approve-role-req-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        App.approveRoleRequest(btn.getAttribute('data-id'), btn.getAttribute('data-action'));
      });
    });
    body.querySelectorAll('.reject-role-req-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        App.rejectRoleRequest(btn.getAttribute('data-id'));
      });
    });
  },

  createRoleRequest: async (userId, action) => {
    if (!App.isStaffAdmin()) return;
    if (String(userId) === String(App.state.currentUser.id)) {
      App.showToast('自分自身の権限は変更できません', 'error');
      return;
    }
    try {
      const commentId = 'admin_role_req_' + String(userId);
      await App.apiClient('POST', '/admin/users/' + userId + '/role-requests', {
        actor_user_id: App.state.currentUser.id,
        actor_email: App.state.currentUser.email || '',
        action: action,
        requested_at: new Date().toISOString(),
        comment_id: commentId,
        content: 'role_request ' + action + ' target=' + String(userId)
      });
      App.showToast(action === 'grant' ? '管理者への昇格を申請しました' : '管理者除外を申請しました', 'success');
      await App.loadAdminLists();
    } catch (error) {
      App.showToast((error && error.message) || '申請に失敗しました', 'error');
    }
  },

  setUserRoleInstant: async (userId, role) => {
    if (!App.isMasterAdmin()) {
      App.showToast('マスター管理者のみ即時変更できます', 'error');
      return;
    }
    if (String(userId) === String(App.state.currentUser.id)) {
      App.showToast('自分自身の権限は変更できません', 'error');
      return;
    }
    const ok = await App.openConfirmDialog(
      role === 'admin' ? '管理者に設定' : '管理者から外す',
      role === 'admin'
        ? 'このユーザを管理者に設定します。よろしいですか？'
        : 'このユーザの管理者権限を外します。よろしいですか？'
    );
    if (!ok) return;
    try {
      await App.apiClient('POST', '/admin/users/' + userId + '/set-role', {
        actor_user_id: App.state.currentUser.id,
        role: role
      });
      App.showToast('権限を更新しました', 'success');
      await App.loadAdminLists();
    } catch (error) {
      App.showToast((error && error.message) || '権限更新に失敗しました', 'error');
    }
  },

  approveRoleRequest: async (userId, action) => {
    if (!App.isMasterAdmin()) return;
    const newRole = action === 'grant' ? 'admin' : 'user';
    try {
      await App.apiClient('PUT', '/admin/role-requests/' + userId + '/approve', {
        actor_user_id: App.state.currentUser.id,
        new_role: newRole,
        comment_id: 'admin_role_req_' + String(userId)
      });
      App.showToast('権限申請を承認しました', 'success');
      await App.loadAdminLists();
    } catch (error) {
      App.showToast((error && error.message) || '承認に失敗しました', 'error');
    }
  },

  rejectRoleRequest: async (userId) => {
    if (!App.isMasterAdmin()) return;
    try {
      await App.apiClient('PUT', '/admin/role-requests/' + userId + '/reject', {
        actor_user_id: App.state.currentUser.id,
        comment_id: 'admin_role_req_' + String(userId)
      });
      App.showToast('権限申請を却下しました', 'info');
      await App.loadAdminLists();
    } catch (error) {
      App.showToast((error && error.message) || '却下に失敗しました', 'error');
    }
  },

  confirmWithdrawUser: async (userId, email) => {
    const target = (App.state.approvedUsers || []).find(function (u) {
      return String(u.id) === String(userId);
    });
    if (!App.isMasterAdmin() && target && (target.role === 'admin' || target.role === 'master_admin')) {
      App.showToast('管理者の退会はマスター管理者のみ実行できます', 'error');
      return;
    }
    const ok = await App.openConfirmDialog(
      '退会削除',
      (email || 'このユーザ') +
        ' を退会（ログイン不可）にします。チャット履歴は残ります。よろしいですか？'
    );
    if (!ok) return;
    try {
      await App.apiClient('PUT', '/admin/users/' + userId + '/withdraw', {
        actor_user_id: App.state.currentUser.id
      });
      App.showToast('退会処理しました', 'success');
      await App.loadAdminLists();
    } catch (error) {
      App.showToast((error && error.message) || '退会処理に失敗しました', 'error');
    }
  },


  loadMembers: async () => {
    if (!App.isStaffAdmin()) return;
    const res = await App.apiClient('GET', '/admin/members');
    App.state.members = (res && res.members) ? res.members : [];
    App.renderMembers();
  },

  renderMembers: () => {
    const body = App.elements.membersTableBody;
    if (!body) return;
    body.innerHTML = '';
    const list = App.state.members || [];
    const activeCount = list.filter(function (m) {
      return (m.status || '') === 'active';
    }).length;
    const registeredCount = list.filter(function (m) {
      return (m.status || '') === 'registered';
    }).length;
    if (App.elements.membersListMeta) {
      App.elements.membersListMeta.textContent =
        '全 ' + list.length + ' 件（未登録 ' + activeCount + ' / 登録済 ' + registeredCount + '）';
    }
    if (!list.length) {
      body.innerHTML = '<tr><td colspan="4" class="p-3 text-slate-500">名簿は空です。CSVを取り込んでください。</td></tr>';
      return;
    }
    const sorted = list.slice().sort(function (a, b) {
      return String(a.member_no || '').localeCompare(String(b.member_no || ''), 'ja');
    });
    sorted.forEach(function (m) {
      const tr = document.createElement('tr');
      tr.className = 'border-t';
      const status = m.status || '';
      const statusLabel =
        status === 'registered'
          ? '<span class="inline-block px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 text-xs">登録済</span>'
          : '<span class="inline-block px-2 py-0.5 rounded bg-slate-100 text-slate-700 text-xs">未登録</span>';
      tr.innerHTML =
        '<td class="p-2">' +
        App.escapeHtml(m.member_no || '') +
        '</td>' +
        '<td class="p-2">' +
        App.escapeHtml(m.name || '') +
        '</td>' +
        '<td class="p-2">' +
        App.escapeHtml(m.email || '') +
        '</td>' +
        '<td class="p-2">' +
        statusLabel +
        '</td>';
      body.appendChild(tr);
    });
  },

  upsertMemberRow: async (memberNo, name, email, existingByNo) => {
    const existing = existingByNo[memberNo];
    const status = existing && existing.status === 'registered' ? 'registered' : 'active';
    const payload = {
      member_no: memberNo,
      name: name || '',
      email: email,
      status: status
    };
    if (existing) {
      await App.apiClient('POST', '/admin/members/update', payload);
      return 'updated';
    }
    await App.apiClient('POST', '/admin/members', payload);
    existingByNo[memberNo] = { member_no: memberNo, name: name, email: email, status: status };
    return 'created';
  },

  downloadMembersCsvTemplate: () => {
    // Excel 向けに UTF-8 BOM 付き。1行目=ヘッダー、2行目=記入例（取込前に差し替え可）
    const lines = [
      'member_no,name,email',
      'A12345,山田太郎,taro.yamada@example.com'
    ];
    const csv = '\uFEFF' + lines.join('\r\n') + '\r\n';
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'members_import_template.csv';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 1000);
    App.showToast('名簿CSVフォーマットをダウンロードしました', 'success');
  },

  importMembersCsv: async () => {
    if (!App.isStaffAdmin()) {
      App.showToast('管理者のみ実行できます', 'error');
      return;
    }
    const file = App.elements.membersCsvFileInput && App.elements.membersCsvFileInput.files[0];
    if (!file) {
      App.showToast('CSVファイルを選択してください', 'error');
      return;
    }
    App.setLoading(true);
    if (App.elements.membersImportResult) {
      App.elements.membersImportResult.textContent = '';
    }
    try {
      const text = await file.text();
      const rows = App.parseCsv(text);
      if (!rows.length) {
        App.showToast('CSVデータが空です', 'error');
        return;
      }
      const headerKeys = Object.keys(rows[0] || {});
      const looksLikeOneColumn =
        headerKeys.length === 1 &&
        (headerKeys[0].indexOf('member') !== -1 ||
          headerKeys[0].indexOf('会員') !== -1 ||
          headerKeys[0].indexOf('email') !== -1) &&
        (headerKeys[0].indexOf(',') !== -1 || headerKeys[0].indexOf(';') !== -1);
      if (looksLikeOneColumn) {
        App.showToast(
          'CSVの列が分割されていません。Excelは「CSV UTF-8（コンマ区切り）」で保存してください。',
          'error'
        );
        return;
      }

      await App.loadMembers();
      const existingByNo = {};
      (App.state.members || []).forEach(function (m) {
        if (m && m.member_no) existingByNo[String(m.member_no)] = m;
      });

      let created = 0;
      let updated = 0;
      let skipped = 0;
      let failed = 0;

      for (let i = 0; i < rows.length; i += 1) {
        const row = rows[i];
        const memberNo = String(
          App.csvCell(row, 'member_no', '会員番号', 'MemberNo', 'memberNo') || ''
        ).trim();
        const name = String(App.csvCell(row, 'name', '氏名', '名前', 'Name') || '').trim();
        const email = String(
          App.csvCell(row, 'email', 'メール', 'メールアドレス', 'Email') || ''
        )
          .trim()
          .toLowerCase();
        if (!memberNo || !email) {
          skipped += 1;
          if (App.elements.membersImportResult) {
            App.elements.membersImportResult.textContent +=
              'SKIP row=' + (i + 2) + ' member_no/email 不足\n';
          }
          continue;
        }
        try {
          const result = await App.upsertMemberRow(memberNo, name, email, existingByNo);
          if (result === 'updated') updated += 1;
          else created += 1;
          if ((i + 1) % 50 === 0 && App.elements.membersImportResult) {
            App.elements.membersImportResult.textContent =
              '進捗 ' + (i + 1) + '/' + rows.length + ' …\n' + App.elements.membersImportResult.textContent;
          }
        } catch (rowErr) {
          failed += 1;
          if (App.elements.membersImportResult) {
            App.elements.membersImportResult.textContent +=
              'FAIL row=' +
              (i + 2) +
              ' ' +
              memberNo +
              ' ' +
              ((rowErr && rowErr.message) || 'error') +
              '\n';
          }
        }
      }

      await App.loadMembers();
      const summary =
        '新規 ' + created + ' / 更新 ' + updated + ' / スキップ ' + skipped + ' / 失敗 ' + failed;
      if (App.elements.membersImportResult) {
        App.elements.membersImportResult.textContent =
          '完了: ' + summary + '\n' + (App.elements.membersImportResult.textContent || '');
      }
      App.showToast('名簿取込完了 ' + summary, failed === 0 ? 'success' : 'info');
    } catch (error) {
      App.showToast((error && error.message) || '名簿CSV取込に失敗しました', 'error');
    } finally {
      App.setLoading(false);
    }
  },

  loadPendingUsers: async () => {
    if (!App.isStaffAdmin()) return;
    const res = await App.apiClient('GET', '/admin/users/pending');
    App.state.pendingUsers = (res && res.users) ? res.users : [];
    App.state.rosterMatches = {};
    App.renderPendingUsers();
    void App.loadRosterMatches();
  },

  // (3) 名簿（目標設定・合格状況）との照合。スイッチ auto_approval が見える管理者だけ。2026-11-10
  // 判定はサーバー。画面は印を付けて「名簿一致の人を選ぶ」を出すだけで、承認は人が押す。
  rosterBadges: {
    match: ['名簿一致', 'bg-emerald-100 text-emerald-800'],
    number_only: ['番号だけ一致・名前を確認', 'bg-amber-100 text-amber-800'],
    none: ['名簿になし', 'bg-slate-100 text-slate-600'],
    duplicate: ['同じ番号が複数・確認', 'bg-amber-100 text-amber-800'],
    missing: ['番号か名前が空', 'bg-slate-100 text-slate-600']
  },
  loadRosterMatches: async () => {
    const info = document.getElementById('rosterMatchInfo'), btn = document.getElementById('selectRosterMatchedBtn');
    const show = App.isStaffAdmin() && App.featureOn('auto_approval');
    if (info) info.classList.toggle('hidden', !show);
    if (btn) btn.classList.toggle('hidden', !show);
    if (!show || !App.state.pendingUsers.length) { if (info) info.textContent = ''; return; }
    if (btn && !btn.dataset.bound) {
      btn.dataset.bound = '1';
      btn.addEventListener('click', function () {
        App.elements.pendingUsersTableBody.querySelectorAll('.pending-user-check').forEach(function (cb) {
          cb.checked = (App.state.rosterMatches || {})[cb.getAttribute('data-id')] === 'match';
        });
        App.updateBulkApproveButtonState();
      });
    }
    info.textContent = '名簿と照合中…';
    try {
      const r = await App.apiClient('POST', '/admin/users/pending/roster-match', {});
      App.state.rosterMatches = (r && r.matches) || {};
      App.renderPendingUsers();
      const n = Object.values(App.state.rosterMatches).filter(function (v) { return v === 'match'; }).length;
      const when = r && r.synced_at ? String(r.synced_at).replace('T', ' ').slice(0, 16) : '未取得';
      info.textContent = '名簿一致 ' + n + ' 人／承認待ち ' + App.state.pendingUsers.length + ' 人（名簿の読み込み：' + when + '）';
    } catch (e) {
      info.textContent = '名簿と照合できませんでした: ' + ((e && e.message) || String(e));
    }
  },

  renderAll: () => {
    App.renderSessionList();
    App.renderChatMessages();
    App.renderSuggestedQuestions();
    App.renderCommentTable();
    App.renderLessonTable();
    App.renderPendingUsers();
    App.renderApprovedUsers();
    App.renderAdmins();
    App.renderRoleRequests();
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
      const msgId = m.id != null ? String(m.id).trim() : '';
      const messageCitations = (function () {
        if (m.role !== 'assistant' || !msgId) return [];
        const raw = (App.state.citationsByMessageId || {})[msgId] || [];
        return raw.map(function (c) {
          if(!c)return c;
          if(c.kind==='video_chunk'){const src=Object.values(App.state.knowledgeSources||{}).find(s=>s.source_key===c.sourceKey||String(s.id)===String(c.sourceId));if(src)return Object.assign({},c,{videoTitle:App.displaySourceTitle(src.title||c.videoTitle),videoUrl:App.withVideoTimeUrl(src.video_url||c.videoUrl||'',c.startSec||0),videoPageUrl:App.knowledgeVideoPageUrl(src,App.knowledgeSourceMeta(src))});}
          if (c.kind !== 'comment' || c.postedAt) return c;
          const pa = App.resolveCommentPostedAt({ comment_id: c.commentId });
          const inferred=Number(((App.state.referenceComments||{})[c.commentId]||{}).inferred_year)||c.inferredYear||null;
          return Object.assign({}, c, { postedAt: pa||'',inferredYear:inferred });
        });
      })();

      bubble.className = 'chat-bubble ' + role;
      bubble.innerHTML =
        '<div class="text-[11px] text-slate-500 mb-1">' +
        App.escapeHtml(m.role) + ' ・ ' + App.escapeHtml(m.created_at || '') +
        '</div>' +
        '<div>' +
        (m.role === 'assistant'
          ? '<div class="md-body">' + App.formatAssistantHtml(App.linkReferenceLabels(m.content || '', messageCitations, msgId)) + '</div>'
          : App.escapeHtml(m.content || '')) +
        '</div>' +
        (m.role === 'assistant' ? App.renderCitationsPanel(messageCitations, msgId, m.content) : '') +
        (m.role === 'assistant' && msgId && App.featureOn('answer_feedback') ? App.renderFeedbackBox(msgId) : '');

      wrap.appendChild(bubble);
      area.appendChild(wrap);
    });

    area.querySelectorAll('.citation-db-link').forEach(function (btn) {
      btn.addEventListener('click', function () {
        const kind = btn.getAttribute('data-kind');
        const key = btn.getAttribute('data-key') || '';
        if (kind === 'video_chunk') {
          App.openCitationInDb({ kind: 'video_chunk', videoTitle: key, chunkKey: key });
        } else if (kind === 'lesson') {
          App.openCitationInDb({ kind: 'lesson', commentId: key });
        } else if (kind === 'openchat') {
          App.openCitationInDb({ kind: 'openchat', openchatId: key });
        } else {
          App.openCitationInDb({ kind: 'comment', commentId: key });
        }
      });
    });

    area.querySelectorAll('a[href^="#reference-"]').forEach(function(link){
      link.addEventListener('click',function(event){
        const id=String(link.getAttribute('href')||'').slice(1),target=document.getElementById(id);
        if(!target||!area.contains(target))return;
        event.preventDefault();target.scrollIntoView({block:'start',behavior:'auto'});
      });
    });
    area.querySelectorAll('.answer-feedback').forEach(App.bindFeedbackBox);
    area.querySelectorAll('.citations-panel').forEach(App.bindSourceClicks);
    area.scrollTop = area.scrollHeight;
    area.querySelectorAll('.citation-attachments').forEach(function (container) {
      App.appendAttachmentLinks(container, container.getAttribute('data-comment-id'), '関連添付：', '', App.attachmentMetaFromElement(container));
    });
    area.querySelectorAll('.openchat-citation-attachments').forEach(function(container){
      App.appendAttachmentLinks(container,container.getAttribute('data-openchat-source-id'),'関連添付：','openchat',App.attachmentMetaFromElement(container));
    });
  },

  // (2) 回答の評価（段階公開スイッチ answer_feedback が見える人だけ）。2026-11-10
  // いいね＝理由を聞かない。超いいね・悪いね＝選択肢から複数選ぶ＋その他は任意で書く（11/10 松野さん）。
  // 理由のコードはサーバー（lib/answerFeedback.ts の REASONS）と同じ。悪いねは直す場所に対応させている。
  feedbackChoices: [
    { rating: 'great', label: '超いいね', icon: '🌟', ask: 'どこが特に良かったですか？（いくつでも）', reasons: [
      ['accurate', '内容が正確で信頼できた'], ['practical', '具体的で、すぐ実践に使える'], ['clear', '分かりやすく、まとまっていた'],
      ['source', '根拠・出典（講義や投稿）が役に立った'], ['new_view', '知らなかった視点・情報があった']] },
    { rating: 'good', label: 'いいね', icon: '👍', ask: '', reasons: [] },
    { rating: 'bad', label: '悪いね', icon: '👎', ask: '何が良くなかったですか？（いくつでも）', reasons: [
      ['wrong', '内容が間違っている・情報が古い'], ['off_topic', '質問とずれた答えだった'], ['vague', '一般論で、具体性が足りない'],
      ['hard_to_read', '分かりにくい・長すぎる'], ['no_source', '根拠・出典が足りない、見つからない']] }
  ],
  feedbackChoice: (rating) => App.feedbackChoices.find(function (x) { return x.rating === rating; }) || null,
  feedbackAsk: (rating) => { const c = App.feedbackChoice(rating); return c ? c.ask : ''; },
  feedbackReasonLabel: (code) => {
    for (const c of App.feedbackChoices) for (const r of c.reasons) if (r[0] === code) return r[1];
    return code;
  },
  feedbackBtnClass: (on) => 'answer-feedback-btn px-2 py-1 rounded border text-xs ' + (on ? 'bg-violet-100 border-violet-400' : 'bg-white hover:bg-slate-50'),
  renderFeedbackReasons: (rating, saved) => {
    const c = App.feedbackChoice(rating);
    if (!c || !c.reasons.length) return '';
    const picked = (saved && saved.rating === rating && Array.isArray(saved.reasons)) ? saved.reasons : [];
    return '<fieldset class="mt-2"><legend class="text-slate-600 mb-1">' + App.escapeHtml(c.ask) + '</legend>' +
      '<div class="grid gap-1 sm:grid-cols-2">' + c.reasons.map(function (r) {
        return '<label class="flex items-start gap-2 px-2 py-1 rounded border bg-white cursor-pointer hover:bg-slate-50">' +
          '<input type="checkbox" class="answer-feedback-reason mt-0.5" value="' + r[0] + '"' + (picked.includes(r[0]) ? ' checked' : '') + '>' +
          '<span>' + App.escapeHtml(r[1]) + '</span></label>';
      }).join('') + '</div></fieldset>';
  },
  renderFeedbackBox: (msgId) => {
    const saved = (App.state.feedbackByMessage || {})[msgId] || {};
    const buttons = App.feedbackChoices.map(function (c) {
      const on = saved.rating === c.rating;
      return '<button type="button" class="' + App.feedbackBtnClass(on) + '" data-rating="' + c.rating + '" aria-pressed="' + (on ? 'true' : 'false') + '">' + c.icon + ' ' + c.label + '</button>';
    }).join('');
    return '<div class="answer-feedback mt-2 pt-2 border-t border-slate-200 text-xs" data-message-id="' + App.escapeHtml(msgId) + '">' +
      '<div class="flex flex-wrap items-center gap-2"><span class="text-slate-500">この回答はどうでしたか？</span>' + buttons + '</div>' +
      '<div class="answer-feedback-detail ' + (App.feedbackAsk(saved.rating) ? '' : 'hidden') + '">' +
      '<div class="answer-feedback-reasons">' + App.renderFeedbackReasons(saved.rating, saved) + '</div>' +
      '<div class="answer-feedback-comment mt-2 flex gap-2">' +
      '<input type="text" maxlength="1000" class="flex-1 border rounded px-2 py-1" placeholder="その他（任意）" aria-label="その他（任意）" value="' + App.escapeHtml(saved.comment || '') + '">' +
      '<button type="button" class="answer-feedback-send px-2 py-1 rounded bg-blue-700 text-white">送る</button></div></div>' +
      '<div class="answer-feedback-status text-slate-500 mt-1" role="status" aria-live="polite">' + (saved.sent ? 'ありがとうございます。受け付けました。' : '') + '</div></div>';
  },
  bindFeedbackBox: (box) => {
    const msgId = box.getAttribute('data-message-id');
    const status = box.querySelector('.answer-feedback-status');
    const detail = box.querySelector('.answer-feedback-detail');
    const input = box.querySelector('.answer-feedback-comment input');
    const picked = function () { return Array.from(box.querySelectorAll('.answer-feedback-reason:checked')).map(function (x) { return x.value; }); };
    // 評価は押した時点で送る。理由とその他は「送る」で追加で送る（同じ回答には最後の1件だけが残る）。
    const send = async function (rating, reasons, comment) {
      const chatId = App.state.currentSessionId;
      if (!chatId) return;
      const prev = (App.state.feedbackByMessage || {})[msgId] || {};
      App.state.feedbackByMessage = Object.assign({}, App.state.feedbackByMessage, { [msgId]: { rating: rating, reasons: reasons, comment: comment, sent: false } });
      status.textContent = '送信中…';
      try {
        await App.apiClient('POST', '/answer-feedback', { chat_id: String(chatId), message_id: msgId, rating: rating, reasons: reasons, comment: comment });
        App.state.feedbackByMessage[msgId].sent = true;
        status.textContent = 'ありがとうございます。受け付けました。';
      } catch (e) {
        App.state.feedbackByMessage[msgId] = prev;
        status.textContent = '送れませんでした。時間をおいてもう一度お試しください。';
        return false;
      }
      return true;
    };
    box.querySelectorAll('.answer-feedback-btn').forEach(function (b) {
      b.addEventListener('click', async function () {
        const rating = b.getAttribute('data-rating'), prev = (App.state.feedbackByMessage || {})[msgId] || {};
        if (prev.rating === rating) return; // 同じ評価の押し直しでは選んだ理由を消さない
        // 評価を変えたら前の理由は引き継がない
        if (!(await send(rating, [], ''))) return;
        box.querySelectorAll('.answer-feedback-btn').forEach(function (x) {
          const on = x.getAttribute('data-rating') === rating;
          x.setAttribute('aria-pressed', on ? 'true' : 'false');
          x.className = App.feedbackBtnClass(on);
        });
        box.querySelector('.answer-feedback-reasons').innerHTML = App.renderFeedbackReasons(rating, null);
        input.value = '';
        detail.classList.toggle('hidden', !App.feedbackAsk(rating));
      });
    });
    box.querySelector('.answer-feedback-send').addEventListener('click', function () {
      const cur = (App.state.feedbackByMessage || {})[msgId];
      if (!cur || !cur.rating) { status.textContent = '先にボタンで評価を選んでください。'; return; }
      const reasons = picked(), comment = input.value.trim();
      if (!reasons.length && !comment) { status.textContent = '当てはまるものを選ぶか、その他に書いてください。'; return; }
      void send(cur.rating, reasons, comment);
    });
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

  renderCommentCategoryFilterOptions: () => {
    const select = App.elements.commentCategoryFilter;
    if (!select) return;
    const current = select.value || '';
    const cats = Array.from(
      new Set(
        (App.state.comments || [])
          .filter(function (row) {
            return !App.isLessonCommentRow(row);
          })
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

  communityCommentRows: () => {
    return (App.state.comments || []).filter(function (row) {
      return !App.isLessonCommentRow(row);
    });
  },

  lessonCommentRows: () => {
    return (App.state.comments || []).filter(function (row) {
      return App.isLessonCommentRow(row);
    });
  },

  renderLessonCourseTabFilterOptions: () => {
    const select = App.elements.lessonCourseTabFilter;
    if (!select) return;
    const current = select.value || '';
    const tabs = Array.from(
      new Set(
        App.lessonCommentRows()
          .map(function (row) {
            return String(App.commentField(row, 'course_tab') || '').trim();
          })
          .filter(Boolean)
      )
    ).sort(function (a, b) {
      return a.localeCompare(b, 'ja');
    });
    select.innerHTML = '<option value="">全コースタブ</option>';
    tabs.forEach(function (tab) {
      const opt = document.createElement('option');
      opt.value = tab;
      opt.textContent = tab;
      select.appendChild(opt);
    });
    if (current && tabs.indexOf(current) !== -1) {
      select.value = current;
    }
  },

  renderLessonTable: (opts) => {
    opts = opts || {};
    const body = App.elements.lessonTableBody;
    if (!body) return;
    App.renderReferenceFilters('lesson');
    const keywordRaw = String(
      (App.elements.lessonSearchInput && App.elements.lessonSearchInput.value) || ''
    ).trim();
    const keyword = keywordRaw.toLowerCase();
    const exactFromOpts = String(opts.exactCommentId || '').trim();
    const exactCommentId =
      exactFromOpts ||
      (keywordRaw.indexOf('lesson_desc_') === 0 ? keywordRaw : '');
    const tabFilter =
      (App.elements.lessonCourseTabFilter && App.elements.lessonCourseTabFilter.value) || '';
    body.innerHTML = '';

    const lessonRows = App.lessonCommentRows();
    const filtered = lessonRows.filter(function (row) {
      const cid = String(App.commentField(row, 'comment_id') || '').trim();
      const courseTab = String(App.commentField(row, 'course_tab') || '').trim();
      const sectionName = String(App.commentField(row, 'section_name') || '').trim();
      const lessonTitle = String(
        App.commentField(row, 'lesson_title') || App.commentField(row, 'topic_title') || ''
      ).trim();
      let hitKeyword = true;
      if (exactCommentId) {
        hitKeyword = cid === exactCommentId;
      } else if (keyword) {
        const hay = [
          cid,
          courseTab,
          sectionName,
          lessonTitle,
          String(App.commentField(row, 'content') || ''),
          String(App.commentField(row, 'lesson_url') || '')
        ]
          .join(' ')
          .toLowerCase();
        hitKeyword = hay.indexOf(keyword) !== -1;
      }
      const hitTab = !tabFilter || courseTab === tabFilter;
      const catalog = App.referenceLessonInfo(App.commentField(row, 'lesson_url'));
      const info = { course: App.referenceLabel(courseTab || catalog.course || '未分類'),
        section: App.referenceLabel(sectionName || catalog.section || '目次未設定'),
        key: String(App.commentField(row, 'lesson_url') || cid) };
      return hitKeyword && hitTab && App.matchesReferenceFilters('lesson', info);
    }).sort(function (a,b) {
      return App.referenceCompare(App.commentField(a, 'course_tab'), App.commentField(b, 'course_tab')) ||
        App.referenceCompare(App.commentField(a, 'section_name'), App.commentField(b, 'section_name')) ||
        App.referenceCompare(App.commentField(a, 'lesson_title'), App.commentField(b, 'lesson_title'));
    });

    if (App.elements.lessonListMeta) {
      App.elements.lessonListMeta.textContent =
        '表示 ' + filtered.length + ' / 全 ' + lessonRows.length + ' 件';
    }

    if (filtered.length === 0) {
      body.innerHTML =
        '<tr><td colspan="5" class="p-3 text-slate-500">該当データがありません</td></tr>';
      return;
    }

    filtered.forEach(function (r) {
      const tr = document.createElement('tr');
      tr.className = 'border-t align-top';
      const courseTab = String(App.commentField(r, 'course_tab') || '').trim();
      const sectionName = String(App.commentField(r, 'section_name') || '').trim();
      const lessonTitle = App.referenceLessonInfo(App.commentField(r, 'lesson_url')).title || App.referenceLabel(
        App.commentField(r, 'lesson_title') || App.commentField(r, 'topic_title') || ''
      );
      const url = String(App.commentField(r, 'lesson_url') || '').trim();
      const fullContent = String(App.commentField(r, 'content') || '');
      const previewLen = 160;
      const isTruncated = fullContent.length > previewLen;
      const preview = isTruncated ? fullContent.slice(0, previewLen) + '…' : fullContent;
      tr.innerHTML =
        '<td class="p-2 whitespace-nowrap">' +
        App.escapeHtml(courseTab) +
        '</td>' +
        '<td class="p-2">' +
        App.escapeHtml(sectionName) +
        '</td>' +
        '<td class="p-2">' +
        App.escapeHtml(lessonTitle) +
        '</td>' +
        '<td class="p-2">' +
        App.escapeHtml(preview) +
        (isTruncated
          ? ' <button type="button" class="lesson-full-btn text-xs text-blue-700 hover:underline">全文</button>'
          : '') +
        '</td>' +
        '<td class="p-2">' +
        (url
          ? '<a class="text-blue-600 underline" target="_blank" rel="noopener noreferrer" href="' +
            App.escapeHtml(url) +
            '">開く</a>'
          : '') +
        '</td>';
      const fullBtn = tr.querySelector('.lesson-full-btn');
      if (fullBtn) {
        fullBtn.addEventListener('click', function (ev) {
          ev.preventDefault();
          App.openCommentDetailDialog(r);
        });
      }
      body.appendChild(tr);
    });
  },

  initializeAttachments: async (email, password, generation) => {
    const userId=String((App.state.currentUser||{}).id||'');
    const current=()=>App.state.attachmentGeneration===generation && String((App.state.currentUser||{}).id||'')===userId;
    if(!current()||!userId)return;
    App.state.attachmentLoading=true;App.state.attachmentStatus='添付情報を読み込み中…';App.renderAttachmentStatus();
    try{
      const session=await App.retryRead(()=>App.apiClient('POST','/auth/attachment-session',App.authGatewayBase?{}:{email:email,password_hash:password}),current);
      if(!current())return;
      const token=String(session.token||'');if(!token)throw new Error('invalid_attachment_session');
      App.state.attachmentToken=token;
      const index={};
      for(const source of ['community','openchat']){
       let offset=0,complete=false;
       for(let page=0;page<201;page++){
        if(!current())return;
        const data=await App.retryRead(()=>App.attachmentRequest({operation:'index',source:source,offset:offset},token),current);
        if(!current())return;
        if(!Array.isArray(data.attachments))throw new Error('invalid_attachment_index');
        data.attachments.forEach(item=>{
          const key=source==='openchat' ? (item.source_log_id?'openchat:'+String(item.source_log_id):'') : String(item.comment_id||'');
          if(!key)return;if(!index[key])index[key]=[];index[key].push(item);
        });
        if(data.next_offset==null){
          App.state.attachmentIndex=index;App.state.attachmentStatus='';
          App.renderCommentTable();App.renderChatMessages();App.renderOpenchatTable();
          if(App.elements.commentDetailDialog&&App.elements.commentDetailDialog.open&&App.elements.commentDetailBody&&App.state.attachmentDetailCommentId)App.appendAttachmentLinks(App.elements.commentDetailBody,App.state.attachmentDetailCommentId,'','',App.state.attachmentDetailMeta);
          complete=true;break;
        }
        if(!Number.isInteger(data.next_offset)||data.next_offset<=offset)throw new Error('invalid_attachment_offset');
        offset=data.next_offset;
       }
       if(!complete)throw new Error('attachment_index_limit');
      }
    }catch(error){
      if(current())App.state.attachmentStatus=error&&[401,403].includes(error.httpStatus)?'添付の確認にはログインし直してください。':'添付の読み込みが中断しました。再取得できます。本文の閲覧は続けられます。';
    }finally{if(current()){App.state.attachmentLoading=false;App.renderAttachmentStatus();if(App.elements.commentTableBody)App.renderCommentTable();}}
  },

  attachmentRequest: async (body, token) => {
    const response=await fetch('https://mwubzgefkkjjbingrmqu.supabase.co/functions/v1/community-attachments',{
      method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+(token||App.state.attachmentToken||'')},body:JSON.stringify(body)
    });
    if(!response.ok){const error=new Error('attachment_request_failed');error.httpStatus=response.status;throw error;}
    return response.json();
  },

  attachmentDisplayName: (item, meta, seq) => {
    const name = String(item.original_name || '').trim();
    const type = String(item.content_type || item.mime_type || item.mime || '').toLowerCase();
    const kind = type.split('/')[0] || name.toLowerCase();
    const label = App.attachmentKindLabel(item);
    const prefix = App.attachmentNamePrefix(meta);
    if (!prefix) {
      if (name && !/^(image|video|audio|file)$/i.test(name)) return name;
      return ({ image: '画像', video: '動画', audio: '音声' }[kind] || '添付ファイル') + '（ファイル名未取得）';
    }
    // 「いつ_誰_中身」の形に揃える（保存しているファイル名は変えず、表示だけ）
    if (name && !App.isMeaninglessAttachmentName(name)) return prefix + '_' + name;
    const ext = (name.match(/\.([A-Za-z0-9]{1,5})$/) || [])[1] || ({ 'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'image/heic': 'heic', 'video/mp4': 'mp4', 'video/quicktime': 'mov', 'audio/mp4': 'm4a', 'audio/mpeg': 'mp3', 'application/pdf': 'pdf' }[type] || '');
    return prefix + '_' + label + (seq ? String(seq) : '') + (ext ? '.' + ext.toLowerCase() : '');
  },

  attachmentKindLabel: (item) => {
    const name = String(item.original_name || '').toLowerCase();
    const type = String(item.content_type || item.mime_type || item.mime || '').toLowerCase();
    const ext = (name.match(/\.([a-z0-9]{1,5})$/) || [])[1] || '';
    if (type === 'application/pdf' || ext === 'pdf') return 'PDF';
    if (/sheet|excel|csv/.test(type) || /^(xlsx?|csv)$/.test(ext)) return '表';
    if (/word/.test(type) || /^docx?$/.test(ext)) return '文書';
    if (/presentation|powerpoint/.test(type) || /^pptx?$/.test(ext)) return 'スライド';
    const kind = type.split('/')[0] || name;
    return { image: '画像', video: '動画', audio: '音声' }[kind] || (/^(jpe?g|png|webp|heic|gif)$/.test(ext) ? '画像' : /^(mp4|mov)$/.test(ext) ? '動画' : '添付');
  },

  // IMG_1234.jpg・S__6856725.jpg・英数字の長い記号・image など、人が見て意味のない名前
  isMeaninglessAttachmentName: (name) => {
    const base = String(name || '').trim().replace(/\.[A-Za-z0-9]{1,5}$/, '');
    if (!base) return true;
    return /^(image|video|audio|file|photo|movie|attachment)$/i.test(base) ||
      /^(IMG|DSC|DSCN|DCIM|PXL|MOV|VID|S_+|LINE_ALBUM|line_\d+)[_\-\s]*[0-9_\-\s]*$/i.test(base) ||
      /^[0-9a-f]{16,}$/i.test(base) || /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(base) ||
      /^[0-9_\-\s]+$/.test(base);
  },

  attachmentNamePrefix: (meta) => {
    if (!meta) return '';
    const d = App.referenceDateParts(meta.when);
    const date = d ? d.year + '-' + String(d.month).padStart(2, '0') + '-' + String(d.day).padStart(2, '0') : '';
    const parsed = App.parseWeStudyAuthorName(String(meta.who || ''));
    const who = String(parsed.authorName || parsed.raw || '').replace(/[\\/:*?"<>|\s　]+/g, '').slice(0, 30);
    return [date || '日付不明', who || '投稿者不明'].join('_');
  },

  attachmentMetaFromElement: (el) => {
    const when = el && el.getAttribute ? el.getAttribute('data-when') : '';
    const who = el && el.getAttribute ? el.getAttribute('data-who') : '';
    return when || who ? { when: when || '', who: who || '' } : null;
  },

  appendAttachmentLinks: (container, commentId, label, source, meta) => {
    const previous = container.querySelector('.community-attachment-links');
    if (previous) previous.remove();
    const isOpenchat=source==='openchat';
    const items = (App.state.attachmentIndex || {})[(isOpenchat?'openchat:':'')+String(commentId || '')] || [];
    if (!items.length) return;
    const wrapper = document.createElement('span');
    wrapper.className = 'community-attachment-links block mt-2 text-sm';
    const title = document.createElement('span');
    title.textContent = label || '添付資料：';
    wrapper.appendChild(title);
    const totals = {}, seen = {};
    const needsSeq = item => meta && (!String(item.original_name || '').trim() || App.isMeaninglessAttachmentName(item.original_name));
    items.forEach(item => { if (needsSeq(item)) { const k = App.attachmentKindLabel(item); totals[k] = (totals[k] || 0) + 1; } });
    items.forEach(function (item) {
      const kindKey = App.attachmentKindLabel(item);
      const seq = needsSeq(item) && totals[kindKey] > 1 ? (seen[kindKey] = (seen[kindKey] || 0) + 1) : 0;
      const link = document.createElement('a');
      link.href = '#attachment-' + String(item.id);
      link.className = 'block text-blue-700 hover:underline break-all';
      link.textContent = App.attachmentDisplayName(item, meta, seq);
      if (meta && item.original_name) link.title = '元のファイル名: ' + String(item.original_name);
      link.addEventListener('click', async function (event) {
        event.preventDefault();
        const generation = App.state.attachmentGeneration;
        const target = window.open('about:blank', '_blank');
        if (target) target.opener = null;
        try {
          const result = await App.attachmentRequest({ operation: 'open', source:isOpenchat?'openchat':'community', attachment_id: item.id });
          if (generation !== App.state.attachmentGeneration) throw new Error('ログイン状態が変わりました。開き直してください。');
          const url = new URL(result.url);
          if (url.origin !== 'https://mwubzgefkkjjbingrmqu.supabase.co' ||
              !url.pathname.startsWith('/storage/v1/object/sign/'+(isOpenchat?'openchat-attachments':'community-attachments')+'/')) throw new Error('添付リンクを確認できませんでした。');
          if (!target) throw new Error('ポップアップを許可して、もう一度リンクを押してください。');
          target.location.replace(url.href);
        } catch (error) {
          if (target) target.close();
          App.showToast(error.message || '添付ファイルを開けませんでした。', 'error');
        }
      });
      wrapper.appendChild(link);
    });
    container.appendChild(wrapper);
  },
  renderCommentTable: (opts) => {
    opts = opts || {};
    const body = App.elements.commentTableBody;
    const keywordRaw = String((App.elements.commentSearchInput && App.elements.commentSearchInput.value) || '').trim();
    const keyword = keywordRaw.toLowerCase();
    const exactFromOpts = String(opts.exactCommentId || '').trim();
    // 「DBで見る」または検索欄が数字のみかつ5桁以上 → comment_id 完全一致（4桁は会員番号検索）
    const exactCommentId =
      exactFromOpts ||
      (/^\d{5,}$/.test(keywordRaw) ? keywordRaw : '');
    const categoryFilter =
      (App.elements.commentCategoryFilter && App.elements.commentCategoryFilter.value) || '';
    const dateFilter = (App.elements.commentDateFilter && App.elements.commentDateFilter.value) || '';
    const commentsLoading = !!(App.state.referenceLoads && App.state.referenceLoads.comments);
    const attachmentsOnly = !!(App.elements.commentAttachmentsOnly && App.elements.commentAttachmentsOnly.checked);
    body.innerHTML = '';

    const communityRows = (App.state.comments || []).filter(function (row) {
      return !App.isLessonCommentRow(row);
    });
    const filtered = communityRows.filter(function (row) {
      const cid = String(App.commentField(row, 'comment_id') || '').trim();
      const attachments = (App.state.attachmentIndex || {})[cid] || [];
      const forumCategory =
        String(App.commentField(row, 'forum_category') || '').trim() || '未分類';
      const hasDate = App.hasPostedAtValue(row);
      const authorParsed = App.parseWeStudyAuthorName(App.commentField(row, 'author_name'));
      let hitKeyword = true;
      if (exactCommentId) {
        hitKeyword = cid === exactCommentId;
      } else if (keyword) {
        const t1 = String(App.commentField(row, 'content')).toLowerCase();
        const t2 = String(authorParsed.raw || '').toLowerCase();
        const t2m = String(authorParsed.memberNo || '').toLowerCase();
        const t2n = String(authorParsed.authorName || '').toLowerCase();
        const t4 = cid.toLowerCase();
        const t5 = forumCategory.toLowerCase();
        hitKeyword =
          t1.indexOf(keyword) !== -1 ||
          t2.indexOf(keyword) !== -1 ||
          t2m.indexOf(keyword) !== -1 ||
          t2n.indexOf(keyword) !== -1 ||
          t4.indexOf(keyword) !== -1 ||
          t5.indexOf(keyword) !== -1 ||
          attachments.some(item => String(item.original_name || '').toLowerCase().includes(keyword));
      }
      const hitCategory = !categoryFilter || forumCategory === categoryFilter;
      const hitDate =
        !dateFilter ||
        (dateFilter === 'hasDate' && hasDate) ||
        (dateFilter === 'missingDate' && !hasDate);
      return hitKeyword && hitCategory && hitDate && (!attachmentsOnly || attachments.length > 0);
    });

    const pageSize = 100;
    const requestedOffset = Number.isInteger(opts.offset) && opts.offset >= 0 ? opts.offset : 0;
    const offset = Math.min(requestedOffset, Math.max(0, Math.floor((filtered.length - 1) / pageSize) * pageSize));
    const visibleRows = filtered.slice(offset, offset + pageSize);
    const totalCount = communityRows.length;
    const missingDateCount = communityRows.reduce(function (n, row) {
      return n + (App.hasPostedAtValue(row) ? 0 : 1);
    }, 0);
    const unknownYearCount=communityRows.reduce((n,row)=>n+(!App.hasPostedAtValue(row)&&!Number(((App.state.referenceComments||{})[String(App.commentField(row,'comment_id'))]||{}).inferred_year)?1:0),0);
    if (App.elements.commentListMeta) {
      App.elements.commentListMeta.textContent =
        '表示 ' +
        (filtered.length ? (offset + 1) + '〜' + (offset + visibleRows.length) : '0') +
        ' / 検索結果 ' + filtered.length + ' / 全 ' +
        totalCount +
        ' 件（月日不明 ' +
        missingDateCount +
        ' 件・年も不明 ' + unknownYearCount + ' 件）' +
        (commentsLoading ? '・コメント一覧を取得中（件数は暫定）' : '') +
        (attachmentsOnly && App.state.attachmentLoading ? '・添付情報を確認中（件数は暫定）' :
          attachmentsOnly && App.state.attachmentStatus ? '・添付情報が未確認のため一部のみ表示。上部から再取得してください。' : '');
      if (filtered.length > pageSize) {
        const controls = document.createElement('span');
        controls.className = 'inline-flex gap-3 ml-3';
        [['前の100件', offset - pageSize], ['次の100件', offset + pageSize]].forEach(function (page) {
          const button = document.createElement('button');
          button.type = 'button'; button.textContent = page[0];
          button.className = 'text-blue-700 underline disabled:text-slate-400';
          button.disabled = page[1] < 0 || page[1] >= filtered.length;
          button.addEventListener('click', function () { App.renderCommentTable({ offset: page[1] }); });
          controls.appendChild(button);
        });
        App.elements.commentListMeta.appendChild(controls);
      }
    }

    if (filtered.length === 0) {
      body.innerHTML = '<tr><td colspan="6" class="p-3 text-slate-500">' +
        (commentsLoading ? 'コメント一覧を取得中…' : attachmentsOnly && (App.state.attachmentLoading || App.state.attachmentStatus) ? '添付情報の確認が完了していません。' : '該当データがありません') + '</td></tr>';
      return;
    }

    visibleRows.forEach(function (r) {
      const tr = document.createElement('tr');
      tr.className = 'border-t';
      const postedAt = String(App.commentField(r, 'posted_at') || '').trim();
      const inferredYear=Number(((App.state.referenceComments||{})[String(App.commentField(r,'comment_id'))]||{}).inferred_year)||null;
      const postedAtLabel = App.formatOpenchatDateTime(postedAt) || (inferredYear?inferredYear+'年（IDから推定・月日不明）':'（日時なし）');
      const forumCategory =
        String(App.commentField(r, 'forum_category') || '').trim() || '未分類';
      const authorParsed = App.parseWeStudyAuthorName(App.commentField(r, 'author_name'));
      const fullContent = String(App.commentField(r, 'content') || '');
      const previewLen = 180;
      const isTruncated = fullContent.length > previewLen;
      const preview = isTruncated ? fullContent.slice(0, previewLen) : fullContent;
      const contentTd = document.createElement('td');
      contentTd.className = 'p-2';
      contentTd.appendChild(document.createTextNode(preview));
      if (isTruncated) {
        const note = document.createElement('span');
        note.className = 'text-slate-400';
        note.textContent = '…（全文 ' + fullContent.length + ' 文字）';
        contentTd.appendChild(note);
      }
      const openBtn = document.createElement('button');
      openBtn.type = 'button';
      openBtn.className = 'ml-2 text-xs text-blue-700 hover:underline whitespace-nowrap';
      openBtn.textContent = '全文';
      openBtn.addEventListener('click', function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        App.openCommentDetailDialog(r);
      });
      contentTd.appendChild(openBtn);
      App.appendAttachmentLinks(contentTd, App.commentField(r, 'comment_id'), '', '', { when: App.commentField(r, 'posted_at') || '', who: App.commentField(r, 'author_name') || '' });

      tr.innerHTML =
        '<td class="p-2 whitespace-nowrap">' +
        App.escapeHtml(String(App.commentField(r, 'comment_id') || '')) +
        '</td>' +
        '<td class="p-2 whitespace-nowrap">' +
        App.escapeHtml(forumCategory) +
        '</td>' +
        '<td class="p-2">' +
        App.escapeHtml(postedAtLabel) +
        (postedAt||inferredYear ? '' : ' <span class="text-[10px] text-amber-700">missing</span>') +
        '</td>' +
        '<td class="p-2 whitespace-nowrap font-mono text-xs">' +
        App.escapeHtml(authorParsed.memberNo || '—') +
        '</td>' +
        '<td class="p-2">' +
        App.escapeHtml(authorParsed.authorName || (authorParsed.memberNo ? '' : authorParsed.raw) || '—') +
        '</td>';
      tr.appendChild(contentTd);
      body.appendChild(tr);
    });
  },

  openCommentDetailDialog: (row) => {
    if (!App.elements.commentDetailDialog) return;
    const cid = String(App.commentField(row, 'comment_id') || '').trim();
    const authorParsed = App.parseWeStudyAuthorName(App.commentField(row, 'author_name'));
    const postedAt = String(App.commentField(row, 'posted_at') || '').trim();
    const category =
      String(App.commentField(row, 'forum_category') || '').trim() || '未分類';
    const content = String(App.commentField(row, 'content') || '');
    if (App.elements.commentDetailTitle) {
      App.elements.commentDetailTitle.textContent = 'コメント全文' + (cid ? '（ID ' + cid + '）' : '');
    }
    if (App.elements.commentDetailMeta) {
      App.elements.commentDetailMeta.textContent =
        '会員番号: ' +
        (authorParsed.memberNo || '—') +
        '\n投稿者: ' +
        (authorParsed.authorName || authorParsed.raw || '—') +
        '\n日時: ' +
        (App.formatOpenchatDateTime(postedAt) || '—') +
        '\n分類: ' +
        category +
        '\n文字数: ' +
        content.length;
    }
    if (App.elements.commentDetailBody) {
      App.elements.commentDetailBody.textContent = content;
      App.state.attachmentDetailCommentId = cid;
      App.state.attachmentDetailMeta = { when: postedAt, who: App.commentField(row, 'author_name') || '' };
      App.appendAttachmentLinks(App.elements.commentDetailBody, cid, '', '', App.state.attachmentDetailMeta);
    }
    if (typeof App.elements.commentDetailDialog.showModal === 'function') {
      App.elements.commentDetailDialog.showModal();
    } else {
      App.elements.commentDetailDialog.setAttribute('open', 'open');
    }
  },

  closeCommentDetailDialog: () => {
    if (!App.elements.commentDetailDialog) return;
    if (typeof App.elements.commentDetailDialog.close === 'function') {
      App.elements.commentDetailDialog.close();
    } else {
      App.elements.commentDetailDialog.removeAttribute('open');
    }
  },

  renderPendingUsers: () => {
    const body = App.elements.pendingUsersTableBody;
    body.innerHTML = '';
    if (App.elements.pendingUsersSelectAll) {
      App.elements.pendingUsersSelectAll.checked = false;
    }
    if (!App.isStaffAdmin()) {
      App.updateBulkApproveButtonState();
      return;
    }

    if (App.state.pendingUsers.length === 0) {
      body.innerHTML = '<tr><td colspan="8" class="p-3 text-slate-500">承認待ちユーザはいません</td></tr>';
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
        '<td class="p-2">' + App.escapeHtml(u.name || '') + '</td>' +
        '<td class="p-2">' + App.escapeHtml(u.email || '') + '</td>' +
        '<td class="p-2">' + App.escapeHtml(u.member_no || '') + '</td>' +
        '<td class="p-2">' + App.escapeHtml(u.prefecture || '') + '</td>' +
        '<td class="p-2">' + App.escapeHtml(u.status || '') + App.rosterBadge(u.id) + '</td>' +
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

  rosterBadge: (id) => {
    const b = App.rosterBadges[(App.state.rosterMatches || {})[id]];
    return b ? ' <span class="inline-block mt-1 px-2 py-0.5 rounded text-xs ' + b[1] + '">' + App.escapeHtml(b[0]) + '</span>' : '';
  },
  updateBulkApproveButtonState: () => {
    const btn = App.elements.bulkApprovePendingUsersBtn;
    if (!btn) return;
    const selected = App.getSelectedPendingUsers();
    btn.disabled = selected.length === 0;
    btn.textContent =
      selected.length > 0
        ? '選択したユーザを一括承認（' + selected.length + '件）'
        : '選択したユーザを一括承認';
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

  handleFastSummaryClick: (event) => {
    if (event) event.preventDefault();
    if (!App.state.pendingQuestionText) return;
    if(App.authGatewayBase&&App.state.pendingAnswerRequest){App.showToast('現在の回答を作成しています。完了までお待ちください。','info');return;}
    App.state.preferFastSummary = true;
    if (App.state.sendAbortController) {
      try {
        App.state.sendAbortController.abort();
      } catch (e) {
        /* ignore */
      }
    }
  },

  messageEndpointForMode: (sessionId, fast) => {
    const base = '/chat-sessions/' + sessionId;
    // 意味検索は Edge 直呼び（設定は /semantic-search-config）。messages-semantic は使わない
    return base + (fast ? '/messages-fast' : '/messages');
  },

  resolveSemanticConfig: async () => {
    let url = String(App.semanticEdgeUrl || '').trim();
    let secret = String(App._semanticSecret || '').trim();
    if (secret && url.indexOf('http') === 0) {
      return { url: url, secret: secret };
    }
    const cfg = await App.apiClient('POST', '/semantic-search-config', {});
    const cfgUrl = String((cfg && cfg.url) || '').trim();
    const cfgSecret = String((cfg && cfg.secret) || '').trim();
    if (cfgUrl.indexOf('http') === 0) {
      url = cfgUrl;
      App.semanticEdgeUrl = cfgUrl;
    }
    if (cfgSecret) {
      secret = cfgSecret;
      App._semanticSecret = cfgSecret;
    }
    if (!url || url.indexOf('http') !== 0 || !secret) {
      throw new Error(
        '意味検索の接続情報を取得できませんでした。再読み込み後に再試行してください'
      );
    }
    return { url: url, secret: secret };
  },

  // Phase 13: 通常検索の利用ログ（意味検索は Edge 側でも記録）
  logQaSearchEvent: async (payload) => {
    try {
      const cfg = await App.resolveSemanticConfig();
      const logUrl = String(cfg.url || '').replace(/semantic-search\/?$/, 'qa-search-log');
      if (!logUrl || logUrl === cfg.url) return;
      await fetch(logUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Semantic-Shared-Secret': cfg.secret
        },
        body: JSON.stringify({
          search_mode: payload.search_mode || 'normal',
          query_text: String(payload.query || '').slice(0, 2000),
          session_id: App.state.currentSessionId || null,
          user_id: (App.state.currentUser && App.state.currentUser.id) || null,
          comment_hit_count: payload.comment_hit_count,
          chunk_hit_count: payload.chunk_hit_count,
          used_sources: payload.used_sources || null,
          meta: payload.meta || {},
          result_status: payload.result_status || 'ok',
          error_message: payload.error_message || null,
          hits: payload.hits,
          term_count: payload.term_count,
          has_or: payload.has_or
        })
      });
    } catch (e) {
      /* analytics must not break chat */
    }
  },

  // (2) 判断ログの補足: 「本文を見る」や元ページのリンクを押したら、参考にした根拠として記録する。
  // 同じ画面で同じ根拠は1回だけ送る。送れなくても画面の動きは変えない。2026-11-10
  bindSourceClicks: (panel) => {
    if (!panel || panel.dataset.srcBound) return;
    panel.dataset.srcBound = '1';
    panel.addEventListener('click', function (event) {
      const el = event.target && event.target.closest ? event.target.closest('a,button') : null;
      if (!el || !panel.contains(el)) return;
      const href = String(el.getAttribute('href') || '');
      if (href.charAt(0) === '#') return; // 一覧の中を移動するだけのリンクは数えない
      const li = el.closest('[data-src-kind]');
      if (!li) return;
      void App.logSourceClick(panel.getAttribute('data-message-id') || '', {
        kind: li.getAttribute('data-src-kind') || '', source_key: li.getAttribute('data-src-key') || '',
        title: li.getAttribute('data-src-title') || '', label: li.getAttribute('data-src-label') || '',
        action: el.classList.contains('citation-db-link') ? 'open_text' : 'open_link'
      });
    });
  },

  logSourceClick: async (msgId, s) => {
    const chatId = App.state.currentSessionId;
    if (!chatId || !msgId || !s.kind || !s.source_key || !App.featureOn('answer_feedback')) return;
    const seen = App.state.sourceClicksSent || (App.state.sourceClicksSent = {});
    const key = chatId + '/' + msgId + '/' + s.kind + '/' + s.source_key;
    if (seen[key]) return;
    seen[key] = true;
    try {
      await App.apiClient('POST', '/answer-source-click', Object.assign({ chat_id: String(chatId), message_id: String(msgId) }, s));
    } catch (e) {
      delete seen[key];
    }
  },

  // 改善履歴（11/11）。会員の声を受けて直したことを新しい順に出す。スイッチ change_log が見える人だけ。
  loadChangeLog: async () => {
    const list = document.getElementById('changeLogList');
    if (!list) return;
    if (!App.featureOn('change_log')) { list.innerHTML = ''; return; }
    list.innerHTML = '<p class="text-sm text-slate-500">読み込み中…</p>';
    try {
      const r = await App.apiClient('GET', '/change-log');
      const rows = (r && Array.isArray(r.entries)) ? r.entries : [];
      list.innerHTML = rows.length ? rows.map(function (x) {
        return '<div class="bg-white rounded border p-4"><div class="text-xs text-slate-500">' + App.escapeHtml(String(x.released_on || '').replace(/-/g, '/')) + '</div>' +
          '<div class="font-semibold">' + App.escapeHtml(x.title || '') + '</div>' +
          (x.body ? '<p class="text-sm text-slate-700 mt-1 whitespace-pre-line">' + App.escapeHtml(x.body) + '</p>' : '') +
          (x.trigger ? '<p class="text-xs text-slate-500 mt-2">きっかけ：' + App.escapeHtml(x.trigger) + '</p>' : '') + '</div>';
      }).join('') : '<p class="text-sm text-slate-500">まだ履歴はありません。</p>';
    } catch (e) {
      list.innerHTML = '<p class="text-sm text-red-600">取得できませんでした: ' + App.escapeHtml((e && e.message) || String(e)) + '</p>';
    }
  },

  // キーワード検索（全データ）（11/11 松野さん）。年配の方も使う前提で、説明と例を画面に出し、文字は大きめ。コミュニティ・講座ページ・動画文字起こし・LINEオプチャを
  // 1つの入力欄から同時にキーワードで探し、データソースごとに並べる。AI は呼ばない（費用は増えない）。
  // スイッチ keyword_all が見える人だけ。中身は各一覧と同じデータ（会員が一覧で見られるもの）だけ。
  allSearchPerGroup: 20,
  allSearchMaxPerGroup: 200,
  allSearchNormalize: (v) => {
    const t = String(v == null ? '' : v);
    return (typeof t.normalize === 'function' ? t.normalize('NFKC') : t).toLowerCase();
  },
  // 書き方: 空白（全角も）で区切る → すべての語を含むもの（AND）。
  // 「または」「OR」「|」で区切る → どれかを含むもの（OR）。例「敷金 または 保証金」「原状回復 費用 または 退去 費用」。
  allSearchOrPattern: /\s+(?:または|or)\s+|\s*\|\s*/,
  allSearchQuery: (q) => {
    return App.allSearchNormalize(q).trim().split(App.allSearchOrPattern).map(function (part) {
      const seen = {};
      return part.split(/\s+/).map(function (x) { return x.trim(); }).filter(function (x) {
        if (!x || x === 'または' || x === 'or' || seen[x]) return false;
        seen[x] = true;
        return true;
      }).slice(0, 8);
    }).filter(function (g) { return g.length; }).slice(0, 5);
  },
  // 印を付ける語（全部の語を1回ずつ）
  allSearchTerms: (q) => {
    const seen = {};
    const out = [];
    App.allSearchQuery(q).forEach(function (g) { g.forEach(function (t) { if (!seen[t]) { seen[t] = true; out.push(t); } }); });
    return out;
  },
  // terms は語の並び（AND）か、語の並びの並び（OR でつないだ AND）
  allSearchMatches: (parts, terms) => {
    if (!terms || !terms.length) return false;
    const hay = App.allSearchNormalize((parts || []).map(function (x) { return x == null ? '' : String(x); }).join(' \n '));
    const groups = Array.isArray(terms[0]) ? terms : [terms];
    return groups.some(function (g) { return g.length && g.every(function (t) { return hay.indexOf(t) !== -1; }); });
  },
  // 最初に当たった語のまわりを切り出し、当たった語に印を付ける（HTML は全部エスケープしてから）。
  allSearchSnippetHtml: (text, terms, width) => {
    const raw = String(text == null ? '' : text).replace(/\s+/g, ' ').trim();
    const w = width || 140;
    const norm = App.allSearchNormalize(raw);
    // NFKC で長さが変わる文字があると位置がずれるので、ずれないときだけ位置を使う。
    let pos = -1;
    if (norm.length === raw.length) {
      (terms || []).forEach(function (t) {
        const i = norm.indexOf(t);
        if (i !== -1 && (pos === -1 || i < pos)) pos = i;
      });
    }
    let start = pos > 40 ? pos - 40 : 0;
    let piece = raw.slice(start, start + w);
    const head = start > 0 ? '…' : '';
    const tail = start + w < raw.length ? '…' : '';
    const esc = App.escapeHtml;
    if (norm.length !== raw.length || !terms || !terms.length) return esc(head + piece + tail);
    const pnorm = norm.slice(start, start + w);
    const mark = new Array(piece.length).fill(false);
    terms.forEach(function (t) {
      let i = pnorm.indexOf(t);
      while (i !== -1 && t.length) {
        for (let k = i; k < i + t.length && k < mark.length; k++) mark[k] = true;
        i = pnorm.indexOf(t, i + t.length);
      }
    });
    let out = '', buf = '', on = false;
    const flush = function () {
      if (!buf) return;
      out += on ? '<mark class="bg-yellow-200 rounded px-0.5">' + esc(buf) + '</mark>' : esc(buf);
      buf = '';
    };
    for (let k = 0; k < piece.length; k++) {
      if (mark[k] !== on) { flush(); on = mark[k]; }
      buf += piece[k];
    }
    flush();
    return esc(head) + out + esc(tail);
  },
  allSearchLocalGroups: (terms) => {
    const limit = App.allSearchMaxPerGroup;
    const pick = function (rows, toParts) {
      const hits = [];
      let total = 0;
      for (const row of rows) {
        if (!App.allSearchMatches(toParts(row), terms)) continue;
        total++;
        if (hits.length < limit) hits.push(row);
      }
      return { rows: hits, total: total };
    };
    const comments = pick(App.communityCommentRows(), function (row) {
      const a = App.parseWeStudyAuthorName(App.commentField(row, 'author_name'));
      return [App.commentField(row, 'content'), a.raw, a.authorName, App.commentField(row, 'forum_category')];
    });
    const lessons = pick(App.lessonCommentRows(), function (row) {
      return [App.commentField(row, 'course_tab'), App.commentField(row, 'section_name'),
        App.commentField(row, 'lesson_title') || App.commentField(row, 'topic_title'), App.commentField(row, 'content')];
    });
    const sources = App.state.knowledgeSources || {};
    const knowledge = pick(App.state.knowledgeChunks || [], function (ch) {
      const src = sources[ch.source_key] || {};
      const info = App.knowledgeReferenceInfo(src);
      return [ch.content, info.title, info.course, info.section];
    });
    return { comments: comments, lessons: lessons, knowledge: knowledge };
  },
  // LINEオプチャは一覧と同じくサーバーで探す（全件を画面に持たないため）。サーバーには一番長い語を渡し、
  // 残りの語は戻ってきた中で絞る。サーバーは新しい順に最大200件までなので、件数は「200件以上」と出す。
  allSearchOpenchat: async (query) => {
    const cfg = await App.resolveSemanticConfig();
    const lists = await Promise.all(query.map(function (g) { return App.allSearchOpenchatOne(cfg, g.slice().sort(function (a, b) { return b.length - a.length; })[0]); }));
    const seen = {};
    const rows = [];
    let capped = false;
    lists.forEach(function (list) {
      if (list.length >= 200) capped = true;
      list.forEach(function (r) {
        const id = String(r.id || '');
        if (seen[id] || !App.allSearchMatches([r.content, r.chat_title, r.sender_name, r.thread_title], query)) return;
        seen[id] = true;
        rows.push(r);
      });
    });
    rows.sort(function (a, b) { return String(b.posted_at || '').localeCompare(String(a.posted_at || '')); });
    return { rows: rows, total: rows.length, capped: capped };
  },
  allSearchOpenchatOne: async (cfg, first) => {
    const response = await fetch(cfg.url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Semantic-Shared-Secret': cfg.secret },
      body: JSON.stringify({
        list_openchat: true,
        query: first,
        openchat_limit: 40,
        session_id: App.state.currentSessionId || undefined,
        user_id: (App.state.currentUser && App.state.currentUser.id) || undefined
      })
    });
    const text = await response.text();
    let data = {};
    try { data = text ? JSON.parse(text) : {}; } catch (e) { data = {}; }
    if (!response.ok) throw new Error(data.errorMessage || data.message || data.error || 'LINEオプチャの検索に失敗しました');
    return App.normalizeRelatedList(data.relatedOpenchat || []);
  },
  runAllSearch: async () => {
    if (!App.featureOn('keyword_all')) return;
    const input = App.elements.allSearchInput;
    const meta = App.elements.allSearchMeta;
    const box = App.elements.allSearchResults;
    if (!input || !box) return;
    const q = String(input.value || '').trim();
    const query = App.allSearchQuery(q);
    const terms = App.allSearchTerms(q);
    if (!query.length) {
      if (meta) meta.textContent = '調べたい言葉を入れてから「検索」を押してください。';
      box.innerHTML = '';
      return;
    }
    const seq = (App.state.allSearchSeq || 0) + 1;
    App.state.allSearchSeq = seq;
    const current = function () { return App.state.allSearchSeq === seq; };
    if (meta) meta.textContent = '';
    box.innerHTML = '';
    App.state.allSearchOcDone = false;
    App.state.allSearchStartedAt = Date.now();
    App.state.allSearchResult = null;
    App.state.allSearchPendingTerms = terms;
    App.startAllSearchProgress(seq);
    const ocTask = App.allSearchOpenchat(query).then(function (r) { return r; }, function (e) { return { error: (e && e.message) || String(e) }; })
      .then(function (r) { if (current()) App.state.allSearchOcDone = true; return r; });
    const local = await Promise.all([App.ensureReferenceData('comments'), App.ensureReferenceData('knowledge')])
      .then(function () { return App.allSearchLocalGroups(query); }, function (e) { return { error: (e && e.message) || String(e) }; });
    if (!current()) return;
    App.stopAllSearchProgress();
    const groups = local.error ? { comments: local, lessons: local, knowledge: local } : local;
    App.state.allSearchResult = { terms: terms, query: query, groups: groups, openchat: null, expanded: {} };
    App.renderAllSearchResults();
    const oc = await ocTask;
    if (!current()) return;
    App.state.allSearchResult.openchat = oc;
    App.renderAllSearchResults();
    void App.logKeywordSearch(query, terms, groups, oc);
  },
  // 運営分析で「チャットの質問」と並べて比べるため、キーワード検索も1回ずつ記録する（11/12 松野さん）。
  // 送る言葉は画面と同じ正規化の後（同じ言葉は同じ行にまとまる）。送れなくても検索の動きは変えない。
  logKeywordSearch: async (query, terms, groups, oc) => {
    try {
      const cnt = function (g) { return g && !g.error ? Number(g.total != null ? g.total : (g.rows || []).length) || 0 : 0; };
      const hits = { comments: cnt(groups.comments), openchat: cnt(oc), lessons: cnt(groups.lessons), knowledge: cnt(groups.knowledge) };
      const failedParts = (groups.comments && groups.comments.error ? 1 : 0) + (oc && oc.error ? 1 : 0);
      await App.logQaSearchEvent({
        search_mode: 'keyword',
        query: query.map(function (g) { return g.join(' '); }).join(' または ').slice(0, 500),
        meta: {},
        result_status: failedParts >= 2 ? 'error' : failedParts ? 'partial' : 'ok',
        hits: hits,
        term_count: (terms || []).length,
        has_or: query.length > 1
      });
    } catch (e) { /* 記録の失敗は画面に出さない */ }
  },
  // 検索中の「進んでいます」表示（11/11 松野さん）。回答待ちと同じ見た目（search-motion）で、
  // こちらは実際の進み具合（読み込んだ件数・区分ごとの済み）をそのまま出す。初回だけ一覧データの読み込みで時間がかかる。
  allSearchProgressState: () => {
    const ready = App.state.referenceReady || {};
    let est = 22000;
    try { const v = Number(localStorage.getItem('qa_comments_total')); if (v > 0) est = v; } catch (e) { /* ignore */ }
    const loaded = ready.comments ? est : Math.min(est, Number(App.state.commentsLoadedCount || 0));
    const steps = [
      { icon: 'fa-solid fa-comments', done: !!ready.comments,
        label: ready.comments ? 'WeStudy コミュニティコメント・講座ページ説明文を読み込みました' : 'WeStudy コミュニティコメント・講座ページ説明文を読み込んでいます',
        detail: ready.comments ? '' : (loaded ? loaded.toLocaleString('ja-JP') + ' / 約' + est.toLocaleString('ja-JP') + '件' : '') },
      { icon: 'fa-solid fa-circle-play', done: !!ready.knowledge,
        label: ready.knowledge ? 'WeStudy 動画文字起こしを読み込みました' : 'WeStudy 動画文字起こしを読み込んでいます', detail: '' },
      { icon: 'fa-brands fa-line', done: !!App.state.allSearchOcDone,
        label: App.state.allSearchOcDone ? 'LINEオプチャを探しました' : 'LINEオプチャを探しています', detail: '' },
      { icon: 'fa-solid fa-magnifying-glass', done: false, label: 'キーワードに合うものを選んでいます', detail: '' }
    ];
    const pct = Math.round(60 * (loaded / est) + (ready.knowledge ? 20 : 0) + (App.state.allSearchOcDone ? 15 : 0));
    let active = steps.findIndex(function (x) { return !x.done; });
    if (active < 0) active = steps.length - 1;
    return { steps: steps, pct: Math.min(97, pct), active: active, firstLoad: !ready.comments };
  },
  renderAllSearchProgress: () => {
    const box = App.elements.allSearchResults;
    if (!box) return;
    const st = App.allSearchProgressState();
    const sec = Math.floor((Date.now() - (App.state.allSearchStartedAt || Date.now())) / 1000);
    const words = st.pct < 30 ? '探し始めました' : st.pct < 60 ? '半分ほど進みました' : st.pct < 90 ? 'もうすぐ結果が出ます' : 'まもなく表示します';
    let card = document.getElementById('allSearchWorkingCard');
    if (!card) {
      box.innerHTML = '<div id="allSearchWorkingCard" class="search-motion-wrap" role="status" aria-live="polite"><div class="search-motion">' +
        '<div class="search-motion-bar"><span></span><span></span><span></span><b>全データからキーワードを探しています</b></div>' +
        '<div class="search-motion-body">' +
          '<div class="search-motion-scan" aria-hidden="true"><div class="search-motion-lines"><i></i><i></i><i></i><i></i></div><div class="search-motion-glass"><i class="fa-solid fa-magnifying-glass"></i></div></div>' +
          '<ol class="search-motion-steps">' + st.steps.map(function (x, i) { return '<li data-step="' + i + '"><i class="' + x.icon + '" aria-hidden="true"></i><span data-label></span><small data-detail class="ml-auto text-xs whitespace-nowrap"></small></li>'; }).join('') + '</ol>' +
          '<div class="search-motion-progress" aria-hidden="true"><div data-progress></div></div>' +
          '<div class="search-motion-meta"><span data-remain></span><span data-elapsed></span></div>' +
          '<p data-first class="mt-2 text-sm text-slate-500"></p>' +
        '</div>' + App.allSearchCoursesHtml() + '</div></div>';
      card = document.getElementById('allSearchWorkingCard');
    }
    card.querySelectorAll('[data-step]').forEach(function (li) {
      const i = Number(li.getAttribute('data-step'));
      const x = st.steps[i];
      li.classList.toggle('is-done', x.done);
      li.classList.toggle('is-active', !x.done && i === st.active);
      li.querySelector('[data-label]').textContent = x.label;
      li.querySelector('[data-detail]').textContent = x.detail;
    });
    const bar = card.querySelector('[data-progress]'); if (bar) bar.style.width = st.pct + '%';
    const r = card.querySelector('[data-remain]'); if (r) r.textContent = words;
    const el = card.querySelector('[data-elapsed]'); if (el) el.textContent = '経過 ' + (sec >= 60 ? Math.floor(sec / 60) + '分' : '') + (sec % 60) + '秒';
    const f = card.querySelector('[data-first]'); if (f) f.textContent = st.firstLoad ? 'はじめての検索では、全データの読み込みに少し時間がかかります。2回目からはすぐに結果が出ます。' : '';
  },
  // おすすめ講座（11/11 松野さん「Q&Aチャットと同じく」）。回答待ちと同じ選び方（answerWaitCourses）で、検索の言葉から最大3件。
  allSearchCoursesHtml: () => {
    const res = App.state.allSearchResult;
    const terms = res ? res.terms : (App.state.allSearchPendingTerms || []);
    const list = App.answerWaitCourses((terms || []).join(''));
    if (!list.length) return '';
    const esc = App.escapeHtml;
    return '<div class="search-motion-courses"><div class="search-motion-courses-title"><i class="fa-solid fa-circle-play" aria-hidden="true"></i> 関連しそうな講座</div><ul>' +
      list.map(function (r) { return '<li><a href="' + esc(r.url) + '" target="_blank" rel="noopener">' + esc(r.title) + '</a><span>' + esc(r.course.replace(/^神大家/, '')) + '</span></li>'; }).join('') + '</ul></div>';
  },
  startAllSearchProgress: (seq) => {
    App.stopAllSearchProgress();
    App.renderAllSearchProgress();
    App.state.allSearchProgressTimer = window.setInterval(function () {
      if (App.state.allSearchSeq !== seq) { App.stopAllSearchProgress(); return; }
      App.renderAllSearchProgress();
    }, 400);
  },
  stopAllSearchProgress: () => {
    if (App.state.allSearchProgressTimer) window.clearInterval(App.state.allSearchProgressTimer);
    App.state.allSearchProgressTimer = null;
  },
  allSearchGroupDefs: [
    // 並びと名前は松野さんの指定（11/11）
    { key: 'comments', label: 'WeStudy コミュニティコメント', screen: 'comments' },
    { key: 'openchat', label: 'LINEオプチャ', screen: 'openchat' },
    { key: 'lessons', label: '講座ページ説明文', screen: 'lessons' },
    { key: 'knowledge', label: 'WeStudy 動画文字起こし', screen: 'knowledge' }
  ],
  allSearchItemHtml: (kind, row, terms) => {
    const esc = App.escapeHtml;
    let head = '', body = '', attrs = '';
    if (kind === 'comments') {
      const cid = String(App.commentField(row, 'comment_id') || '').trim();
      const a = App.parseWeStudyAuthorName(App.commentField(row, 'author_name'));
      const d = App.referenceDateParts(App.commentField(row, 'posted_at'));
      head = [d ? d.label : '', a.authorName || a.raw || '', String(App.commentField(row, 'forum_category') || '').trim()].filter(Boolean).join(' ・ ');
      body = App.commentField(row, 'content');
      attrs = 'data-kind="comment" data-id="' + esc(cid) + '"';
    } else if (kind === 'lessons') {
      const cid = String(App.commentField(row, 'comment_id') || '').trim();
      head = [App.commentField(row, 'course_tab'), App.commentField(row, 'section_name'),
        App.commentField(row, 'lesson_title') || App.commentField(row, 'topic_title')].map(function (x) { return String(x || '').trim(); }).filter(Boolean).join(' ＞ ');
      body = App.commentField(row, 'content');
      attrs = 'data-kind="lesson" data-id="' + esc(cid) + '"';
    } else if (kind === 'knowledge') {
      const src = (App.state.knowledgeSources || {})[row.source_key] || {};
      const info = App.knowledgeReferenceInfo(src);
      head = [info.course, info.title, App.formatMmSs(row.start_sec != null ? Number(row.start_sec) : 0) + '〜'].filter(Boolean).join(' ＞ ');
      body = row.content;
      attrs = 'data-kind="video_chunk" data-id="' + esc(String(row.chunk_key || '')) + '"';
    } else {
      const when = String(row.posted_at || row.postedAt || row.post_date || row.postDate || '').trim();
      head = [row.chat_title || row.chatTitle, App.formatOpenchatDateTime(when), row.sender_name || row.senderName].map(function (x) { return String(x || '').trim(); }).filter(Boolean).join(' ・ ');
      body = App.cleanOpenchatDisplayText(row.content);
      attrs = 'data-kind="openchat" data-id="' + esc(String(row.id || '')) + '"';
    }
    return '<li><button type="button" class="all-search-item w-full text-left px-3 py-3 hover:bg-blue-50 border-t" ' + attrs + '>' +
      '<div class="text-sm text-slate-600">' + esc(head) + '</div>' +
      '<div class="text-base leading-relaxed text-slate-900">' + App.allSearchSnippetHtml(body, terms) + '</div></button></li>';
  },
  renderAllSearchResults: () => {
    const res = App.state.allSearchResult;
    const box = App.elements.allSearchResults;
    if (!res || !box) return;
    const esc = App.escapeHtml;
    let sum = 0;
    const summary = [];
    const parts = App.allSearchGroupDefs.map(function (def) {
      const g = def.key === 'openchat' ? res.openchat : res.groups[def.key];
      let count = '', list = '';
      if (!g) {
        count = '探しています…';
      } else if (g.error) {
        count = '取得できませんでした';
        list = '<p class="text-sm text-red-600 p-2">' + esc(g.error) + '</p>';
      } else {
        sum += g.total;
        count = g.total + (g.capped ? '件以上' : '件');
        const shown = res.expanded[def.key] ? g.rows.length : Math.min(App.allSearchPerGroup, g.rows.length);
        list = g.rows.length
          ? '<ul>' + g.rows.slice(0, shown).map(function (r) { return App.allSearchItemHtml(def.key, r, res.terms); }).join('') + '</ul>' +
            (shown < g.rows.length ? '<button type="button" class="all-search-more m-3 px-4 py-2 rounded border border-blue-700 text-blue-800 text-base" data-group="' + def.key + '">続きを表示（あと' + (g.rows.length - shown) + '件）</button>' : '') +
            (g.total > g.rows.length ? '<p class="text-sm text-slate-600 px-3 pb-3">数が多いので、最初の' + g.rows.length + '件だけ出しています。言葉を足すと絞り込めます。</p>' : '')
          : '<p class="text-base text-slate-600 px-3 py-3">見つかりませんでした。</p>';
      }
      summary.push({ def: def, count: count, has: !!(g && !g.error && g.total) });
      // 見出しはスクロールしても上に残す（sticky）。どの区分を見ているか分かるように。
      return '<section id="allSearchGroup-' + def.key + '" class="bg-white rounded border scroll-mt-2">' +
        '<div class="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-2 px-3 py-2 bg-slate-100 border-b shadow-sm">' +
        '<h4 class="font-bold text-base">' + esc(def.label) + ' <span class="text-blue-900">' + esc(count) + '</span></h4>' +
        '<button type="button" class="all-search-open text-sm text-blue-700 underline shrink-0" data-screen-to="' + def.screen + '">この一覧を開く</button>' +
        '</div>' + list + '</section>';
    });
    // 最初に4区分の件数の表。区分名を押すとその区分へ移動する。
    const table = '<div class="bg-white rounded border">' +
      '<table class="w-full text-base"><thead class="bg-slate-100"><tr><th class="text-left px-3 py-2">区分</th><th class="text-right px-3 py-2 whitespace-nowrap">件数</th></tr></thead><tbody>' +
      summary.map(function (x) {
        return '<tr class="border-t"><td class="px-3 py-2">' +
          (x.has ? '<button type="button" class="all-search-jump text-blue-700 underline text-left" data-group="' + x.def.key + '">' + esc(x.def.label) + '</button>' : '<span class="text-slate-700">' + esc(x.def.label) + '</span>') +
          '</td><td class="px-3 py-2 text-right whitespace-nowrap font-bold">' + esc(x.count) + '</td></tr>';
      }).join('') +
      '</tbody></table></div>';
    const courses = App.allSearchCoursesHtml();
    box.innerHTML = table + (courses ? '<div class="bg-white rounded border overflow-hidden">' + courses + '</div>' : '') + parts.join('');
    if (App.elements.allSearchMeta) {
      const pending = !res.openchat;
      const how = res.query.length > 1 && res.query.every(function (g) { return g.length === 1; })
        ? '「' + res.query.map(function (g) { return g[0]; }).join('」「') + '」のどれかを含む'
        : res.query.map(function (g) { return '「' + g.join('」と「') + '」' + (g.length > 1 ? 'をすべて含む' : 'を含む'); }).join('もの、または');
      App.elements.allSearchMeta.textContent = how + 'もの：' + sum + '件' + (pending ? '（LINEオプチャはまだ探しています）' : '') + '。表の区分名を押すとその区分へ移動します。気になる行を押すと、元の一覧で開きます。';
    }
  },
  onAllSearchResultClick: (ev) => {
    const t = ev.target && ev.target.closest ? ev.target : null;
    if (!t) return;
    const jump = t.closest('.all-search-jump');
    if (jump) {
      const sec = document.getElementById('allSearchGroup-' + jump.getAttribute('data-group'));
      if (sec && sec.scrollIntoView) sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
    const more = t.closest('.all-search-more');
    if (more && App.state.allSearchResult) {
      App.state.allSearchResult.expanded[more.getAttribute('data-group')] = true;
      App.renderAllSearchResults();
      return;
    }
    const open = t.closest('.all-search-open');
    if (open && App.state.allSearchResult) {
      // 各一覧の検索欄に入るのは1語だけ（一覧の検索は語を区切らない）。一番長い語を入れて開く。
      const screen = open.getAttribute('data-screen-to');
      const word = (App.state.allSearchResult.query[0] || []).slice().sort(function (a, b) { return b.length - a.length; })[0] || '';
      const inputId = { comments: 'commentSearchInput', knowledge: 'knowledgeSearchInput', lessons: 'lessonSearchInput', openchat: 'openchatSearchInput' }[screen];
      const el = App.elements[inputId];
      if (el) el.value = word;
      if (screen === 'openchat' && App.elements.openchatTitleFilter) App.elements.openchatTitleFilter.value = '';
      if (screen === 'comments' && App.elements.commentAttachmentsOnly) App.elements.commentAttachmentsOnly.checked = false;
      App.state.returnScreen = 'allSearch';
      App.switchScreen(screen);
      App.showDbReturnBar(screen);
      if (screen === 'comments') App.renderCommentTable();
      else if (screen === 'knowledge') App.renderKnowledgeTable();
      else if (screen === 'lessons') App.renderLessonTable();
      // オプチャは switchScreen が検索欄の語で読み込み直す
      return;
    }
    const item = t.closest('.all-search-item');
    if (!item) return;
    const kind = item.getAttribute('data-kind');
    const id = item.getAttribute('data-id') || '';
    if (kind === 'video_chunk') App.openCitationInDb({ kind: 'video_chunk', chunkKey: id });
    else if (kind === 'lesson') App.openCitationInDb({ kind: 'lesson', commentId: id });
    else if (kind === 'openchat') App.openCitationInDb({ kind: 'openchat', openchatId: id });
    else App.openCitationInDb({ kind: 'comment', commentId: id });
  },
  // (2) 評価した答えの作り方（11/11）。軽いモデルや使い回しで悪いねが多いかを見分ける。
  answerMakeLabel: (x) => {
    if (!x || !x.answer_mode) return '不明（記録前の評価）';
    const mode = { semantic: '意味検索', deep: 'より詳しく調べる', normal: '通常検索（切替前）', fast: '高速' }[x.answer_mode] || x.answer_mode;
    const tier = x.answer_mode === 'semantic' ? (x.answer_tier === 'lite' ? '・ライト版' : '・上位版') : '';
    return mode + tier + (x.answer_model ? '（' + x.answer_model + '）' : '') + (x.answer_reused ? '・使い回し' : '');
  },
  feedbackByMakeHtml: (rows) => {
    const groups = {};
    (rows || []).forEach(function (x) {
      const k = App.answerMakeLabel(x);
      const g = groups[k] || (groups[k] = { great: 0, good: 0, bad: 0 });
      if (g[x.rating] != null) g[x.rating]++;
    });
    const keys = Object.keys(groups);
    if (!keys.length) return '';
    return '<div class="md:col-span-2"><div class="font-medium">🤖 答えの作り方ごとの評価</div><ul class="text-slate-600">' + keys.map(function (k) {
      const g = groups[k], n = g.great + g.good + g.bad;
      return '<li>' + App.escapeHtml(k) + '：🌟' + g.great + ' 👍' + g.good + ' 👎' + g.bad + '（悪いね ' + Math.round(g.bad * 100 / n) + '%）</li>';
    }).join('') + '</ul></div>';
  },

  // (2) 回答の評価の一覧。見えない人には枠ごと出さない。2026-11-10
  loadFeedbackAnalytics: async () => {
    const box = document.getElementById('feedbackAnalytics');
    if (!box) return;
    const show = App.isStaffAdmin() && App.featureOn('answer_feedback');
    box.classList.toggle('hidden', !show);
    if (!show) return;
    const summary = document.getElementById('feedbackSummary'), list = document.getElementById('feedbackList');
    const btn = document.getElementById('reloadFeedbackBtn');
    if (btn && !btn.dataset.bound) { btn.dataset.bound = '1'; btn.addEventListener('click', function () { void App.loadFeedbackAnalytics(); }); }
    summary.textContent = '読み込み中…'; list.innerHTML = '';
    try {
      const r = await App.apiClient('POST', '/admin/answer-feedback/list', {});
      const rows = (r && Array.isArray(r.feedback)) ? r.feedback : [];
      const count = { great: 0, good: 0, bad: 0 };
      rows.forEach(function (x) { if (count[x.rating] != null) count[x.rating]++; });
      summary.textContent = '🌟超いいね ' + count.great + ' ／ 👍いいね ' + count.good + ' ／ 👎悪いね ' + count.bad + '（全 ' + rows.length + ' 件）';
      // 理由の内訳（多い順）。悪いねの内訳が、どこを直すかの目安になる。
      const tally = function (rating) {
        const n = {};
        rows.forEach(function (x) { if (x.rating === rating && Array.isArray(x.reasons)) x.reasons.forEach(function (c) { n[c] = (n[c] || 0) + 1; }); });
        const c = App.feedbackChoice(rating);
        return (c ? c.reasons : []).map(function (r) { return [r[1], n[r[0]] || 0]; }).sort(function (p, q) { return q[1] - p[1]; });
      };
      const breakdown = document.getElementById('feedbackBreakdown');
      if (breakdown) {
        breakdown.innerHTML = [['great', '🌟超いいねの理由'], ['bad', '👎悪いねの理由']].map(function (g) {
          return '<div><div class="font-medium">' + g[1] + '</div><ul class="text-slate-600">' + tally(g[0]).map(function (t) {
            return '<li>' + App.escapeHtml(t[0]) + '：' + t[1] + ' 件</li>';
          }).join('') + '</ul></div>';
        }).join('') + App.feedbackByMakeHtml(rows);
      }
      // よく参考にされた根拠（開いた人の数が多い順）。評価を付けていない回答で開いたものも含む。
      const topBox = document.getElementById('feedbackSources');
      if (topBox) {
        const top = Array.isArray(r && r.sources_top) ? r.sources_top : [];
        const kindLabel = { comment: 'コミュニティ', openchat: 'LINEオプチャ', lesson: '講座', video_chunk: '動画' };
        topBox.innerHTML = '<div class="font-medium">📎 参考にされた根拠（開いた人の多い順）</div>' + (top.length ? '<ol class="list-decimal ml-5 text-slate-600">' + top.map(function (t) {
          return '<li>' + App.escapeHtml((kindLabel[t.kind] || '') + '：' + (t.title || '')) + ' ― ' + t.people + ' 人・' + t.answers + ' 回答</li>';
        }).join('') + '</ol>' : '<p class="text-slate-500">まだ記録はありません。会員が答えの「本文を見る」や元ページのリンクを押すと、ここに出ます。</p>');
      }
      const icon = { great: '🌟', good: '👍', bad: '👎' };
      list.innerHTML = rows.length ? rows.map(function (x) {
        return '<div class="border rounded p-2"><div class="text-xs text-slate-500">' + (icon[x.rating] || '') + ' ' + App.escapeHtml(String(x.updated_at || '').replace('T', ' ').slice(0, 16)) + '</div>' +
          '<div><span class="text-slate-500">質問：</span>' + App.escapeHtml(x.question || '') + '</div>' +
          (Array.isArray(x.reasons) && x.reasons.length ? '<div><span class="text-slate-500">理由：</span>' + x.reasons.map(function (c) { return App.escapeHtml(App.feedbackReasonLabel(c)); }).join('、') + '</div>' : '') +
          (x.comment ? '<div><span class="text-slate-500">その他：</span>' + App.escapeHtml(x.comment) + '</div>' : '') +
          '<div class="text-xs text-slate-500">作り方：' + App.escapeHtml(App.answerMakeLabel(x)) + '</div>' +
          (Array.isArray(x.sources) && x.sources.length ? '<div><span class="text-slate-500">開いた根拠：</span>' + x.sources.map(function (c) { return App.escapeHtml((c.label ? '[' + c.label + '] ' : '') + (c.title || '')); }).join('、') + '</div>' : '') +
          '<details class="text-xs text-slate-600"><summary>回答の冒頭</summary>' + App.escapeHtml(x.answer || '') + '</details></div>';
      }).join('') : '<p class="text-slate-500">まだ評価はありません。</p>';
    } catch (e) {
      summary.textContent = '取得できませんでした: ' + ((e && e.message) || String(e));
    }
  },

  // うまくいかなかった可能性のある会話。見えない人には枠ごと出さない。2026-11-11
  loadSignalsAnalytics: async () => {
    const box = document.getElementById('signalsAnalytics');
    if (!box) return;
    const show = App.isStaffAdmin() && App.featureOn('conversation_signals');
    box.classList.toggle('hidden', !show);
    if (!show) return;
    const summary = document.getElementById('signalsSummary'), list = document.getElementById('signalsList');
    const btn = document.getElementById('reloadSignalsBtn');
    if (btn && !btn.dataset.bound) { btn.dataset.bound = '1'; btn.addEventListener('click', function () { void App.loadSignalsAnalytics(); }); }
    summary.textContent = '読み込み中…'; list.innerHTML = '';
    try {
      const r = await App.apiClient('POST', '/admin/conversation-signals/list', {});
      const labels = (r && r.labels) || {}, counts = (r && r.counts) || {}, chats = (r && Array.isArray(r.chats)) ? r.chats : [];
      const modeLabel = { semantic: '意味検索', deep: 'より詳しく', normal: '通常（切替前）', fast: '高速' };
      summary.innerHTML = App.escapeHtml('会話 ' + (r.total_chats || 0) + ' 件のうち、目印のある会話 ' + (r.flagged || 0) + ' 件') +
        '<ul class="text-slate-600 mt-1">' + Object.keys(labels).filter(function (k) { return counts[k]; }).map(function (k) {
          return '<li>' + App.escapeHtml(labels[k]) + '：' + counts[k] + ' 件</li>';
        }).join('') + '</ul>';
      list.innerHTML = chats.length ? chats.map(function (c) {
        const who = c.member ? ((c.member.member_no ? c.member.member_no + ' ' : '') + (c.member.name || '')) : '';
        return '<div class="border rounded p-2"><div class="text-xs text-slate-500">' + App.escapeHtml(String(c.last_at || '').replace('T', ' ').slice(0, 16) + (who ? '　' + who : '')) + '</div>' +
          '<div class="text-xs"><span class="text-slate-500">目印：</span>' + c.signals.map(function (s) { return App.escapeHtml(labels[s] || s); }).join('、') + '</div>' +
          '<ol class="list-decimal ml-5 mt-1">' + c.turns.map(function (t) {
            return '<li><div>' + App.escapeHtml(t.question) + ' <span class="text-xs text-slate-500">（' + App.escapeHtml(modeLabel[t.mode] || t.mode) + '）</span>' +
              (t.signals.length ? ' <span class="text-xs text-orange-700">' + t.signals.map(function (s) { return App.escapeHtml(labels[s] || s); }).join('、') + '</span>' : '') + '</div>' +
              (t.answer ? '<details class="text-xs text-slate-600"><summary>回答の冒頭</summary>' + App.escapeHtml(t.answer) + '</details>' : '') + '</li>';
          }).join('') + '</ol></div>';
      }).join('') : '<p class="text-slate-500">目印のある会話はありません。</p>';
    } catch (e) {
      summary.textContent = '取得できませんでした: ' + ((e && e.message) || String(e));
    }
  },
  // (4) 質問ランキング＋講座テーマ案。見えない人には枠ごと出さない。2026-11-11
  themeChoiceLabel: { adopt: '✅ 採用', revise: '✏️ 直して採用', reject: '❌ 不採用' },
  loadRankingThemes: async () => {
    const box = document.getElementById('rankingThemes');
    if (!box) return;
    const show = App.isStaffAdmin() && App.featureOn('ranking_themes');
    box.classList.toggle('hidden', !show);
    if (!show) return;
    const status = document.getElementById('rankingThemesStatus');
    const btn = document.getElementById('reloadRankingThemesBtn');
    if (btn && !btn.dataset.bound) { btn.dataset.bound = '1'; btn.addEventListener('click', function () { void App.loadRankingThemes(); }); }
    status.textContent = '読み込み中…';
    try {
      const r = await App.apiClient('POST', '/admin/ranking-themes/list', {});
      App.renderRankingThemes(r || {});
    } catch (e) {
      status.textContent = '取得できませんでした: ' + ((e && e.message) || String(e));
    }
  },
  renderRankingThemes: (r) => {
    const status = document.getElementById('rankingThemesStatus');
    const list = document.getElementById('rankingList'), cards = document.getElementById('themeCards'), hist = document.getElementById('themeHistory');
    const esc = App.escapeHtml;
    const latest = r.latest;
    if (!latest) {
      status.textContent = 'まだ集計の回がありません（毎週月曜の朝に作られます）。';
      list.innerHTML = ''; cards.innerHTML = ''; hist.innerHTML = '';
      return;
    }
    const st = latest.stats || {};
    status.textContent = String(latest.created_at || '').slice(0, 10) + ' の回（直近 ' + (latest.period_days || 120) + ' 日）／ Q&Aチャットへの質問 ' + (st.chatbot || 0) +
      ' 回' + (st.chatbot_users ? '・' + st.chatbot_users + ' 人' : '') + '（テーマ案の材料には、コミュニティ ' + (st.forum || 0) + ' 件・オプチャ ' + (st.openchat || 0) + ' 件・既存講座 ' + (st.courses || 0) + ' 本も使っています）';
    const exact = (latest.ranking || []).some(function (x) { return x.people != null; });
    list.innerHTML = exact ? (latest.ranking || []).map(function (x) {
      return '<li><span class="font-medium">' + esc(x.topic) + '</span> <span class="text-slate-600">' + x.count + ' 回・' + x.people + ' 人</span>' +
        (x.examples && x.examples.length ? '<details class="text-xs text-slate-600"><summary>実際の質問' + (x.variants > 1 ? '（言い方 ' + x.variants + ' 通り）' : '') + '</summary><ul class="list-disc ml-4">' + x.examples.map(function (e) { return '<li>' + esc(e) + '</li>'; }).join('') + '</ul></details>' : '') + '</li>';
    }).join('') || '<li class="list-none text-slate-500">まだ質問がありません。</li>'
      : '<li class="list-none text-slate-500">この回は数え方を見直す前のものです。次の回（または再集計）から、Q&Aチャットで聞かれた回数・人数で並びます。</li>';
    cards.innerHTML = (latest.themes || []).map(function (t) {
      const d = t.decision;
      return '<div class="border rounded p-2" data-theme="' + esc(t.id) + '">' +
        '<div class="font-medium">' + esc(t.title) + '</div>' +
        (t.target || t.format ? '<div class="text-xs text-slate-500">' + esc([t.target, t.format].filter(Boolean).join(' ／ ')) + '</div>' : '') +
        (t.why ? '<div class="mt-1"><span class="text-slate-500">なぜ今：</span>' + esc(t.why) + '</div>' : '') +
        (t.evidence ? '<div class="text-xs text-slate-600"><span class="text-slate-500">根拠：</span>' + esc(t.evidence) + '</div>' : '') +
        (d ? '<div class="mt-1 text-xs bg-slate-50 rounded p-1">' + esc(App.themeChoiceLabel[d.choice] || d.choice) + (d.revised_title ? '：' + esc(d.revised_title) : '') + (d.reason ? ' ― ' + esc(d.reason) : '') + '</div>' : '') +
        '<div class="mt-2 flex flex-wrap gap-1">' + ['adopt', 'revise', 'reject'].map(function (c) {
          return '<button type="button" class="px-2 py-0.5 rounded border text-xs" data-choice="' + c + '">' + App.themeChoiceLabel[c] + '</button>';
        }).join('') + '</div>' +
        '<div class="theme-form hidden mt-2 space-y-1">' +
        '<input type="text" maxlength="200" class="theme-title w-full border rounded px-2 py-1 text-sm hidden" placeholder="直した題名">' +
        '<textarea maxlength="1000" rows="2" class="theme-reason w-full border rounded px-2 py-1 text-sm" placeholder="理由（次の案づくりに使います）"></textarea>' +
        '<div class="flex gap-2 items-center"><button type="button" class="theme-save px-3 py-1 rounded bg-slate-800 text-white text-xs">保存</button><span class="theme-msg text-xs text-slate-500"></span></div></div></div>';
    }).join('');
    cards.querySelectorAll('[data-theme]').forEach(function (card) {
      const form = card.querySelector('.theme-form'), title = card.querySelector('.theme-title'), reason = card.querySelector('.theme-reason');
      const theme = (latest.themes || []).find(function (t) { return t.id === card.dataset.theme; }) || {};
      let choice = '';
      card.querySelectorAll('[data-choice]').forEach(function (b) {
        b.addEventListener('click', function () {
          choice = b.dataset.choice;
          card.querySelectorAll('[data-choice]').forEach(function (x) { x.classList.toggle('bg-slate-200', x === b); });
          form.classList.remove('hidden');
          title.classList.toggle('hidden', choice !== 'revise');
          if (choice === 'revise' && !title.value) title.value = (theme.decision && theme.decision.revised_title) || theme.title || '';
          if (!reason.value && theme.decision) reason.value = theme.decision.reason || '';
        });
      });
      card.querySelector('.theme-save').addEventListener('click', async function () {
        const msg = card.querySelector('.theme-msg');
        if (choice === 'revise' && !title.value.trim()) { msg.textContent = '直した題名を入れてください'; return; }
        msg.textContent = '保存中…';
        try {
          await App.apiClient('POST', '/admin/ranking-themes/decide', { round_id: latest.id, theme_id: theme.id, choice: choice, revised_title: title.value, reason: reason.value });
          void App.loadRankingThemes();
        } catch (e) {
          msg.textContent = '保存できませんでした: ' + ((e && e.message) || String(e));
        }
      });
    });
    hist.innerHTML = (r.history || []).map(function (h) {
      return '<div><span class="font-medium">' + esc(String(h.created_at || '').slice(0, 10)) + '</span>：' + (h.themes || []).map(function (t) {
        return esc(t.title) + (t.decision ? '（' + esc(App.themeChoiceLabel[t.decision.choice] || '') + '）' : '（未判断）');
      }).join('、') + '</div>';
    }).join('') || '<div>まだありません。</div>';
  },

  // Phase 13: 運営分析ダッシュボード（qa-analytics Edge）
  loadAnalytics: async () => {
    if (!App.isStaffAdmin()) return;
    void App.loadFeedbackAnalytics();
    void App.loadSignalsAnalytics();
    void App.loadRankingThemes();
    const statusEl = document.getElementById('analyticsStatus');
    const daysSelect = document.getElementById('analyticsDaysSelect');
    const days = daysSelect ? Number(daysSelect.value) || 14 : 14;
    const sinceInput = document.getElementById('analyticsSinceInput');
    const since = sinceInput && /^\d{4}-\d{2}-\d{2}$/.test(sinceInput.value) ? sinceInput.value : '';
    if (statusEl) statusEl.textContent = '読み込み中…';
    try {
      const cfg = await App.resolveSemanticConfig();
      const analyticsUrl = String(cfg.url || '').replace(/semantic-search\/?$/, 'qa-analytics');
      if (!analyticsUrl || analyticsUrl === cfg.url) {
        throw new Error('分析APIのURLを解決できませんでした');
      }
      const response = await fetch(analyticsUrl + '?days=' + encodeURIComponent(String(days)), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Semantic-Shared-Secret': cfg.secret
        },
        body: JSON.stringify(since ? { days: days, since: since } : { days: days })
      });
      const text = await response.text();
      let data = {};
      if (text) {
        try {
          data = JSON.parse(text);
        } catch (e) {
          data = { errorMessage: text.slice(0, 200) };
        }
      }
      if (!response.ok) {
        throw new Error(data.errorMessage || data.message || '分析APIエラー HTTP ' + response.status);
      }
      App.state.analyticsOverview = data;
      App.renderAnalytics();
      if (statusEl) {
        statusEl.textContent =
          '更新: ' +
          new Date().toLocaleString('ja-JP') +
          ' ／ 集計 ' +
          (data.range_days || days) +
          '日 ／ 合計 ' +
          ((data.totals && data.totals.total) || 0) +
          ' 件';
      }
    } catch (err) {
      App.state.analyticsOverview = null;
      App.renderAnalytics();
      if (statusEl) statusEl.textContent = '取得失敗: ' + ((err && err.message) || String(err));
      throw err;
    }
  },

  renderAnalytics: () => {
    const data = App.state.analyticsOverview;
    const cards = document.getElementById('analyticsSummaryCards');
    const geminiEl = document.getElementById('analyticsGeminiEstimate');
    const dailyEl = document.getElementById('analyticsDailyBars');
    const topBody = document.getElementById('analyticsTopQueriesBody');
    const recentBody = document.getElementById('analyticsRecentBody');
    App.renderAnalyticsBrand(data);
    if (!cards || !dailyEl || !topBody || !recentBody) return;

    if (!data || !data.totals) {
      cards.innerHTML = '<p class="text-sm text-slate-500 col-span-full">データがありません</p>';
      if (geminiEl) geminiEl.innerHTML = '';
      dailyEl.innerHTML = '';
      topBody.innerHTML = '';
      recentBody.innerHTML = '';
      return;
    }

    const t = data.totals;
    const pct = function (r) {
      return ((Number(r) || 0) * 100).toFixed(1) + '%';
    };
    cards.innerHTML =
      '<div class="bg-white rounded border p-3"><div class="text-xs text-slate-500">合計</div><div class="text-2xl font-semibold">' +
      App.escapeHtml(String(t.total || 0)) +
      '</div></div>' +
      '<div class="bg-white rounded border p-3 border-blue-200"><div class="text-xs text-blue-700">意味検索</div><div class="text-2xl font-semibold text-blue-900">' +
      App.escapeHtml(String(t.semantic || 0)) +
      '</div><div class="text-xs text-blue-600 mt-1">' +
      App.escapeHtml(pct(t.semantic_ratio)) +
      '</div></div>' +
      '<div class="bg-white rounded border p-3 border-amber-200"><div class="text-xs text-amber-700">より詳しく調べる</div><div class="text-2xl font-semibold text-amber-900">' +
      App.escapeHtml(String(t.deep || 0)) +
      '</div><div class="text-xs text-amber-700 mt-1">' +
      App.escapeHtml(pct(t.deep_ratio)) +
      '</div></div>' +
      // 通常検索は、新しいモードに切り替わる前の会員がいる間だけ出す（2026-11-11）
      (Number(t.normal) > 0
        ? '<div class="bg-white rounded border p-3"><div class="text-xs text-slate-500">通常検索（切替前）</div><div class="text-2xl font-semibold">' +
          App.escapeHtml(String(t.normal || 0)) +
          '</div><div class="text-xs text-slate-500 mt-1">' +
          App.escapeHtml(pct(t.normal_ratio)) +
          '</div></div>'
        : '') +
      '<div class="bg-white rounded border p-3 ' +
      (Number(t.failed) > 0 ? 'border-amber-300' : '') +
      '"><div class="text-xs text-amber-700">失敗・停止</div><div class="text-2xl font-semibold">' +
      App.escapeHtml(String(t.failed || 0)) +
      '</div><div class="text-xs text-slate-500 mt-1">disabled ' +
      App.escapeHtml(String(t.disabled || 0)) +
      '</div></div>' +
      '<div class="bg-white rounded border p-3"><div class="text-xs text-slate-500">集計日数</div><div class="text-2xl font-semibold">' +
      App.escapeHtml(String(data.range_days || 0)) +
      '</div></div>';

    if (geminiEl) {
      const g = data.gemini_estimate;
      if (!g) {
        geminiEl.innerHTML =
          '<p class="text-slate-500">試算API未更新（qa-analytics を再デプロイしてください）</p>';
      } else {
        const billableTotal =
          Number(g.billable_total) ||
          Number(g.billable_normal || 0) + Number(g.billable_semantic || 0);
        const fmtUsd = function (n) {
          return '$' + Number(n || 0).toFixed(2);
        };
        const fmtJpy = function (n) {
          return '約 ' + Number(n || 0).toLocaleString('ja-JP') + ' 円';
        };
        const unit = g.unit_usd || {};
        geminiEl.innerHTML =
          '<div class="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-2">' +
          '<div class="rounded border p-3 bg-slate-50">' +
          '<div class="text-xs text-slate-500">課金対象質問（成功のみ）</div>' +
          '<div class="text-xl font-semibold mt-1">' +
          App.escapeHtml(String(billableTotal)) +
          '</div>' +
          '<div class="text-xs text-slate-500 mt-1">意味・より詳しく ' +
          App.escapeHtml(String(g.billable_semantic || 0)) +
          (Number(g.billable_normal) > 0 ? ' / 通常（切替前） ' + App.escapeHtml(String(g.billable_normal || 0)) : '') +
          '</div></div>' +
          '<div class="rounded border p-3 bg-slate-50">' +
          '<div class="text-xs text-slate-500">想定課金（USD）</div>' +
          '<div class="text-xl font-semibold mt-1">' +
          App.escapeHtml(fmtUsd(g.usd_low) + ' 〜 ' + fmtUsd(g.usd_high)) +
          '</div></div>' +
          '<div class="rounded border p-3 bg-slate-50">' +
          '<div class="text-xs text-slate-500">想定課金（円）</div>' +
          '<div class="text-xl font-semibold mt-1">' +
          App.escapeHtml(fmtJpy(g.jpy_low) + ' 〜 ' + fmtJpy(g.jpy_high)) +
          '</div></div></div>' +
          '<p class="text-xs text-slate-500">' +
          App.escapeHtml(g.note || '想定レンジ。Google請求額そのものではありません。') +
          ' 単価目安: 通常 $' +
          App.escapeHtml(String(unit.normal_low != null ? unit.normal_low : 0.02)) +
          '〜$' +
          App.escapeHtml(String(unit.normal_high != null ? unit.normal_high : 0.04)) +
          '／問、意味 $' +
          App.escapeHtml(String(unit.semantic_low != null ? unit.semantic_low : 0.01)) +
          '〜$' +
          App.escapeHtml(String(unit.semantic_high != null ? unit.semantic_high : 0.025)) +
          '／問。為替 1USD≒' +
          App.escapeHtml(String(g.usd_per_jpy || 150)) +
          '円。</p>';
      }
    }

    const daily = data.daily || [];
    const maxDaily = Math.max(1, ...daily.map(function (d) {
      return Number(d.total) || 0;
    }));
    if (daily.length === 0) {
      dailyEl.innerHTML = '<p class="text-sm text-slate-500">この期間のデータはありません</p>';
    } else {
      dailyEl.innerHTML = daily
        .map(function (d) {
          const n = Number(d.normal) || 0;
          const s = Number(d.semantic) || 0;
          const dp = Number(d.deep) || 0;
          const nw = ((n / maxDaily) * 100).toFixed(1);
          const sw = ((s / maxDaily) * 100).toFixed(1);
          const dw = ((dp / maxDaily) * 100).toFixed(1);
          return (
            '<div>' +
            '<div class="flex justify-between text-xs text-slate-500 mb-1">' +
            '<span>' +
            App.escapeHtml(d.day || '') +
            '</span>' +
            '<span>意味 ' +
            s +
            ' / より詳しく ' +
            dp +
            (n > 0 ? ' / 通常（切替前） ' + n : '') +
            '（計 ' +
            (Number(d.total) || n + s + dp) +
            '）</span>' +
            '</div>' +
            '<div class="flex h-3 rounded-full overflow-hidden bg-slate-100 border">' +
            '<div class="bg-blue-600" style="width:' +
            sw +
            '%" title="意味 ' +
            s +
            '"></div>' +
            '<div class="bg-amber-500" style="width:' +
            dw +
            '%" title="より詳しく ' +
            dp +
            '"></div>' +
            '<div class="bg-slate-400" style="width:' +
            nw +
            '%" title="通常（切替前） ' +
            n +
            '"></div>' +
            '</div></div>'
          );
        })
        .join('');
    }

    const top = data.top_queries || [];
    const showNormal = top.some(function (q) { return Number(q.normal) > 0; });
    const normalTh = document.getElementById('analyticsTopNormalTh');
    if (normalTh) normalTh.classList.toggle('hidden', !showNormal);
    topBody.innerHTML =
      top.length === 0
        ? '<tr><td class="p-2 text-slate-500" colspan="5">なし</td></tr>'
        : top
            .map(function (q) {
              return (
                '<tr class="border-t">' +
                '<td class="p-2 max-w-md truncate" title="' +
                App.escapeHtml(q.query || '') +
                '">' +
                App.escapeHtml(q.query || '') +
                '</td>' +
                '<td class="p-2">' +
                App.escapeHtml(String(q.count || 0)) +
                '</td>' +
                '<td class="p-2">' +
                App.escapeHtml(String(q.semantic || 0)) +
                '</td>' +
                '<td class="p-2">' +
                App.escapeHtml(String(q.deep || 0)) +
                '</td>' +
                (showNormal ? '<td class="p-2">' + App.escapeHtml(String(q.normal || 0)) + '</td>' : '') +
                '</tr>'
              );
            })
            .join('');

    App.renderAnalyticsMetering(data);

    const recent = data.recent_events || [];
    recentBody.innerHTML =
      recent.length === 0
        ? '<tr><td class="p-2 text-slate-500" colspan="5">なし</td></tr>'
        : recent
            .map(function (ev) {
              const mode = String(ev.search_mode || '');
              const modeLabel = { semantic: '意味', deep: 'より詳しく', normal: '通常（切替前）', openchat_list: 'オプチャ一覧' }[mode] || mode;
              const st = String(ev.result_status || 'ok');
              const stLabel =
                st === 'ok'
                  ? 'OK'
                  : st === 'disabled'
                    ? '停止'
                    : st === 'rate_limited'
                      ? '上限'
                      : st === 'error'
                        ? 'エラー'
                        : st;
              const hits =
                (ev.comment_hit_count != null ? 'c:' + ev.comment_hit_count : '') +
                (ev.chunk_hit_count != null ? ' k:' + ev.chunk_hit_count : '');
              const dt = String(ev.created_at || '').replace('T', ' ').slice(0, 19);
              return (
                '<tr class="border-t">' +
                '<td class="p-2 whitespace-nowrap text-xs">' +
                App.escapeHtml(dt) +
                '</td>' +
                '<td class="p-2">' +
                App.escapeHtml(modeLabel) +
                '</td>' +
                '<td class="p-2 text-xs" title="' +
                App.escapeHtml(ev.error_message || '') +
                '">' +
                App.escapeHtml(stLabel) +
                '</td>' +
                '<td class="p-2 max-w-md truncate" title="' +
                App.escapeHtml(ev.query_text || '') +
                '">' +
                App.escapeHtml(ev.query_text || '') +
                '</td>' +
                '<td class="p-2 text-xs text-slate-500">' +
                App.escapeHtml(hits || '—') +
                '</td></tr>'
              );
            })
            .join('');
  },

  // 運営分析の新しい見た目（2026-11-11 松野さん「味気ないので、見やすく把握しやすく、動きもつけて」）。
  // 配色(design_theme)と同じスイッチの人だけ。数字はカウントアップ、グラフは下から伸びる。動きを減らす設定の端末では動かさない。
  // 表記: 意味=semantic、より詳しく=deep、通常(normal)は切替前の会員の分で、0件なら出さない。
  renderAnalyticsBrand: (data) => {
    const root = document.getElementById('analyticsBrand');
    if (!root) return;
    if (!document.documentElement.classList.contains('theme-a')) { root.innerHTML = ''; return; }
    const esc = App.escapeHtml;
    const num = (n) => Number(n || 0);
    const fmt = (n) => num(n).toLocaleString('ja-JP');
    if (!data || !data.totals) {
      root.innerHTML = '<div class="ab-empty"><i class="fa-solid fa-chart-column"></i><p>まだ表示できるデータがありません。<br>上の「再取得」を押すと最新の数字を読み込みます。</p></div>';
      return;
    }
    const t = data.totals;
    const days = num(data.range_days) || (data.daily || []).length || 0;
    const semantic = num(t.semantic), deep = num(t.deep), normal = num(t.normal);
    const total = num(t.total) || semantic + deep + normal;
    const failed = num(t.failed);
    const okCount = Math.max(0, total - failed);
    const series = [
      { key: 'semantic', label: '意味', note: 'ふだんの検索（言い換えも探す）', cls: 'ab-c1', value: semantic },
      { key: 'deep', label: 'より詳しく', note: '上位のAIで時間をかけて答える', cls: 'ab-c2', value: deep },
    ];
    if (normal > 0) series.push({ key: 'normal', label: '通常（切替前）', note: 'まだ新しい検索に切り替わっていない方', cls: 'ab-c3', value: normal });
    const pctOf = (v) => (total > 0 ? Math.round((v / total) * 1000) / 10 : 0);
    const daily = (data.daily || []).map((d) => {
      const o = { day: String(d.day || ''), semantic: num(d.semantic), deep: num(d.deep), normal: num(d.normal), users: num(d.users) };
      o.total = num(d.total) || o.semantic + o.deep + o.normal;
      return o;
    });
    const wd = ['日', '月', '火', '水', '木', '金', '土'];
    const dayLabel = (s, withWeek) => {
      const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
      if (!m) return s;
      const dt = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
      return Number(m[2]) + '/' + Number(m[3]) + (withWeek ? '（' + wd[dt.getDay()] + '）' : '');
    };
    const peak = daily.reduce((a, d) => (!a || d.total > a.total ? d : a), null);
    const activeDays = daily.filter((d) => d.total > 0).length;
    const avg = days > 0 ? total / days : 0;
    const half = Math.floor(daily.length / 2);
    const sumOf = (arr) => arr.reduce((s, d) => s + d.total, 0);
    const firstHalf = sumOf(daily.slice(0, half)), secondHalf = sumOf(daily.slice(daily.length - half));
    let trend = '';
    if (half >= 3 && firstHalf + secondHalf > 0) {
      if (secondHalf > firstHalf * 1.15) trend = '<span class="ab-trend ab-trend-up"><i class="fa-solid fa-arrow-trend-up"></i> 後半のほうが増えています</span>';
      else if (secondHalf < firstHalf * 0.85) trend = '<span class="ab-trend ab-trend-down"><i class="fa-solid fa-arrow-trend-down"></i> 後半のほうが減っています</span>';
      else trend = '<span class="ab-trend"><i class="fa-solid fa-arrow-right"></i> 前半と後半はほぼ同じです</span>';
    }
    const countUp = (v, digits) => '<span class="ab-count" data-to="' + v + '" data-digits="' + (digits || 0) + '">' + (digits ? Number(v).toFixed(digits) : fmt(v)) + '</span>';
    // キーワード検索（全データ）の利用。チャットの質問とは別に数えて並べる（11/12 松野さん「どっちがよく使われているか分かるように」）
    const kw = data.keyword || {};
    const kwOn = !!kw.available;
    const kwTotal = num(kw.total), kwUsers = num(kw.users), kwZero = num(kw.zero_hit);
    const chatUsers = num(t.users);

    // 1) ひと目でわかるまとめ
    const lead =
      '<div class="ab-lead">' +
      '<div class="ab-lead-icon"><i class="fa-solid fa-lightbulb"></i></div>' +
      '<div><p class="ab-lead-title">この' + esc(String(days)) + '日間のまとめ</p>' +
      '<p class="ab-lead-text">質問は <b>' + fmt(total) + '件</b>、1日あたり <b>約' + esc(avg.toFixed(1)) + '件</b> でした。' +
      (peak && peak.total > 0 ? 'いちばん多かったのは <b>' + esc(dayLabel(peak.day, true)) + 'の' + fmt(peak.total) + '件</b> です。' : '') +
      (failed > 0 ? 'うまく答えられなかった質問が <b class="ab-warn-text">' + fmt(failed) + '件</b> あります。' : 'うまく答えられなかった質問はありません。') +
      (kwOn ? 'キーワード検索は <b>' + fmt(kwTotal) + '回</b>' + (kwUsers ? '（' + fmt(kwUsers) + '人）' : '') + '使われました。' : '') +
      '</p>' + trend + '</div></div>';

    // 2) 大きな数字のカード
    const kpi = (icon, label, valueHtml, unit, sub, cls) =>
      '<div class="ab-kpi ' + (cls || '') + '"><div class="ab-kpi-head"><span class="ab-kpi-icon"><i class="fa-solid ' + icon + '"></i></span>' + esc(label) + '</div>' +
      '<div class="ab-kpi-value">' + valueHtml + '<span class="ab-kpi-unit">' + esc(unit) + '</span></div>' +
      '<div class="ab-kpi-sub">' + sub + '</div></div>';
    const kpis =
      '<div class="ab-kpis">' +
      kpi('fa-comments', '質問の合計', countUp(total), '件', '1日あたり 約' + esc(avg.toFixed(1)) + '件', 'ab-kpi-main') +
      kpi('fa-magnifying-glass', '意味', countUp(semantic), '件', '全体の ' + esc(String(pctOf(semantic))) + '%', 'ab-kpi-c1') +
      kpi('fa-book-open-reader', 'より詳しく', countUp(deep), '件', '全体の ' + esc(String(pctOf(deep))) + '%', 'ab-kpi-c2') +
      kpi(failed > 0 ? 'fa-triangle-exclamation' : 'fa-circle-check', '答えられなかった', countUp(failed), '件',
        failed > 0 ? '停止・上限・エラーの合計' : 'すべて答えられました', failed > 0 ? 'ab-kpi-warn' : 'ab-kpi-good') +
      '</div>';

    // 3) 使われ方の割合（ドーナツ）
    const R = 15.915; // 円周 100
    let offset = 0;
    const arcs = total > 0
      ? series.filter((s) => s.value > 0).map((s) => {
          const p = (s.value / total) * 100;
          const gap = p > 2 ? 0.8 : 0;
          const a = '<circle class="ab-arc ' + s.cls + '" r="' + R + '" cx="21" cy="21" transform="rotate(-90 21 21)" stroke-dasharray="0 100" data-dash="' + Math.max(0, p - gap).toFixed(2) + '" stroke-dashoffset="' + (-offset).toFixed(2) + '"><title>' + esc(s.label) + ' ' + fmt(s.value) + '件</title></circle>';
          offset += p;
          return a;
        }).join('')
      : '';
    const donut =
      '<div class="ab-card ab-mix"><h4 class="ab-h"><i class="fa-solid fa-chart-pie"></i> 検索の使われ方</h4>' +
      '<div class="ab-mix-body"><div class="ab-donut"><svg viewBox="0 0 42 42" role="img" aria-label="検索の使われ方の割合">' +
      '<circle r="' + R + '" cx="21" cy="21" class="ab-arc-bg"></circle>' + arcs + '</svg>' +
      '<div class="ab-donut-center"><span class="ab-donut-num">' + countUp(okCount) + '<small>件</small></span><span>答えられた質問</span></div></div>' +
      '<ul class="ab-legend">' + series.map((s) =>
        '<li><span class="ab-swatch ' + s.cls + '"></span><div><div class="ab-legend-name">' + esc(s.label) + '<b>' + fmt(s.value) + '件</b><em>' + esc(String(pctOf(s.value))) + '%</em></div>' +
        '<div class="ab-legend-note">' + esc(s.note) + '</div></div></li>').join('') + '</ul></div></div>';

    // 4) 日ごとの件数（積み上げ棒）
    const maxDay = Math.max(1, ...daily.map((d) => d.total));
    const step = maxDay <= 5 ? 1 : maxDay <= 10 ? 2 : maxDay <= 25 ? 5 : maxDay <= 50 ? 10 : Math.ceil(maxDay / 50) * 10;
    const top = Math.ceil(maxDay / step) * step;
    const grid = [];
    for (let v = 0; v <= top; v += step) grid.push(v);
    const labelEvery = daily.length <= 14 ? 1 : daily.length <= 31 ? 3 : daily.length <= 60 ? 7 : 14;
    const cols = daily.map((d, i) => {
      const segs = series.map((s) => d[s.key] > 0 ? '<i class="' + s.cls + '" style="height:' + ((d[s.key] / top) * 100).toFixed(2) + '%"></i>' : '').join('');
      return '<button type="button" class="ab-col' + (peak && d === peak && d.total > 0 ? ' is-peak' : '') + '" data-i="' + i + '" style="--d:' + Math.min(i * 30, 900) + 'ms" aria-label="' + esc(dayLabel(d.day, true) + ' 合計' + d.total + '件') + '">' +
        '<span class="ab-stack">' + segs + (peak && d === peak && d.total > 0 ? '<em class="ab-peak">最多 ' + fmt(d.total) + '</em>' : '') + '</span>' +
        '<span class="ab-xlab">' + (i % labelEvery === 0 || i === daily.length - 1 ? esc(dayLabel(d.day, false)) : '') + '</span></button>';
    }).join('');
    const chart = daily.length === 0
      ? '<p class="ab-muted">この期間のデータはありません</p>'
      : '<p class="ab-readout" aria-live="polite"></p>' +
        '<div class="ab-chart"><div class="ab-grid">' + grid.map((v) => '<div style="bottom:' + ((v / top) * 100).toFixed(2) + '%"><span>' + v + '</span></div>').join('') + '</div>' +
        '<div class="ab-cols' + (labelEvery === 1 && daily.length > 7 ? ' ab-cols-many' : '') + '">' + cols + '</div></div>' +
        '<ul class="ab-legend ab-legend-row">' + series.map((s) => '<li><span class="ab-swatch ' + s.cls + '"></span>' + esc(s.label) + '</li>').join('') + '</ul>';
    const dailyCard =
      '<div class="ab-card ab-daily"><h4 class="ab-h"><i class="fa-solid fa-chart-column"></i> 日ごとの質問の数</h4>' +
      '<p class="ab-muted">棒にふれる（タップする）と、その日の内訳が出ます。質問があった日は ' + fmt(activeDays) + '日／' + fmt(daily.length) + '日。</p>' + chart + '</div>';

    // 5) よく聞かれた質問（横棒）
    const tq = (data.top_queries || []).slice(0, 10);
    const tqMax = Math.max(1, ...tq.map((q) => num(q.count)));
    const ranking = tq.length === 0
      ? '<p class="ab-muted">まだありません</p>'
      : '<ol class="ab-rank">' + tq.map((q, i) =>
          '<li style="--d:' + (i * 70) + 'ms"><span class="ab-rank-no' + (i < 3 ? ' is-top' : '') + '">' + (i + 1) + '</span>' +
          '<div class="ab-rank-main"><div class="ab-rank-q" title="' + esc(q.query || '') + '">' + esc(q.query || '') + '</div>' +
          '<div class="ab-rank-bar"><i style="width:' + ((num(q.count) / tqMax) * 100).toFixed(1) + '%"></i></div></div>' +
          '<span class="ab-rank-n">' + fmt(q.count) + '<small>回</small>' + (q.users != null ? '<em>' + fmt(q.users) + '人</em>' : '') + '</span></li>').join('') + '</ol>';
    const rankCard =
      '<div class="ab-card ab-ranking"><h4 class="ab-h"><i class="fa-solid fa-comments"></i> Q&amp;Aチャットの質問ランキング</h4>' +
      '<p class="ab-muted ab-rank-note">チャットに入力された質問。同じ文の多い順・上位10（同じ人が何度聞いても人数は1人）</p>' + ranking + '</div>';

    // 6) キーワード検索ランキング（チャットとは別に）
    const kq = (kw.top || []).slice(0, 10);
    const kqMax = Math.max(1, ...kq.map((q) => num(q.count)));
    const kwRanking = !kwOn
      ? '<p class="ab-muted">記録の準備中です（反映後の検索から数えます）。</p>'
      : kq.length === 0
        ? '<p class="ab-muted">この期間はまだ検索がありません</p>'
        : '<ol class="ab-rank ab-rank-kw">' + kq.map((q, i) =>
            '<li style="--d:' + (i * 70) + 'ms"><span class="ab-rank-no' + (i < 3 ? ' is-top' : '') + '">' + (i + 1) + '</span>' +
            '<div class="ab-rank-main"><div class="ab-rank-q" title="' + esc(q.query || '') + '">' + esc(q.query || '') +
            (num(q.zero_hit) > 0 ? '<span class="ab-badge-zero">見つからず ' + fmt(q.zero_hit) + '回</span>' : '<span class="ab-rank-hits">平均 ' + fmt(q.avg_hits) + '件ヒット</span>') + '</div>' +
            '<div class="ab-rank-bar"><i style="width:' + ((num(q.count) / kqMax) * 100).toFixed(1) + '%"></i></div></div>' +
            '<span class="ab-rank-n">' + fmt(q.count) + '<small>回</small><em>' + fmt(q.users) + '人</em></span></li>').join('') + '</ol>';
    const zq = (kw.zero_queries || []).slice(0, 5);
    const kwRankCard =
      '<div class="ab-card ab-ranking ab-ranking-kw"><h4 class="ab-h"><i class="fa-solid fa-magnifying-glass"></i> キーワード検索ランキング</h4>' +
      '<p class="ab-muted ab-rank-note">「キーワード検索（全データ）」に入れた言葉。多い順・上位10</p>' + kwRanking +
      (zq.length ? '<div class="ab-zero"><b><i class="fa-solid fa-circle-exclamation"></i> 見つからなかった言葉</b>（言い換えやデータを足す候補）<div>' +
        zq.map((q) => '<span>' + esc(q.query) + '<small>' + fmt(q.count) + '回</small></span>').join('') + '</div></div>' : '') + '</div>';

    // 7) チャットとキーワード検索の比べ（回数・人数・1人あたり・前半/後半・日ごと）と、次の手のヒント
    const kwDaily = {};
    (kw.daily || []).forEach((d) => { kwDaily[String(d.day || '')] = d; });
    const allDays = Array.from(new Set(daily.map((d) => d.day).concat(Object.keys(kwDaily)))).sort();
    const pairs = allDays.map((day) => {
      const c = daily.find((d) => d.day === day);
      const k = kwDaily[day];
      return { day: day, chat: c ? c.total : 0, chatUsers: c ? num(c.users) : 0, kw: k ? num(k.count) : 0, kwUsers: k ? num(k.users) : 0 };
    });
    const halfOf = (key) => {
      const h = Math.floor(pairs.length / 2);
      if (h < 3) return null;
      const a = pairs.slice(0, h).reduce((x, d) => x + d[key], 0), b = pairs.slice(pairs.length - h).reduce((x, d) => x + d[key], 0);
      if (a + b === 0) return null;
      return b > a * 1.15 ? { cls: 'ab-trend-up', icon: 'fa-arrow-trend-up', text: '後半に増加' }
        : b < a * 0.85 ? { cls: 'ab-trend-down', icon: 'fa-arrow-trend-down', text: '後半に減少' }
        : { cls: '', icon: 'fa-arrow-right', text: '横ばい' };
    };
    const both = total + kwTotal;
    const chatPct = both > 0 ? Math.round((total / both) * 100) : 0;
    const per = (n, u) => (u > 0 ? (n / u).toFixed(1) : '—');
    const side = (cls, icon, label, count, users, extra, tr) =>
      '<div class="ab-vs-side ' + cls + '"><div class="ab-vs-label"><i class="fa-solid ' + icon + '"></i>' + esc(label) + '</div>' +
      '<div class="ab-vs-num">' + countUp(count) + '<small>回</small></div>' +
      '<div class="ab-vs-sub"><span><b>' + fmt(users) + '</b>人</span><span>1人あたり <b>' + esc(per(count, users)) + '</b>回</span></div>' +
      (extra || '') + (tr ? '<span class="ab-trend ' + tr.cls + '"><i class="fa-solid ' + tr.icon + '"></i> ' + esc(tr.text) + '</span>' : '') + '</div>';
    const hints = [];
    if (!kwOn) {
      hints.push('キーワード検索の記録はこれから始まります。反映後の検索から、ここで比べられるようになります。');
    } else if (both === 0) {
      hints.push('この期間はどちらもまだ使われていません。');
    } else {
      if (kwTotal > total * 1.2) hints.push('キーワード検索のほうがよく使われています（チャットの約' + (total > 0 ? (kwTotal / total).toFixed(1) + '倍' : '—') + '）。調べたい言葉がはっきりしている方が多いようです。よく検索される言葉は、チャットの例や講座テーマの候補にできます。');
      else if (total > kwTotal * 1.2) hints.push('チャットの質問のほうがよく使われています（キーワード検索の約' + (kwTotal > 0 ? (total / kwTotal).toFixed(1) + '倍' : '—') + '）。' + (kwTotal === 0 ? 'キーワード検索はまだ使われていません。' : '') + 'キーワード検索は、知られていないか、使いどころが伝わっていない可能性があります。');
      else hints.push('チャットの質問とキーワード検索は、ほぼ同じくらい使われています。');
      if (kwZero > 0) hints.push('キーワード検索で見つからなかったのは <b>' + fmt(kwZero) + '回</b>（' + Math.round((kwZero / Math.max(1, kwTotal)) * 100) + '%）です。キーワード検索ランキングの下の「見つからなかった言葉」は、言い換えやデータを足す候補です。');
      if (kwUsers > 0 && chatUsers > 0 && kwUsers < chatUsers / 2) hints.push('キーワード検索を使った人（' + fmt(kwUsers) + '人）は、チャットを使った人（' + fmt(chatUsers) + '人）の半分未満です。');
    }
    const fKw = App.state.features && App.state.features.keyword_all;
    if (kwOn && fKw && !fKw.members) hints.push('キーワード検索はまだ会員には公開していないため、いまの数字は試しに使った分です。');
    const pMax = Math.max(1, ...pairs.map((d) => Math.max(d.chat, d.kw)));
    const pEvery = pairs.length <= 14 ? 1 : pairs.length <= 31 ? 3 : pairs.length <= 60 ? 7 : 14;
    const pairChart = pairs.length === 0 ? '' :
      '<p class="ab-readout ab-vs-readout" aria-live="polite"></p>' +
      '<div class="ab-pair">' + pairs.map((d, i) =>
        '<button type="button" class="ab-pair-col" data-p="' + i + '" style="--d:' + Math.min(i * 30, 900) + 'ms" aria-label="' + esc(dayLabel(d.day, true) + ' チャット' + d.chat + '回 キーワード検索' + d.kw + '回') + '">' +
        '<span class="ab-pair-bars"><i class="ab-k1" style="height:' + ((d.chat / pMax) * 100).toFixed(1) + '%"></i><i class="ab-k2" style="height:' + ((d.kw / pMax) * 100).toFixed(1) + '%"></i></span>' +
        '<span class="ab-xlab">' + (i % pEvery === 0 || i === pairs.length - 1 ? esc(dayLabel(d.day, false)) : '') + '</span></button>').join('') + '</div>';
    const compareCard =
      '<div class="ab-card ab-compare"><h4 class="ab-h"><i class="fa-solid fa-scale-balanced"></i> チャットの質問とキーワード検索の比べ</h4>' +
      '<div class="ab-vs">' +
        side('ab-vs-chat', 'fa-comments', 'Q&Aチャットの質問', total, chatUsers, '', halfOf('chat')) +
        side('ab-vs-kw', 'fa-magnifying-glass', 'キーワード検索', kwTotal, kwUsers,
          kwOn ? '<div class="ab-vs-sub ab-vs-zero"><span>見つからなかった <b>' + fmt(kwZero) + '</b>回</span></div>' : '<div class="ab-vs-sub">記録の準備中</div>', halfOf('kw')) +
      '</div>' +
      (both > 0 ? '<div class="ab-share" role="img" aria-label="使われた割合 チャット' + chatPct + '% キーワード検索' + (100 - chatPct) + '%">' +
        '<i class="ab-k1" style="width:' + chatPct + '%"><span>' + (chatPct >= 12 ? 'チャット ' + chatPct + '%' : '') + '</span></i>' +
        '<i class="ab-k2" style="width:' + (100 - chatPct) + '%"><span>' + (100 - chatPct >= 12 ? 'キーワード ' + (100 - chatPct) + '%' : '') + '</span></i></div>' : '') +
      pairChart +
      (pairs.length ? '<ul class="ab-legend ab-legend-row"><li><span class="ab-swatch ab-k1"></span>Q&Aチャットの質問</li><li><span class="ab-swatch ab-k2"></span>キーワード検索</li></ul>' : '') +
      '<div class="ab-hints"><b><i class="fa-solid fa-lightbulb"></i> 読み取りと次の手</b><ul>' + hints.map((h) => '<li>' + h + '</li>').join('') + '</ul></div>' +
      '</div>';

    root.innerHTML = lead + kpis + '<div class="ab-row">' + donut + compareCard + '</div>' +
      '<div class="ab-row ab-row-even">' + rankCard + kwRankCard + '</div>' + dailyCard;
    const vsReadout = root.querySelector('.ab-vs-readout');
    const showPair = (d) => {
      if (!vsReadout || !d) return;
      vsReadout.innerHTML = '<b>' + esc(dayLabel(d.day, true)) + '</b>' +
        '<span><span class="ab-swatch ab-k1"></span>チャット ' + fmt(d.chat) + '回（' + fmt(d.chatUsers) + '人）</span>' +
        '<span><span class="ab-swatch ab-k2"></span>キーワード検索 ' + fmt(d.kw) + '回（' + fmt(d.kwUsers) + '人）</span>';
    };
    const pairPeak = pairs.reduce((a, d) => (!a || d.chat + d.kw > a.chat + a.kw ? d : a), null);
    showPair(pairPeak);
    root.querySelectorAll('.ab-pair-col').forEach((b) => {
      const d = pairs[Number(b.getAttribute('data-p'))];
      const on = () => { root.querySelectorAll('.ab-pair-col.is-on').forEach((x) => x.classList.remove('is-on')); b.classList.add('is-on'); showPair(d); };
      b.addEventListener('mouseenter', on); b.addEventListener('focus', on); b.addEventListener('click', on);
    });

    // 棒にふれたら内訳を出す（ふれていないときは、いちばん多い日）
    const readout = root.querySelector('.ab-daily .ab-readout');
    const showDay = (d) => {
      if (!readout || !d) return;
      readout.innerHTML = '<b>' + esc(dayLabel(d.day, true)) + '</b> 合計 <b>' + fmt(d.total) + '件</b>' +
        series.map((s) => '<span><span class="ab-swatch ' + s.cls + '"></span>' + esc(s.label) + ' ' + fmt(d[s.key]) + '件</span>').join('');
    };
    showDay(peak || daily[daily.length - 1]);
    root.querySelectorAll('.ab-col').forEach((b) => {
      const d = daily[Number(b.getAttribute('data-i'))];
      const on = () => { root.querySelectorAll('.ab-col.is-on').forEach((x) => x.classList.remove('is-on')); b.classList.add('is-on'); showDay(d); };
      b.addEventListener('mouseenter', on); b.addEventListener('focus', on); b.addEventListener('click', on);
    });

    // 動き: 次の描画で伸ばす・数える
    let reduce = false;
    try { reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { /* ignore */ }
    const finish = () => {
      root.classList.add('is-in');
      root.querySelectorAll('.ab-arc[data-dash]').forEach((c) => c.setAttribute('stroke-dasharray', c.getAttribute('data-dash') + ' 100'));
    };
    if (reduce) { finish(); return; }
    root.classList.remove('is-in');
    requestAnimationFrame(() => requestAnimationFrame(finish));
    const start = performance.now(), dur = 1100;
    const counters = Array.from(root.querySelectorAll('.ab-count'));
    counters.forEach((el) => { el.textContent = '0'; });
    const tick = (now) => {
      const p = Math.min(1, (now - start) / dur);
      const e = 1 - Math.pow(1 - p, 3);
      counters.forEach((el) => {
        const to = Number(el.getAttribute('data-to')) || 0, dg = Number(el.getAttribute('data-digits')) || 0;
        el.textContent = dg ? (to * e).toFixed(dg) : Math.round(to * e).toLocaleString('ja-JP');
      });
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  },

  // 費用の実測（週次）: qa-analytics の metering を表示
  renderAnalyticsMetering: (data) => {
    const el = document.getElementById('analyticsMetering');
    if (!el) return;
    const m = data && data.metering;
    if (!m) {
      el.innerHTML =
        '<p class="text-slate-500">' +
        App.escapeHtml(
          data && data.metering_error
            ? '週次集計が未設定です（migration 20261105_qa_usage_metering.sql を適用してください）'
            : 'データがありません'
        ) +
        '</p>';
      return;
    }
    const yen = function (n) {
      return Number(n || 0).toLocaleString('ja-JP') + '円';
    };
    const num = function (n) {
      return Number(n || 0).toLocaleString('ja-JP');
    };
    const card = function (label, value, sub) {
      return (
        '<div class="rounded border p-3 bg-slate-50"><div class="text-xs text-slate-500">' +
        App.escapeHtml(label) +
        '</div><div class="text-lg font-semibold mt-1">' +
        App.escapeHtml(value) +
        '</div>' +
        (sub ? '<div class="text-xs text-slate-500 mt-1">' + App.escapeHtml(sub) + '</div>' : '') +
        '</div>'
      );
    };
    const perQ =
      m.jpy_per_question_low == null
        ? '—'
        : m.jpy_per_question_low + '〜' + m.jpy_per_question_high + '円';
    const semPerQ =
      m.semantic_usd_per_question == null
        ? '未計測'
        : '$' + Number(m.semantic_usd_per_question).toFixed(4) +
          '（約' + (Number(m.semantic_usd_per_question) * Number(m.usd_jpy || 150)).toFixed(2) + '円）';
    const weekly = m.weekly || [];
    el.innerHTML =
      '<div class="grid grid-cols-2 md:grid-cols-4 gap-3">' +
      card('成功質問数', num(m.questions), '利用者 ' + (m.period_users == null ? '—' : num(m.period_users)) + ' 人') +
      card('Gemini 費用（期間）', yen(m.total_jpy_low) + '〜' + yen(m.total_jpy_high), '通常検索（切替前）の幅で上下') +
      card('1問あたり', perQ, '試算は1.5〜6円') +
      card('意味検索 1問の実費', semPerQ, '実測 ' + num(m.semantic_metered) + ' 問') +
      '</div>' +
      '<table class="w-full text-xs mt-2"><thead class="bg-slate-50 text-slate-600"><tr>' +
      '<th class="p-2 text-left">週</th><th class="p-2 text-right">質問</th><th class="p-2 text-right">通常（切替前）</th>' +
      '<th class="p-2 text-right">意味・より詳しく</th><th class="p-2 text-right">利用者</th>' +
      '<th class="p-2 text-right">入力トークン</th><th class="p-2 text-right">出力トークン</th>' +
      '<th class="p-2 text-right">費用（円）</th></tr></thead><tbody>' +
      (weekly.length === 0
        ? '<tr><td class="p-2 text-slate-500" colspan="8">なし</td></tr>'
        : weekly
            .map(function (w) {
              return (
                '<tr class="border-t"><td class="p-2 whitespace-nowrap">' +
                App.escapeHtml(String(w.week_start_jst || '')) +
                '〜</td><td class="p-2 text-right">' + num(w.questions) +
                '</td><td class="p-2 text-right">' + num(w.normal_ok) +
                '</td><td class="p-2 text-right">' + num(w.semantic_ok) +
                '</td><td class="p-2 text-right">' + num(w.users) +
                '</td><td class="p-2 text-right">' + num(w.prompt_tokens) +
                '</td><td class="p-2 text-right">' + num(w.output_tokens) +
                '</td><td class="p-2 text-right whitespace-nowrap">' +
                App.escapeHtml(num(w.total_jpy_low) + '〜' + num(w.total_jpy_high)) +
                '</td></tr>'
              );
            })
            .join('')) +
      '</tbody></table>' +
      '<p class="text-xs text-slate-500">' +
      App.escapeHtml(
        (m.note || '') +
          ' 単価: 入力 $' + (m.price_usd_per_m ? m.price_usd_per_m.input : 0.5) +
          '／出力 $' + (m.price_usd_per_m ? m.price_usd_per_m.output : 3) +
          '（100万トークンあたり）、1USD≒' + (m.usd_jpy || 150) +
          '円。週の利用者数は通常（切替前）と意味・より詳しくの多い方。'
      ) +
      '</p>';
  },

  callSemanticSearch: async (query, fetchOptions) => {
    const cfg = await App.resolveSemanticConfig();
    const options = {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Semantic-Shared-Secret': cfg.secret
      },
      body: JSON.stringify({
        query: query,
        comment_limit: 100,
        chunk_limit: 50,
        openchat_limit: 20,
        match_threshold: 0.22,
        session_id: App.state.currentSessionId || undefined,
        user_id: (App.state.currentUser && App.state.currentUser.id) || undefined
      })
    };
    if (fetchOptions && fetchOptions.signal) options.signal = fetchOptions.signal;
    const response = await fetch(cfg.url, options);
    const text = await response.text();
    let data = {};
    if (text) {
      try {
        data = JSON.parse(text);
      } catch (e) {
        data = { _rawBody: text };
      }
    }
    if (!response.ok) {
      const msg =
        data.errorMessage ||
        data.message ||
        data.error ||
        (data._rawBody ? String(data._rawBody).slice(0, 200) : '') ||
        '意味検索APIエラー';
      const err = new Error(msg);
      err.httpStatus = response.status;
      err.code = data.code || '';
      throw err;
    }
    if (data && data.errorMessage) {
      throw new Error(String(data.errorMessage));
    }
    return data;
  },

  sendQuestionSemantic: async (sessionId, questionText, signal) => {
    await App.apiClient(
      'POST',
      '/chat-sessions/' + sessionId + '/messages-append',
      { role: 'user', content: questionText },
      { signal: signal }
    );
    const sem = await App.callSemanticSearch(questionText, { signal: signal });
    const answer =
      String((sem && sem.answer) || '').trim() ||
      '参照内で確証が取れないため、お答えすることができません。';
    await App.apiClient(
      'POST',
      '/chat-sessions/' + sessionId + '/messages-append',
      { role: 'assistant', content: answer },
      { signal: signal }
    );
    return {
      answer: answer,
      usedSources: (sem && sem.usedSources) || '',
      relatedComments: (sem && sem.relatedComments) || [],
      relatedChunks: (sem && sem.relatedChunks) || [],
      relatedSources: (sem && sem.relatedSources) || [],
      relatedOpenchat: (sem && sem.relatedOpenchat) || []
    };
  },

  citationAnchor: (c, messageId) => 'reference-' + encodeURIComponent(String(messageId || 'answer')) + '-' + encodeURIComponent(String(c.kind || '')) + '-' + encodeURIComponent(String(c.commentId || c.openchatId || c.chunkKey || '')),

  referenceDateParts: (value) => {
    let raw=String(value || '').trim();
    if (!raw) return null;
    if (/^\d{4}[/-]\d{1,2}[/-]\d{1,2}(?:\s|$)/.test(raw) && !/[zZ]|[+-]\d{2}:?\d{2}$/.test(raw)) raw=raw.replace(/\//g,'-').replace(' ','T') + (raw.length<=10 ? 'T00:00:00' : '') + '+09:00';
    const ms=Date.parse(raw); if (!Number.isFinite(ms)) return null;
    const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(ms));
    const get=(kind)=>parts.find(p=>p.type===kind).value;
    return {year:Number(get('year')),month:Number(get('month')),day:Number(get('day')),ms:ms,label:get('year')+'/'+get('month')+'/'+get('day')};
  },

  groupReferencesByDate: (items, currentYear) => {
    const year=currentYear || Number(new Intl.DateTimeFormat('en',{timeZone:'Asia/Tokyo',year:'numeric'}).format(new Date()));
    const groups={};
    items.slice().sort((a,b)=>((App.referenceDateParts(b.postedAt)||{}).ms||0)-((App.referenceDateParts(a.postedAt)||{}).ms||0)).forEach(c=>{
      const d=App.referenceDateParts(c.postedAt),inferred=Number(c.inferredYear),y=d?d.year:(inferred>=1900&&inferred<=2100?inferred:null);
      const key=!y?'unknown':y===year?String(y)+'-'+(d?String(d.month).padStart(2,'0'):'00'):String(y);
      if(!groups[key])groups[key]={key:key,label:!y?'日時未記録':y===year?y+'年'+(d?d.month+'月':'（月不明）'):y+'年',items:[]};
      groups[key].items.push(c);
    });
    return Object.keys(groups).sort((a,b)=>a==='unknown'?1:b==='unknown'?-1:b.localeCompare(a)).map(k=>groups[k]);
  },

  linkReferenceLabels: (text, citations, messageId) => {
    const labels={};(citations||[]).forEach(c=>{if(c.citationLabel)labels[c.citationLabel]=c;});
    const expanded=String(text||'').replace(/(LINEオプチャ|コミュニティ|セミナー)(\d+(?:\s*[、,]\s*\d+)+)/g,(_,prefix,numbers)=>numbers.split(/[、,]/).map(n=>prefix+Number(n.trim())).join('、'));
    let linked=expanded.replace(/(?:LINEオプチャ|コミュニティ|セミナー)\d+/g,label=>labels[label]?'['+label+'](#'+App.citationAnchor(labels[label],messageId)+')':label);
    (citations||[]).filter(c=>c.kind==='video_chunk'&&c.videoTitle&&c.videoUrl).forEach(c=>{
      const url=App.safeReferenceUrl(c.videoPageUrl)||App.safeReferenceUrl(App.withVideoTimeUrl(c.videoUrl,c.startSec||0));if(!url)return;
      const time=App.formatMmSs(c.startSec||0),plain=String(Math.floor(Number(c.startSec||0)/60))+time.slice(-3);
      [time,plain].forEach(t=>{const phrase=App.displaySourceTitle(c.videoTitle)+' '+t+'頃';if(linked.includes(phrase))linked=linked.split(phrase).join('['+phrase.replace(/[\[\]]/g,'')+']('+url.replace(/\(/g,'%28').replace(/\)/g,'%29')+')');});
    });
    return linked;
  },

  safeReferenceUrl: (value) => {
    try {const u=new URL(String(value||''));return ['https:','http:'].includes(u.protocol)?u.href:'';}catch(e){return '';}
  },

  retryRead: async (operation, current) => {
    for(let attempt=0;attempt<3;attempt++){
      if(current && !current())throw new Error('session_changed');
      try{return await operation();}catch(error){
        const status=error && error.httpStatus;
        if((status && status<500 && status!==429)||attempt===2)throw error;
        await App.retryDelay(attempt===0?1000:3000);
      }
    }
  },

  retryDelay: (milliseconds) => new Promise(resolve=>window.setTimeout(resolve,milliseconds)),

  renderAttachmentStatus: () => {
    const box=document.getElementById('attachmentStatus'),text=document.getElementById('attachmentStatusText'),button=document.getElementById('retryAttachmentsBtn');
    if(!box||!text||!button)return;
    box.classList.toggle('hidden',!App.state.attachmentStatus);
    text.textContent=App.state.attachmentStatus;
    button.disabled=App.state.attachmentLoading;
    button.classList.toggle('hidden',App.state.attachmentLoading);
  },

  loadReferenceMetadata: async (generation) => {
    const uid=String((App.state.currentUser||{}).id||'');
    const current=()=>App.state.attachmentGeneration===generation && String((App.state.currentUser||{}).id||'')===uid;
    if(!App.authGatewayBase)return;
    try{
      const data=await App.retryRead(()=>App.apiClient('GET','/reference-metadata'),current);
      if(!current())return;
      const map={};(data.comments||[]).forEach(row=>{map[String(row.comment_id)]=row;});
      App.state.referenceComments=map;
      (data.sources||[]).forEach(row=>{if(row.source_key)App.state.knowledgeSources[row.source_key]=row;});
      App.renderChatMessages();App.renderCommentTable();
    }catch(error){if(current())App.state.referenceMetadataUnavailable=true;}
  },

  pendingAnswerStorageKey: () => 'qa_pending_answer_v1_'+String((App.state.currentUser||{}).id||''),

  readPendingAnswer: () => {
    try{
      if(typeof sessionStorage==='undefined')return App.state.pendingAnswerRequest||null;
      const value=JSON.parse(sessionStorage.getItem(App.pendingAnswerStorageKey())||'null');
      return value&&String(value.userId)===String((App.state.currentUser||{}).id)?value:null;
    }catch(error){return null;}
  },

  savePendingAnswer: (value) => {
    App.state.pendingAnswerRequest=value;
    try{if(typeof sessionStorage!=='undefined')sessionStorage.setItem(App.pendingAnswerStorageKey(),JSON.stringify(value));}catch(error){}
  },

  clearPendingAnswer: () => {
    try{if(typeof sessionStorage!=='undefined')sessionStorage.removeItem(App.pendingAnswerStorageKey());}catch(error){}
    App.state.pendingAnswerRequest=null;App.state.answerJobStatus='';App.renderAnswerJobStatus();
  },

  renderAnswerJobStatus: () => {
    const box=document.getElementById('answerJobStatus'),text=document.getElementById('answerJobStatusText'),button=document.getElementById('resumeAnswerBtn');
    if(!box||!text||!button)return;
    // 作成中は、画面上の細い帯ではなくチャット欄の中に大きく出す（11/11 松野さん「今検討中だとわかりやすく」）。
    // 帯は「取得を再開」が要るとき（通信の中断など）だけ使う。
    const working=!!App.state.answerJobStatus&&!!App.state.sendAbortController;
    box.classList.toggle('hidden',!App.state.answerJobStatus||working);text.textContent=App.state.answerJobStatus;
    button.classList.toggle('hidden',!!App.state.sendAbortController);button.disabled=!!App.state.sendAbortController;
    App.renderAnswerWorkingCard(working);
  },

  renderAnswerWorkingCard: (on) => {
    const stop=()=>{if(App.state.answerWorkingTimer){window.clearInterval(App.state.answerWorkingTimer);App.state.answerWorkingTimer=null;}const old=document.getElementById('answerWorkingCard');if(old)old.remove();};
    if(!on){stop();App.state.answerWorkingSince=0;return;}
    if(!App.state.answerWorkingSince)App.state.answerWorkingSince=Date.now();
    const deep=(App.state.pendingAnswerRequest&&App.state.pendingAnswerRequest.mode==='deep')||!!App.state.deepMode;
    if(document.documentElement.classList.contains('theme-a')){App.renderAnswerSearchMotion(deep);if(!App.state.answerWorkingTimer)App.state.answerWorkingTimer=window.setInterval(()=>App.renderAnswerSearchMotion(deep),1000);return;}
    const draw=()=>{
      const list=document.getElementById('chatMessages');if(!list)return;
      let card=document.getElementById('answerWorkingCard');
      if(!card){
        card=document.createElement('div');card.id='answerWorkingCard';card.setAttribute('role','status');card.setAttribute('aria-live','polite');
        card.className='flex justify-center py-4';
        card.innerHTML='<div class="flex items-center gap-3 rounded-xl border border-blue-200 bg-white shadow-sm px-5 py-4 max-w-md w-full">'+
          '<i class="fa-solid fa-spinner fa-spin text-blue-700 text-xl" aria-hidden="true"></i>'+
          '<div class="min-w-0"><div class="font-semibold text-blue-900">'+(deep?'より詳しく調べています…':'回答を考えています…')+'</div>'+
          '<div class="text-xs text-slate-500 mt-0.5">'+(deep?'たくさんの投稿や動画を読み比べるため、1〜3分ほどかかることがあります。':'関連する投稿・動画・LINEオプチャを探して、まとめています。')+'</div>'+
          '<div class="text-xs text-slate-400 mt-1" data-elapsed></div></div></div>';
      }
      if(card.parentNode!==list||list.lastElementChild!==card){list.appendChild(card);list.scrollTop=list.scrollHeight;}
      const sec=Math.floor((Date.now()-App.state.answerWorkingSince)/1000),el=card.querySelector('[data-elapsed]');
      if(el)el.textContent='経過 '+(sec>=60?Math.floor(sec/60)+'分':'')+(sec%60)+'秒';
    };
    draw();
    if(!App.state.answerWorkingTimer)App.state.answerWorkingTimer=window.setInterval(draw,1000);
  },

  // 回答待ちの「探しています」アニメーションと残り時間の目安（2026-11-11 松野さん「待ってますよ感」「あとどれくらいか」）。
  // 配色(design_theme)と同じスイッチの人だけ。サーバーは途中経過を返さないので、段階は時間に合わせた目安の表示。
  // 残り時間は、この端末で過去にかかった時間（質問の種類ごと最大10回の中央値）か、全体の実測から決めた初期値で出す。
  ANSWER_DURATION_DEFAULTS: { normal: 60, semantic: 25, deep: 90 },
  answerModeKey: () => {
    const p=App.state.pendingAnswerRequest;const m=p&&p.mode?p.mode:(App.state.deepMode?'deep':(App.state.semanticMode?'semantic':'normal'));
    return (m==='deep'||m==='semantic')?m:'normal';
  },
  recordAnswerDuration: (mode,ms) => {
    try{
      const key=(mode==='deep'||mode==='semantic')?mode:'normal';const sec=Math.round(ms/1000);
      if(!(sec>=3&&sec<=330))return;
      const all=JSON.parse(localStorage.getItem('qa_answer_durations')||'{}');
      const list=Array.isArray(all[key])?all[key]:[];list.push(sec);all[key]=list.slice(-10);
      localStorage.setItem('qa_answer_durations',JSON.stringify(all));
    }catch(e){/* ignore */}
  },
  estimateAnswerSeconds: (mode) => {
    try{
      const list=(JSON.parse(localStorage.getItem('qa_answer_durations')||'{}')[mode])||[];
      if(list.length>=3){const v=list.slice().sort((a,b)=>a-b);return Math.max(10,v[Math.floor(v.length/2)]);}
    }catch(e){/* ignore */}
    return App.ANSWER_DURATION_DEFAULTS[mode]||60;
  },
  // 待っている間のおすすめ講座（11/11 松野さん、いけともさんの事例）。質問の言葉と講座タイトルの重なりで最大3件。
  // データは画面に同梱している講座一覧（WESTUDY_COURSE_CATALOG）だけを使い、AIも追加の通信も使わない。
  answerWaitCourses: (query) => {
    const cat=window.WESTUDY_COURSE_CATALOG||{};const q=String(query||'').replace(/[\s、。？！?!・「」（）()]/g,'');
    if(q.length<2)return [];
    const grams=new Set();for(let i=0;i<q.length-1;i++){const g=q.slice(i,i+2);if(!/^[ぁ-ん]{2}$/.test(g))grams.add(g);}
    if(!grams.size)return [];
    const seen=new Set();const rows=[];
    Object.keys(cat).forEach((url)=>{
      const v=cat[url]||{};if(!v.title||/はじめに/.test(v.course||''))return;
      const text=String(v.title)+' '+String(v.section||'');let score=0;grams.forEach((g)=>{if(text.indexOf(g)>=0)score+=1;});
      const key=String(v.title).replace(/\s+/g,'');if(score>=2&&!seen.has(key)){seen.add(key);rows.push({url:url,title:String(v.title),course:String(v.course||''),score:score});}
    });
    return rows.sort((a,b)=>b.score-a.score).slice(0,3);
  },
  answerWaitCoursesHtml: () => {
    const p=App.state.pendingAnswerRequest;const list=App.answerWaitCourses(p&&p.query);
    if(!list.length)return '';
    const esc=(t)=>App.escapeHtml?App.escapeHtml(t):String(t).replace(/[&<>"']/g,(c)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
    return '<div class="search-motion-courses"><div class="search-motion-courses-title"><i class="fa-solid fa-circle-play" aria-hidden="true"></i> 待っている間に（関連しそうな講座）</div><ul>'+
      list.map((r)=>'<li><a href="'+esc(r.url)+'" target="_blank" rel="noopener">'+esc(r.title)+'</a><span>'+esc(r.course.replace(/^神大家/,''))+'</span></li>').join('')+'</ul></div>';
  },
  renderAnswerSearchMotion: (deep) => {
    const list=document.getElementById('chatMessages');if(!list)return;
    const mode=App.answerModeKey(),est=App.estimateAnswerSeconds(mode);
    const sec=Math.floor((Date.now()-App.state.answerWorkingSince)/1000);
    const steps=[
      {icon:'fa-comments',label:'コミュニティの投稿を探しています'},
      {icon:'fa-circle-play',label:'講義動画の内容を探しています'},
      {icon:'fa-brands fa-line',label:'LINEオプチャを探しています'},
      {icon:'fa-pen-to-square',label:'見つかった情報をまとめています'},
    ];
    // 目安時間の 15% / 35% / 55% で次の段階へ。最後の「まとめ」は回答が届くまで続く。
    const ratio=sec/est;const idx=ratio<0.15?0:ratio<0.35?1:ratio<0.55?2:3;
    // 進み具合の帯: 目安までに9割、超えたらゆっくり近づくだけ（100%にはしない）
    const pct=ratio<=1?Math.round(ratio*90):Math.min(98,Math.round(90+8*(1-Math.exp(-(ratio-1)*1.5))));
    // 秒数ではなく言葉で進み具合を伝える（11/11 松野さん「ゲージで進んでる感が出ればいい」）
    const remain=ratio<0.3?'調べ始めました':ratio<0.6?'半分ほど進みました':ratio<0.9?'もうすぐまとまります':ratio<=1?'まもなくお届けします':'もう少しお待ちください（混み合うと少し長くかかります）';
    let card=document.getElementById('answerWorkingCard');
    if(!card){
      card=document.createElement('div');card.id='answerWorkingCard';card.setAttribute('role','status');card.setAttribute('aria-live','polite');
      card.className='search-motion-wrap';
      card.innerHTML='<div class="search-motion">'+
        '<div class="search-motion-bar"><span></span><span></span><span></span><b>'+(deep?'より詳しく調べています':'神大家AIナビが調べています')+'</b></div>'+
        '<div class="search-motion-body">'+
          '<div class="search-motion-scan" aria-hidden="true"><div class="search-motion-lines"><i></i><i></i><i></i><i></i></div><div class="search-motion-glass"><i class="fa-solid fa-magnifying-glass"></i></div></div>'+
          '<ol class="search-motion-steps">'+steps.map((s,i)=>'<li data-step="'+i+'"><i class="'+(s.icon.indexOf('fa-brands')===0?s.icon:'fa-solid '+s.icon)+'" aria-hidden="true"></i><span>'+s.label+'</span></li>').join('')+'</ol>'+
          '<div class="search-motion-progress" aria-hidden="true"><div data-progress></div></div>'+
          '<div class="search-motion-meta"><span data-remain></span><span data-elapsed></span></div>'+
        '</div>'+App.answerWaitCoursesHtml()+'</div>';
    }
    if(card.parentNode!==list||list.lastElementChild!==card){list.appendChild(card);list.scrollTop=list.scrollHeight;}
    card.querySelectorAll('[data-step]').forEach((li)=>{const i=Number(li.getAttribute('data-step'));li.classList.toggle('is-done',i<idx);li.classList.toggle('is-active',i===idx);});
    const bar=card.querySelector('[data-progress]');if(bar)bar.style.width=pct+'%';
    const r=card.querySelector('[data-remain]');if(r)r.textContent=remain;
    const el=card.querySelector('[data-elapsed]');if(el)el.textContent='経過 '+(sec>=60?Math.floor(sec/60)+'分':'')+(sec%60)+'秒';
  },
  answerPollDelay: (ms,signal) => new Promise((resolve,reject)=>{
    const cancel=()=>{window.clearTimeout(timer);const error=new Error('aborted');error.name='AbortError';reject(error);};
    const timer=window.setTimeout(()=>{signal.removeEventListener('abort',cancel);resolve();},ms);
    signal.addEventListener('abort',cancel,{once:true});if(signal.aborted)cancel();
  }),

  runAnswerJob: async (sessionId,query,mode,signal) => {
    const uid=String((App.state.currentUser||{}).id||'');
    const current=()=>!signal.aborted&&String((App.state.currentUser||{}).id||'')===uid;
    let pending=App.state.pendingAnswerRequest||App.readPendingAnswer();
    if(pending&&(pending.query!==query||pending.mode!==mode||String(pending.sessionId)!==String(sessionId)))throw new Error('前の回答を作成中です。「回答の取得を再開」から確認してください。');
    if(!pending){pending={userId:uid,sessionId:String(sessionId),query:query,mode:mode,requestId:crypto.randomUUID(),startedAt:Date.now(),jobId:null};App.savePendingAnswer(pending);}
    App.state.answerJobStatus='回答を作成中です。数分かかる場合があります。';App.renderAnswerJobStatus();
    const call=(method,path,body)=>App.retryRead(()=>App.apiClient(method,path,body,{signal:AbortSignal.any([signal,AbortSignal.timeout(20000)])}),current);
    try{
      let state=pending.jobId?null:await call('POST','/chat-sessions/'+sessionId+'/answer-jobs',{request_id:pending.requestId,query:query,mode:mode});
      if(!current()){const error=new Error('aborted');error.name='AbortError';throw error;}
      if(state){if(!/^[0-9a-f-]{36}$/i.test(state.job_id||''))throw new Error('回答の受付結果を確認できませんでした。取得を再開してください。');pending.jobId=state.job_id;App.savePendingAnswer(pending);}
      const pollStartedAt=Date.now();
      while(Date.now()-pollStartedAt<330000){
        if(!current()){const error=new Error('aborted');error.name='AbortError';throw error;}
        if(!state)state=await call('GET','/chat-sessions/'+sessionId+'/answer-jobs/'+pending.jobId);
        if(!current()){const error=new Error('aborted');error.name='AbortError';throw error;}
        if(state.status==='done'&&state.result){App.recordAnswerDuration(mode,Date.now()-(pending.startedAt||pollStartedAt));return state.result;}
        if(state.status==='failed'){
          App.clearPendingAnswer();
          throw new Error(state.error==='answer_timeout'?'回答の作成が制限時間に達しました。履歴を確認してから再試行してください。':state.error==='semantic_disabled'?'意味検索は一時停止中です。':'回答を作成できませんでした。履歴を確認してから再試行してください。');
        }
        await App.answerPollDelay(5000,signal);state=null;
      }
      App.state.answerJobStatus='回答の処理状況を再確認できます。';App.renderAnswerJobStatus();
      throw new Error('回答の取得を再開して処理状況を確認してください。');
    }catch(error){
      if(error&&[403,404,409].includes(error.httpStatus))App.clearPendingAnswer();
      if(current()&&App.state.pendingAnswerRequest){App.state.answerJobStatus='通信が中断しました。回答を作り直さずに取得を再開できます。';App.renderAnswerJobStatus();}
      throw error;
    }
  },

  resumePendingAnswer: async () => {
    if(!App.state.currentUser||App.state.sendAbortController)return;
    const pending=App.state.pendingAnswerRequest||App.readPendingAnswer();if(!pending)return;
    App.state.pendingAnswerRequest=pending;App.state.currentSessionId=pending.sessionId;
    App.state.semanticMode=pending.mode==='semantic'||pending.mode==='deep';App.state.deepMode=pending.mode==='deep';App.updateSemanticModeButton();
    await App.sendQuestion(pending.query,true);
  },

  sendQuestion: async (questionText, fromSuggested) => {
    if (!questionText) {
      App.showToast('質問内容が空です', 'error');
      return;
    }
    if (!App.state.currentUser || !App.state.currentUser.id) {
      App.showToast('ユーザ情報が取得できません', 'error');
      return;
    }
    // Phase 14-1: 二重送信ガード（意味検索の長時間中に連打しない）
    if (App.state.loadingCount > 0 || App.state.sendAbortController) {
      App.showToast('回答生成中です。完了までお待ちください', 'info');
      return;
    }

    App.state.pendingQuestionText = questionText;
    App.state.preferFastSummary = false;
    App.setButtonLoading(App.elements.sendMessageBtn, true, '送信中');
    App.setLoading(true);
    try {
      let sessionId = App.state.currentSessionId;

      if (!sessionId) {
        const title =
          String(questionText || '')
            .replace(/\s+/g, ' ')
            .trim()
            .slice(0, 40) || '新しいチャット';
        const sessionRes = await App.apiClient('POST', '/chat-sessions', {
          user_id: App.state.currentUser.id,
          initial_message: title
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

      let msgRes = null;
      let usedFast = false;
      while (!msgRes) {
        const fast = !!App.state.preferFastSummary;
        usedFast = fast;
        const controller = new AbortController();
        App.state.sendAbortController = controller;
        try {
          if(App.authGatewayBase){
            const pending=App.state.pendingAnswerRequest||App.readPendingAnswer();
            const mode=pending?pending.mode:App.currentAnswerMode(fast);
            msgRes=await App.runAnswerJob(sessionId,questionText,mode,controller.signal);
          } else if (App.state.semanticMode && !fast) {
            // 意味検索: Raimo api ネスト障害を避け、Edge をブラウザから直接呼ぶ
            msgRes = await App.sendQuestionSemantic(
              sessionId,
              questionText,
              controller.signal
            );
          } else {
            msgRes = await App.apiClient(
              'POST',
              App.messageEndpointForMode(sessionId, fast),
              { content: questionText },
              { signal: controller.signal }
            );
          }
        } catch (error) {
          if (error && error.name === 'AbortError') {
            if (App.state.preferFastSummary && !fast) {
              continue;
            }
            throw error;
          }
          throw error;
        } finally {
          if (App.state.sendAbortController === controller) {
            App.state.sendAbortController = null;
          }
        }
      }
      // 答えが届いたら、画面の描き直しより先に「探しています」を閉じる。
      // （描き直しで一度消えたカードを1秒ごとの更新がまた出してしまい、2回終わるように見えていた。11/11 松野さん）
      App.renderAnswerWorkingCard(false);

      const used = App.parseUsedSources(
        (msgRes && (msgRes.usedSources || msgRes.used_sources)) || ''
      );
      const relatedCommentsMerged = []
        .concat(App.normalizeRelatedList((msgRes && msgRes.relatedComments) || []))
        .concat(App.normalizeRelatedList((msgRes && msgRes.relatedLessonComments) || []));
      let pendingCitations = App.buildCitationsFromRelated(
        relatedCommentsMerged,
        (msgRes && msgRes.relatedChunks) || [],
        (msgRes && msgRes.relatedSources) || [],
        used.ok
          ? {
              commentIds: used.commentIds,
              chunkKeys: used.chunkKeys,
              openchatIds: used.openchatIds,
              strict: true
            }
          : null,
        (msgRes && msgRes.relatedOpenchat) || [],
        (msgRes && msgRes.referenceSelection) || 'unknown'
      );
      if (msgRes && Array.isArray(msgRes.citations) && msgRes.citations.length) {
        pendingCitations = msgRes.citations;
      }
      App.state.lastCitations = pendingCitations;

      if (!fromSuggested) {
        try{await App.createSuggestedQuestionIfNeeded(questionText);}catch(error){}
      }

      await App.loadSessionDetails(sessionId);
      const assistantMsgId = App.findLastAssistantMessageId(App.state.chatMessages || []);
      if (assistantMsgId) {
        App.saveCitationsForMessage(sessionId, assistantMsgId, pendingCitations);
      }
      App.renderChatMessages();
      try{await App.loadSuggestedQuestions();}catch(error){}

      if(String(App.elements.messageInput.value||'').trim()===questionText)App.elements.messageInput.value = '';
      try{await App.bumpSessionToTop(sessionId);await App.loadChatSessions();}catch(error){}
      if(App.authGatewayBase)App.clearPendingAnswer();
      App.state.currentSessionId = sessionId;
      App.renderSessionList();
      App.showToast(usedFast ? '送信しました（準拠省略）' : '送信しました', 'success');
      if (!(App.state.semanticMode && !usedFast)) {
        const relatedComments = relatedCommentsMerged;
        const relatedChunks = (msgRes && msgRes.relatedChunks) || [];
        App.logQaSearchEvent({
          search_mode: usedFast ? 'normal' : 'normal',
          query: questionText,
          comment_hit_count: Array.isArray(relatedComments) ? relatedComments.length : null,
          chunk_hit_count: Array.isArray(relatedChunks) ? relatedChunks.length : null,
          used_sources: (msgRes && (msgRes.usedSources || msgRes.used_sources)) || null,
          meta: { fast: !!usedFast }
        });
      }
    } catch (error) {
      if (!(error && error.name === 'AbortError')) {
        const st = error && error.httpStatus;
        let msg = (error && error.message) || '送信に失敗しました';
        if ((App.state.semanticMode && st === 503) || (error && error.code === 'semantic_disabled')) {
          msg =
            msg.indexOf('一時停止') >= 0
              ? msg
              : '意味検索は一時停止中です。通常検索（意味検索モードOFF）をご利用ください';
        } else if (st) {
          msg = msg + '（HTTP ' + st + '）';
        }
        App.showToast(msg, 'error');
      }
    } finally {
      App.state.pendingQuestionText = '';
      App.state.preferFastSummary = false;
      App.state.sendAbortController = null;
      App.renderAnswerJobStatus();
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
    const ok = await App.openConfirmDialog('ユーザ承認', 'ユーザID ' + userId + ' を承認しますか？');
    if (!ok) return;

    App.setLoading(true);
    try {
      await App.apiClient('PUT', '/admin/users/' + userId + '/approve');
      if (applicantEmail) {
        await App.notifyApprovalCompleted(applicantEmail);
      } else {
        console.warn('approval notify skipped: applicant email missing');
      }
      App.showToast('ユーザを承認しました', 'success');
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
      'ユーザ却下',
      'ユーザID ' + userId + ' を却下しますか？申請者へ却下メールを送信します。'
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
      App.showToast('ユーザを却下しました', 'success');
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
      App.showToast('承認するユーザを選択してください', 'error');
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
    if (!App.isStaffAdmin()) {
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
    if (!App.isStaffAdmin()) {
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

  importSrtTranscript: async () => {
    if (!App.isStaffAdmin()) {
      App.showToast('管理者のみ実行できます', 'error');
      return;
    }
    const title = String((document.getElementById('srtTitleInput') || {}).value || '').trim();
    const videoId = String((document.getElementById('srtVideoIdInput') || {}).value || '').trim();
    const videoUrl = String((document.getElementById('srtVideoUrlInput') || {}).value || '').trim();
    const instructor = String((document.getElementById('srtInstructorInput') || {}).value || '').trim();
    const fileInput = document.getElementById('srtFileInput');
    const file = fileInput && fileInput.files && fileInput.files[0] ? fileInput.files[0] : null;
    const resultEl = document.getElementById('srtImportResult');
    if (!title || !videoId) {
      App.showToast('タイトルと video_id は必須です', 'error');
      return;
    }
    if (!file) {
      App.showToast('SRTファイルを選択してください', 'error');
      return;
    }

    App.setLoading(true);
    if (resultEl) resultEl.textContent = '読み込み中…\n';
    try {
      const srtText = await file.text();
      if (!String(srtText || '').trim()) {
        throw new Error('SRTの内容が空です');
      }
      const cfg = await App.resolveSemanticConfig();
      const ingestUrl = String(cfg.url || '').replace(/semantic-search\/?$/, 'srt-ingest');
      if (!ingestUrl || ingestUrl === cfg.url) {
        throw new Error('SRT取込APIのURLを解決できませんでした');
      }
      if (resultEl) resultEl.textContent += 'Supabase へ送信中…\n';
      const response = await fetch(ingestUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Semantic-Shared-Secret': cfg.secret
        },
        body: JSON.stringify({
          title: title,
          video_id: videoId,
          video_url: videoUrl,
          instructor: instructor,
          srt_text: srtText
        })
      });
      const text = await response.text();
      let data = {};
      if (text) {
        try {
          data = JSON.parse(text);
        } catch (e) {
          data = { errorMessage: text.slice(0, 300) };
        }
      }
      if (!response.ok) {
        throw new Error(data.errorMessage || data.message || 'SRT取込失敗 HTTP ' + response.status);
      }

      const sourceKey = data.source_key || 'notta:' + videoId;
      const chunks = Array.isArray(data.chunks) ? data.chunks : [];
      if (resultEl) {
        resultEl.textContent +=
          'Supabase OK source_key=' +
          sourceKey +
          ' cues=' +
          (data.cue_count || 0) +
          ' chunks=' +
          (data.chunk_count || 0) +
          ' embedded=' +
          (data.embedded_count || 0) +
          '\n';
        if (data.embed_error) {
          resultEl.textContent += 'embed警告: ' + data.embed_error + '\n';
        }
        if (data.note) resultEl.textContent += data.note + '\n';
        resultEl.textContent += 'Raimo へ反映中…\n';
      }

      // Raimo knowledge（通常検索・一覧用）
      try {
        await App.apiClient('POST', '/admin/knowledge-sources/update', {
          source_key: sourceKey,
          source_kind: 'video',
          content_channel: 'seminar_video',
          title: title,
          video_id: videoId,
          video_url: videoUrl || '',
          instructor: instructor || '',
          origin_path: 'admin-upload:' + videoId + '.srt',
          meta_json: JSON.stringify({ ingest_via: 'srt-ingest' }),
          ingest_status: 'ready'
        });
      } catch (updateErr) {
        await App.apiClient('POST', '/admin/knowledge-sources', {
          source_key: sourceKey,
          source_kind: 'video',
          content_channel: 'seminar_video',
          title: title,
          video_id: videoId,
          video_url: videoUrl || '',
          instructor: instructor || '',
          origin_path: 'admin-upload:' + videoId + '.srt',
          meta_json: JSON.stringify({ ingest_via: 'srt-ingest' }),
          ingest_status: 'ready'
        });
      }
      try {
        await App.apiClient('POST', '/admin/knowledge-chunks/delete-by-source', {
          source_key: sourceKey
        });
      } catch (delErr) {
        if (resultEl) {
          resultEl.textContent +=
            'Raimo旧チャンク削除スキップ: ' + ((delErr && delErr.message) || delErr) + '\n';
        }
      }
      let raimoOk = 0;
      let raimoNg = 0;
      for (let i = 0; i < chunks.length; i += 1) {
        const c = chunks[i];
        try {
          await App.apiClient('POST', '/admin/knowledge-chunks', {
            chunk_key: c.chunk_key,
            source_key: sourceKey,
            start_sec: c.start_sec,
            end_sec: c.end_sec,
            speaker: c.speaker || '',
            content: c.content,
            search_text: c.search_text || c.content
          });
          raimoOk += 1;
        } catch (chunkErr) {
          raimoNg += 1;
          if (resultEl && raimoNg <= 5) {
            resultEl.textContent +=
              'Raimo chunk NG ' +
              (c.chunk_key || '') +
              ': ' +
              ((chunkErr && chunkErr.message) || chunkErr) +
              '\n';
          }
        }
      }
      if (resultEl) {
        resultEl.textContent +=
          'Raimo chunks OK=' + raimoOk + ' NG=' + raimoNg + '\n完了\n';
      }
      try {
        await App.loadKnowledge();
      } catch (e) {
        /* ignore */
      }
      App.showToast(
        'SRT取込完了（チャンク ' + (data.chunk_count || chunks.length) + '）',
        raimoNg === 0 ? 'success' : 'info'
      );
    } catch (error) {
      if (resultEl) resultEl.textContent += 'ERROR: ' + ((error && error.message) || error) + '\n';
      App.showToast((error && error.message) || 'SRT取込に失敗しました', 'error');
    } finally {
      App.setLoading(false);
    }
  },

  importCsvComments: async () => {
    if (!App.isStaffAdmin()) {
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
      let updateCount = 0;
      let failCount = 0;
      let junkSkipCount = 0;

      for (let i = 0; i < rows.length; i += 1) {
        const row = rows[i];
        try {
          const explicitId = App.csvCell(row, 'comment_id', 'commentId', 'コメントID', 'コメントid');
          let commentId = explicitId
            ? String(explicitId).trim()
            : 'csv-' + importBatchTs + '-' + i;
          if (commentId.indexOf('comment-') === 0) {
            commentId = commentId.slice(8).trim();
          }
          if (explicitId && !/^\d+$/.test(commentId) && !/^lesson_desc_/.test(commentId)) {
            junkSkipCount += 1;
            App.elements.importResult.textContent +=
              'SKIP junk_id row=' + (i + 1) + ' id=' + commentId + '\n';
            continue;
          }

          let contentStr = String(
            App.csvCell(row, 'content', '本文', 'Content', 'コメント内容', 'comment_body') || ''
          ).trim();
          contentStr = contentStr.replace(/^(続きを(見る|みる|読む)|もっと(見る|みる))\s*/g, '').trim();
          if (!contentStr) {
            skipCount += 1;
            App.elements.importResult.textContent +=
              'SKIP empty_body row=' + (i + 1) + ' id=' + commentId + '\n';
            continue;
          }
          const postedAt =
            App.csvCell(row, 'posted_at', 'postedAt', '日時', '投稿日時', '投稿日') || null;
          const authorName =
            App.csvCell(row, 'author_name', 'authorName', '投稿者名', '投稿者', 'author') || null;
          const composite = App.commentImportCompositeKey(contentStr, postedAt, authorName);
          const sourceType =
            App.csvCell(row, 'source_type', 'ソース', 'sourceType', 'データソース') ||
            (Object.prototype.hasOwnProperty.call(row, 'コメントID') &&
            Object.prototype.hasOwnProperty.call(row, 'コメント内容')
              ? '神大家コミュニティ'
              : 'WeStudy');
          const sourceSystem =
            App.csvCell(row, 'source_system', 'ソース系統', 'sourceSystem') || 'WeStudy';
          const sourceKind =
            App.csvCell(row, 'source_kind', 'ソース種別', 'sourceKind') || 'コミュニティ情報';
          const forumCategory =
            App.csvCell(row, 'forum_category', '分類', 'forumCategory', 'カテゴリ') || '未分類';
          const topicTitle =
            App.csvCell(row, 'topic_title', '板タイトル', 'topicTitle', 'トピック名') || null;
          const authorEmail =
            App.csvCell(row, 'author_email', 'authorEmail', '投稿者メール', 'メール') || null;
          const parentCommentId =
            App.csvCell(row, 'parent_comment_id', 'parentCommentId', '親コメントID', '親コメントid') ||
            null;
          const courseTab =
            App.csvCell(row, 'course_tab', 'コースタブ', 'courseTab') || null;
          const sectionName =
            App.csvCell(row, 'section_name', '目次セクション', 'sectionName') || null;
          const lessonTitle =
            App.csvCell(row, 'lesson_title', 'レッスンタイトル', 'lessonTitle') || null;
          const lessonUrl =
            App.csvCell(row, 'lesson_url', 'レッスンURL', 'lessonUrl') || null;
          const contentHash =
            App.csvCell(row, 'content_hash', 'コンテンツハッシュ', 'contentHash') || null;

          // comment_id が明示されているCSVは ID 優先で判定し、
          // 本文が短い既存行は長い本文で上書きする。
          const isDupById = dedupe.idSet.has(commentId);
          const isDupByComposite = !explicitId && dedupe.compositeSet.has(composite);
          if (isDupById) {
            const existing = (App.state.comments || []).find(function (c) {
              return String(c.comment_id || c.commentId || '').trim() === commentId;
            });
            const existingLen = existing
              ? String(App.commentField(existing, 'content') || '').trim().length
              : 0;
            const isLessonRow = /^lesson_desc_/.test(commentId) || sourceSystem === 'lesson';
            const existingCourseTab = existing
              ? String(App.commentField(existing, 'course_tab') || '').trim()
              : '';
            const needsMetaFill =
              isLessonRow &&
              (!existingCourseTab ||
                !String(App.commentField(existing, 'lesson_title') || '').trim()) &&
              !!(courseTab || sectionName || lessonTitle || lessonUrl);
            const longerBody = contentStr.length > existingLen + 20;
            if (longerBody || needsMetaFill) {
              await App.apiClient('POST', '/admin/comments/update-content', {
                comment_id: commentId,
                content: contentStr,
                posted_at: postedAt,
                author_name: authorName,
                author_email: authorEmail,
                source_type: sourceType,
                source_system: sourceSystem,
                source_kind: sourceKind,
                forum_category: forumCategory,
                topic_title: topicTitle,
                parent_comment_id: parentCommentId,
                course_tab: courseTab,
                section_name: sectionName,
                lesson_title: lessonTitle,
                lesson_url: lessonUrl,
                content_hash: contentHash
              });
              updateCount += 1;
              App.elements.importResult.textContent +=
                (longerBody ? 'UPDATE longer ' : 'UPDATE meta ') +
                'row=' +
                (i + 1) +
                ' id=' +
                commentId +
                (longerBody ? ' ' + existingLen + '→' + contentStr.length : '') +
                '\n';
              continue;
            }
            skipCount += 1;
            App.elements.importResult.textContent +=
              'SKIP dup row=' + (i + 1) + ' id=' + commentId + '\n';
            continue;
          }
          if (isDupByComposite) {
            skipCount += 1;
            App.elements.importResult.textContent +=
              'SKIP dup row=' + (i + 1) + ' id=' + commentId + '\n';
            continue;
          }

          await App.apiClient('POST', '/admin/comments', {
            source_type: sourceType,
            source_system: sourceSystem,
            source_kind: sourceKind,
            forum_category: forumCategory,
            topic_title: topicTitle,
            comment_id: commentId,
            posted_at: postedAt,
            author_name: authorName,
            author_email: authorEmail,
            content: contentStr,
            parent_comment_id: parentCommentId,
            ip_address:
              App.csvCell(row, 'ip_address', 'ipAddress', 'IPアドレス', 'IP アドレス', 'IP') || null,
            user_agent:
              App.csvCell(row, 'user_agent', 'userAgent', 'ユーザーエージェント', 'UA') || null,
            course_tab: courseTab,
            section_name: sectionName,
            lesson_title: lessonTitle,
            lesson_url: lessonUrl,
            content_hash: contentHash
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
        ' / 更新 ' +
        updateCount +
        ' / スキップ(重複) ' +
        skipCount +
        ' / ゴミID ' +
        junkSkipCount +
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

  /**
   * WeStudy 投稿者名「0089前田 行」「1345 佐伯澄人」→ 会員番号(4桁)と氏名に分離。
   * 先頭が4桁以外の数字のとき（例: 88 バンティング）は会員番号なし・全文を氏名側。
   */
  parseWeStudyAuthorName: (raw) => {
    const s = String(raw == null ? '' : raw).trim();
    if (!s) return { memberNo: '', authorName: '', raw: '' };
    const m = /^(\d{4})\s*(.*)$/.exec(s);
    if (m) {
      return {
        memberNo: m[1],
        authorName: String(m[2] || '').trim(),
        raw: s,
      };
    }
    return { memberNo: '', authorName: s, raw: s };
  },

  formatAuthorForDisplay: (raw) => {
    const p = App.parseWeStudyAuthorName(raw);
    if (p.memberNo && p.authorName) return p.memberNo + ' ' + p.authorName;
    if (p.memberNo) return p.memberNo;
    return p.authorName || p.raw || '';
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
