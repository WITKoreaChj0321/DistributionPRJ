/* =============================================================
   유통관리사 최빈출 기출 - frequent.js
   ============================================================= */
'use strict';

const API_BASE = '';

// ⚠️ 카카오 JavaScript 키 (콘솔 → 앱 → 앱 키 → JavaScript 키)
const KAKAO_JS_KEY = 'YOUR_KAKAO_JAVASCRIPT_KEY';

let kakaoLoggedIn = false;
let currentSubject = '전체';
let toastTimer    = null;
let _allQuestions = null;   // 정적 JSON 캐시 (서버 불필요)

// 카카오 SDK 초기화
function initKakao() {
  if (window.Kakao && KAKAO_JS_KEY && KAKAO_JS_KEY !== 'YOUR_KAKAO_JAVASCRIPT_KEY') {
    if (!Kakao.isInitialized()) Kakao.init(KAKAO_JS_KEY);
    return true;
  }
  return false;
}

// DOM
const kakaoLoginArea  = document.getElementById('kakao-login-area');
const kakaoFriendArea = document.getElementById('kakao-friend-area');
const kakaoLogoutBtn  = document.getElementById('kakao-logout-btn');
const userNameEl      = document.getElementById('user-name');
const userAvatarEl    = document.getElementById('user-avatar');
const freqList        = document.getElementById('frequent-list');
const countSelect     = document.getElementById('count-select');
const sendBtn         = document.getElementById('send-frequent-btn');
const toast           = document.getElementById('toast');
const toastIcon       = document.getElementById('toast-icon');
const toastMsg        = document.getElementById('toast-msg');

// ── INIT ───────────────────────────────────────
(function init() {
  initKakao();
  // 이미 로그인된 세션 복원
  if (window.Kakao && Kakao.isInitialized() && Kakao.Auth.getAccessToken()) {
    fetchKakaoProfile();
  }
  loadFrequent();
})();

// ── 카카오 로그인 (JS SDK, 서버 없이) ───────────
document.getElementById('kakao-login-btn').addEventListener('click', () => {
  if (!initKakao()) {
    showToast('카카오 JavaScript 키가 설정되지 않았습니다.', 'error');
    return;
  }
  Kakao.Auth.login({
    scope: 'profile_nickname,profile_image,talk_message',
    success: () => fetchKakaoProfile(),
    fail: (err) => showToast('카카오 로그인 실패: ' + (err.error_description || JSON.stringify(err)), 'error'),
  });
});

function fetchKakaoProfile() {
  Kakao.API.request({
    url: '/v2/user/me',
    success: (res) => {
      const p = (res.kakao_account && res.kakao_account.profile) || {};
      onKakaoLogin({ nickname: p.nickname || '카카오 사용자', profile_image: p.profile_image_url || '' });
    },
    fail: () => onKakaoLogin({ nickname: '카카오 사용자', profile_image: '' }),
  });
}

function onKakaoLogin(info) {
  kakaoLoggedIn = true;
  userNameEl.textContent = info.nickname || '사용자';
  if (info.profile_image) userAvatarEl.innerHTML = `<img src="${info.profile_image}" alt="프로필" />`;
  kakaoLoginArea.classList.add('hidden');
  kakaoFriendArea.classList.remove('hidden');
  showToast(`${info.nickname || '사용자'}님 환영합니다!`, 'success');
}

kakaoLogoutBtn.addEventListener('click', () => {
  if (window.Kakao && Kakao.Auth.getAccessToken()) Kakao.Auth.logout();
  kakaoLoggedIn = false;
  kakaoFriendArea.classList.add('hidden');
  kakaoLoginArea.classList.remove('hidden');
  showToast('로그아웃했습니다.', 'info');
});

// ── 과목 탭 ────────────────────────────────────
document.querySelectorAll('.subject-tab').forEach((tab) => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.subject-tab').forEach((t) => t.classList.remove('active'));
    tab.classList.add('active');
    currentSubject = tab.dataset.subject;
    loadFrequent();
  });
});

countSelect.addEventListener('change', loadFrequent);

// ── 최빈출 데이터 로드 (정적 JSON, 서버 불필요) ──
async function fetchAllQuestions() {
  if (_allQuestions) return _allQuestions;
  // 여러 경로 시도: GitHub Pages(상대) → 로컬 서버(/static) → API 폴백
  const urls = ['data/frequent.json', '/static/data/frequent.json'];
  for (const u of urls) {
    try {
      const r = await fetch(u);
      if (r.ok) {
        const d = await r.json();
        _allQuestions = d.questions || [];
        return _allQuestions;
      }
    } catch (e) { /* 다음 경로 */ }
  }
  // 최후 폴백: 서버 API (실시간 계산)
  try {
    const r = await fetch(`${API_BASE}/api/frequent?top=1000`);
    if (r.ok) { _allQuestions = (await r.json()).questions || []; return _allQuestions; }
  } catch (e) { /* */ }
  return null;
}

