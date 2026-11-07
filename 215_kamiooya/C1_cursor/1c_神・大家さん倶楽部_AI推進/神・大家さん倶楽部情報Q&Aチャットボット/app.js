const App = {
  // Offline repair candidate: stay on the existing backend until an approved cutover.
  authGatewayBase: '', // Release publisher sets the verified gateway URL.
  // 公開 Edge URL（シークレットは /semantic-search-config から取得）
  semanticEdgeUrl: 'https://mwubzgefkkjjbingrmqu.supabase.co/functions/v1/semantic-search',
  _semanticSecret: null,

  state: {
    currentUser: null,
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

  isStaffAdmin: () => {
    const role = App.state.currentUser && App.state.currentUser.role;
    return role === 'admin' || role === 'master_admin';
  },

  isMasterAdmin: () => {
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
          try {
            await App.apiClient('POST', '/auth/register', payload);
            registered = true;
          } catch (regErr) {
            if (isReregisterCandidate(regErr)) {
              await App.apiClient('POST', '/auth/reregister', payload);
              registered = true;
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
              await App.apiClient('POST', '/auth/reregister', payload);
              registered = true;
              await App.notifyRegistrationPending(email, '再登録（アプリ）', memberNo, name, prefecture);
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
    App.elements.currentUserLabel.textContent = App.state.currentUser.email + ' (' + App.state.currentUser.role + ')';

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
    App.state.currentUser = null;
    App.state.currentSessionId = null;
    App.state.chatSessions = [];
    App.state.chatMessages = [];
    App.state.suggestedQuestions = [];
    App.state.comments = [];App.state.referenceReady={};App.state.referenceLoads={};
    App.state.pendingUsers = [];
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
      adminAnalytics: 'adminAnalyticsScreen'
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
          App.escapeHtml(snippet) + '<span class="openchat-attachment-slot" data-openchat-source-id="'+App.escapeHtml(rowId)+'"></span>' +
          '</td></tr>'
        );
      })
      .join('');
    tbody.querySelectorAll('.openchat-attachment-slot').forEach(function(container){
      App.appendAttachmentLinks(container,container.getAttribute('data-openchat-source-id'),'添付：','openchat');
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
        if(part.length<500)break;
        after=previous;
        if(page===99)throw new Error('コメント一覧の上限を超えました');
      }
    }else{const res=await App.apiClient('GET','/comments');rows=(res&&res.comments)||[];}
    if(!current())return;
    rows.sort((a,b)=>String(b.posted_at||'').localeCompare(String(a.posted_at||''))||Number(b.id)-Number(a.id));
    App.state.comments = rows.map(App.enrichCommentCategory);
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

  updateSemanticModeButton: () => {
    const btn = App.elements.semanticModeToggle;
    if (!btn) return;
    const on = !!App.state.semanticMode;
    btn.textContent = '意味検索モード: ' + (on ? 'ON' : 'OFF');
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
    const attrs=c=>' id="'+esc(App.citationAnchor(c,messageId))+'" class="mb-2 scroll-mt-4"';
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
        return '<li class="mb-1">'+anchor+' ・ '+(u?'<a class="text-blue-700 underline" target="_blank" rel="noopener noreferrer" href="'+esc(u)+'">'+title+(page?' 元動画ページを開く':' から再生')+'</a>':title)+'</li>';
      }
      if(c.kind==='lesson')return '<li class="mb-1">'+anchor+' ・ '+esc(c.lessonTitle||c.topicTitle||'講座ページ')+db('lesson',c.commentId)+'</li>';
      return '<li class="mb-1">'+anchor+' ・ '+esc(App.citationDateLabel(c))+db(c.kind,c.commentId||c.openchatId)+'</li>';
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
      return '<li'+attrs(c)+'>'+badge(c)+esc(App.citationDateLabel(c))+' ・ '+esc(App.formatAuthorForDisplay(c.authorName||''))+cat+' #'+esc(c.commentId||'')+db('comment',c.commentId)+'<div class="text-slate-600">'+esc(c.snippet||'')+'</div><span class="citation-attachments" data-comment-id="'+esc(c.commentId||'')+'"></span></li>';
    }));
    if(lines.length)parts.push('<div class="font-semibold mb-1">LINEオプチャの根拠</div>'+dated(lines,c=>{
      const d=App.referenceDateParts(c.postedAt);
      return '<li'+attrs(c)+'>'+badge(c)+(d?esc(d.label)+' ・ ':'')+esc(c.chatTitle||'オプチャ名未登録')+(c.streamLabel?' / '+esc(c.streamLabel):'')+(c.threadTitle?' / '+esc(c.threadTitle):'')+db('openchat',c.openchatId)+'<div class="text-slate-600">'+esc(c.snippet||'')+'</div><div class="openchat-citation-attachments" data-openchat-source-id="'+esc(c.openchatId||'')+'"></div></li>';
    }));
    if(lessons.length)parts.push('<div class="font-semibold mb-1">講座ページの根拠</div><ul class="citations-list mb-2">'+lessons.map(c=>{
      const url=App.safeReferenceUrl(c.lessonUrl);
      return '<li'+attrs(c)+'>'+badge(c)+esc(c.lessonTitle||c.topicTitle||c.commentId||'講座')+db('lesson',c.commentId)+(url?' <a class="text-blue-700 underline" target="_blank" rel="noopener noreferrer" href="'+esc(url)+'">講座を開く</a>':'')+'<div class="text-slate-600">'+esc(c.snippet||'')+'</div></li>';
    }).join('')+'</ul>');
    const note=citations.some(c=>c.referenceSelection==='provided-context')?'<p class="text-slate-600 mb-2">回答作成時の参考候補です。本文中の使用箇所が明示されていない情報も含みます。</p>':'';
    return '<div class="citations-panel mt-3 border-t pt-2 text-xs">'+note+parts.join('')+'</div>';
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
    App.renderPendingUsers();
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
        (m.role === 'assistant' ? App.renderCitationsPanel(messageCitations, msgId, m.content) : '');

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
    area.scrollTop = area.scrollHeight;
    area.querySelectorAll('.citation-attachments').forEach(function (container) {
      App.appendAttachmentLinks(container, container.getAttribute('data-comment-id'), '関連添付：');
    });
    area.querySelectorAll('.openchat-citation-attachments').forEach(function(container){
      App.appendAttachmentLinks(container,container.getAttribute('data-openchat-source-id'),'関連添付：','openchat');
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
          if(App.elements.commentDetailDialog&&App.elements.commentDetailDialog.open&&App.elements.commentDetailBody&&App.state.attachmentDetailCommentId)App.appendAttachmentLinks(App.elements.commentDetailBody,App.state.attachmentDetailCommentId);
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

  attachmentDisplayName: (item) => {
    const name = String(item.original_name || '').trim();
    if (name && !/^(image|video|audio|file)$/i.test(name)) return name;
    const kind = String(item.content_type || item.mime_type || item.mime || '').split('/')[0] || name.toLowerCase();
    const label = { image: '画像', video: '動画', audio: '音声' }[kind] || '添付ファイル';
    return label + '（ファイル名未取得）';
  },

  appendAttachmentLinks: (container, commentId, label, source) => {
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
    items.forEach(function (item) {
      const link = document.createElement('a');
      link.href = '#attachment-' + String(item.id);
      link.className = 'block text-blue-700 hover:underline break-all';
      link.textContent = App.attachmentDisplayName(item);
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
      App.appendAttachmentLinks(contentTd, App.commentField(r, 'comment_id'));

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
      App.appendAttachmentLinks(App.elements.commentDetailBody, cid);
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
          error_message: payload.error_message || null
        })
      });
    } catch (e) {
      /* analytics must not break chat */
    }
  },

  // Phase 13: 運営分析ダッシュボード（qa-analytics Edge）
  loadAnalytics: async () => {
    if (!App.isStaffAdmin()) return;
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
      '<div class="bg-white rounded border p-3"><div class="text-xs text-slate-500">通常検索</div><div class="text-2xl font-semibold">' +
      App.escapeHtml(String(t.normal || 0)) +
      '</div><div class="text-xs text-slate-500 mt-1">' +
      App.escapeHtml(pct(t.normal_ratio)) +
      '</div></div>' +
      '<div class="bg-white rounded border p-3 border-blue-200"><div class="text-xs text-blue-700">意味検索</div><div class="text-2xl font-semibold text-blue-900">' +
      App.escapeHtml(String(t.semantic || 0)) +
      '</div><div class="text-xs text-blue-600 mt-1">' +
      App.escapeHtml(pct(t.semantic_ratio)) +
      '</div></div>' +
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
          '<div class="text-xs text-slate-500 mt-1">通常 ' +
          App.escapeHtml(String(g.billable_normal || 0)) +
          ' / 意味 ' +
          App.escapeHtml(String(g.billable_semantic || 0)) +
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
          const nw = ((n / maxDaily) * 100).toFixed(1);
          const sw = ((s / maxDaily) * 100).toFixed(1);
          return (
            '<div>' +
            '<div class="flex justify-between text-xs text-slate-500 mb-1">' +
            '<span>' +
            App.escapeHtml(d.day || '') +
            '</span>' +
            '<span>通常 ' +
            n +
            ' / 意味 ' +
            s +
            '（計 ' +
            (Number(d.total) || n + s) +
            '）</span>' +
            '</div>' +
            '<div class="flex h-3 rounded-full overflow-hidden bg-slate-100 border">' +
            '<div class="bg-slate-400" style="width:' +
            nw +
            '%" title="通常 ' +
            n +
            '"></div>' +
            '<div class="bg-blue-600" style="width:' +
            sw +
            '%" title="意味 ' +
            s +
            '"></div>' +
            '</div></div>'
          );
        })
        .join('');
    }

    const top = data.top_queries || [];
    topBody.innerHTML =
      top.length === 0
        ? '<tr><td class="p-2 text-slate-500" colspan="4">なし</td></tr>'
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
                App.escapeHtml(String(q.normal || 0)) +
                '</td>' +
                '<td class="p-2">' +
                App.escapeHtml(String(q.semantic || 0)) +
                '</td></tr>'
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
              const modeLabel = mode === 'semantic' ? '意味' : mode === 'normal' ? '通常' : mode;
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
      card('Gemini 費用（期間）', yen(m.total_jpy_low) + '〜' + yen(m.total_jpy_high), '通常検索の幅で上下') +
      card('1問あたり', perQ, '試算は1.5〜6円') +
      card('意味検索 1問の実費', semPerQ, '実測 ' + num(m.semantic_metered) + ' 問') +
      '</div>' +
      '<table class="w-full text-xs mt-2"><thead class="bg-slate-50 text-slate-600"><tr>' +
      '<th class="p-2 text-left">週</th><th class="p-2 text-right">質問</th><th class="p-2 text-right">通常</th>' +
      '<th class="p-2 text-right">意味</th><th class="p-2 text-right">利用者</th>' +
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
          '円。週の利用者数は通常・意味の多い方。'
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
    box.classList.toggle('hidden',!App.state.answerJobStatus);text.textContent=App.state.answerJobStatus;
    button.classList.toggle('hidden',!!App.state.sendAbortController);button.disabled=!!App.state.sendAbortController;
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
        if(state.status==='done'&&state.result)return state.result;
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
    App.state.semanticMode=pending.mode==='semantic';App.updateSemanticModeButton();
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
            const mode=pending?pending.mode:(fast?'fast':App.state.semanticMode?'semantic':'normal');
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