// ── 최빈출 표시 (과목·개수 필터는 브라우저에서) ──
async function loadFrequent() {
  freqList.innerHTML = '<p style="color:#94A3B8;font-size:.9rem;padding:20px 0;text-align:center;">불러오는 중...</p>';
  const all = await fetchAllQuestions();
  if (!all) {
    freqList.innerHTML = '<p style="color:#EF4444;font-size:.9rem;padding:20px 0;text-align:center;">데이터를 불러오지 못했습니다.</p>';
    return;
  }
  const top = countSelect ? parseInt(countSelect.value, 10) : 20;
  let filtered = currentSubject === '전체'
    ? all
    : all.filter((q) => q.subject === currentSubject);
  renderFrequent(filtered.slice(0, top));
}

function renderFrequent(items) {
  freqList.innerHTML = '';
  if (!items.length) {
    freqList.innerHTML = '<p style="color:#94A3B8;font-size:.9rem;padding:20px 0;text-align:center;">데이터가 없습니다.</p>';
    return;
  }
  items.forEach((q, i) => {
    const card = document.createElement('div');
    card.className = 'similar-card';
    card.innerHTML = `
      <div class="similar-card-header">
        <div class="similar-meta">
          <span class="badge badge-subject">${escapeHtml(q.subject || '')}</span>
          <span class="badge badge-year">${q.frequency}개년 반복</span>
        </div>
        <span class="similarity-badge">TOP ${i + 1}</span>
      </div>
      <p class="similar-qtext">${escapeHtml(q.question_text || '')}</p>
      <p class="similar-answer-line">&#10003; 정답: ${escapeHtml(q.answer_content || '')}</p>`;
    freqList.appendChild(card);
  });
}

// ── 카카오 메시지 빌더 (서버 kakao.py 포팅) ──────
function buildFrequentMessages(items) {
  const msgs = [
    `🔥 유통관리사 최빈출 기출문제\n\n여러 해 반복 출제된 핵심 ${items.length}문제를 보내드립니다.`,
  ];
  items.forEach((q) => {
    let body = (q.question_text || '').trim();
    const head = `🔥 최빈출 [${q.subject}] ${q.frequency}개년 반복`;
    const ansLine = `✅ 정답: ${q.answer_content || ''}`;
    const maxBody = Math.max(0, 190 - head.length - ansLine.length - 6);
    if (body.length > maxBody) body = body.slice(0, Math.max(0, maxBody - 3)) + '...';
    msgs.push(`${head}\n\n${body}\n\n${ansLine}`);
  });
  return msgs;
}

// 카카오 memo(나에게 보내기) 1건 — Promise 래핑
function sendMemo(text) {
  return new Promise((resolve, reject) => {
    Kakao.API.request({
      url: '/v2/api/talk/memo/default/send',
      data: {
        template_object: JSON.stringify({
          object_type: 'text',
          text,
          link: { web_url: 'https://www.comcbt.com', mobile_web_url: 'https://www.comcbt.com' },
          button_title: '기출문제 더 풀기',
        }),
      },
      success: resolve,
      fail: reject,
    });
  });
}

// ── 카카오 전송 (JS SDK, 서버 없이) ─────────────
let _sending = false;
sendBtn.addEventListener('click', async () => {
  if (_sending) return;
  if (!kakaoLoggedIn) { showToast('카카오 로그인이 필요합니다.', 'info'); return; }

  const top = countSelect ? parseInt(countSelect.value, 10) : 20;
  const all = await fetchAllQuestions();
  if (!all) { showToast('데이터를 불러오지 못했습니다.', 'error'); return; }
  let items = currentSubject === '전체' ? all : all.filter((q) => q.subject === currentSubject);
  items = items.slice(0, top);

  const messages = buildFrequentMessages(items);
  try {
    _sending = true; sendBtn.disabled = true;
    let sent = 0;
    for (const text of messages) {
      await sendMemo(text);
      sent++;
    }
    showToast(`${items.length}문제를 카카오톡으로 전송했습니다!`, 'success');
  } catch (e) {
    const detail = (e && (e.msg || e.error_description)) || JSON.stringify(e);
    showToast('전송 실패: ' + detail, 'error');
  } finally {
    _sending = false; sendBtn.disabled = false;
  }
});

// ── TOAST / UTIL ───────────────────────────────
function showToast(msg, type = 'info') {
  const icons = { success: '✓', error: '✕', info: 'ℹ' };
  toastIcon.textContent = icons[type] || '';
  toastMsg.textContent = msg;
  toast.className = `toast ${type}`;
  void toast.offsetWidth;
  toast.classList.add('show');
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 3200);
}

function escapeHtml(str) {
  if (typeof str !== 'string') return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}
