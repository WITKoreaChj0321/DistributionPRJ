/* =============================================================
   유통관리사 최빈출 기출 - frequent.js
   ============================================================= */
'use strict';

const API_BASE = '';

let kakaoLoggedIn = false;
let kakaoToken    = null;
let currentSubject = '전체';
let toastTimer    = null;

// DOM
const kakaoLoginArea  = document.getElementById('kakao-login-area');
const kakaoFriendArea = document.getElementById('kakao-friend-area');
const kakaoLogoutBtn  = document.getElementById('kakao-logout-btn');
const friendSelect    = document.getElementById('friend-select');
const userNameEl      = document.getElementById('user-name');
const userAvatarEl    = document.getElementById('user-avatar');
const freqList        = document.getElementById('frequent-list');
const countSelect     = document.getElementById('count-select');
const sendBtn         = document.getElementById('send-frequent-btn');
const toast           = document.getElementById('toast');
const toastIcon       = document.getElementById('toast-icon');
const toastMsg        = document.getElementById('toast-msg');

// ── INIT: 카카오 콜백 ──────────────────────────
(function init() {
  const p = new URLSearchParams(location.search);
  const token = p.get('token');
  if (token) {
    kakaoToken = token;
    onKakaoLogin({ nickname: p.get('nickname') || '카카오 사용자', profile_image: p.get('profile_image') || '' });
    history.replaceState({}, '', location.pathname);
  }
  if (p.get('error')) {
    showToast('카카오 로그인 실패: ' + p.get('error'), 'error');
    history.replaceState({}, '', location.pathname);
  }
  loadFrequent();
})();

// ── 카카오 ─────────────────────────────────────
function onKakaoLogin(info) {
  kakaoLoggedIn = true;
  userNameEl.textContent = info.nickname || '사용자';
  if (info.profile_image) userAvatarEl.innerHTML = `<img src="${info.profile_image}" alt="프로필" />`;
  kakaoLoginArea.classList.add('hidden');
  kakaoFriendArea.classList.remove('hidden');
  loadFriends();
  showToast(`${info.nickname || '사용자'}님 환영합니다!`, 'success');
}

kakaoLogoutBtn.addEventListener('click', () => {
  kakaoLoggedIn = false; kakaoToken = null;
  kakaoFriendArea.classList.add('hidden');
  kakaoLoginArea.classList.remove('hidden');
  showToast('로그아웃했습니다.', 'info');
});

async function loadFriends() {
  if (!kakaoToken) return;
  try {
    const res = await fetch(`${API_BASE}/api/kakao/friends?token=${encodeURIComponent(kakaoToken)}`);
    if (!res.ok) return;
    const data = await res.json();
    (data.friends || []).forEach((f) => {
      const o = document.createElement('option');
      o.value = f.uuid; o.textContent = f.nickname || '알 수 없음';
      friendSelect.appendChild(o);
    });
  } catch (e) { /* 친구 목록 없으면 나에게 보내기만 */ }
}

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

// ── 최빈출 로드 ────────────────────────────────
async function loadFrequent() {
  const top = countSelect ? countSelect.value : 20;
  freqList.innerHTML = '<p style="color:#94A3B8;font-size:.9rem;padding:20px 0;text-align:center;">불러오는 중...</p>';
  try {
    const res = await fetch(`${API_BASE}/api/frequent?top=${top}&subject=${encodeURIComponent(currentSubject)}`);
    if (!res.ok) throw new Error();
    const data = await res.json();
    renderFrequent(data.questions || []);
  } catch (e) {
    freqList.innerHTML = '<p style="color:#EF4444;font-size:.9rem;padding:20px 0;text-align:center;">불러오지 못했습니다. 서버 실행을 확인하세요.</p>';
  }
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

// ── 카카오 전송 ────────────────────────────────
let _sending = false;
sendBtn.addEventListener('click', async () => {
  if (_sending) return;
  if (!kakaoLoggedIn) { showToast('카카오 로그인이 필요합니다.', 'info'); return; }

  const top = countSelect ? parseInt(countSelect.value, 10) : 20;
  const friendUuid = friendSelect.value || 'me';
  try {
    _sending = true; sendBtn.disabled = true;
    const res = await fetch(`${API_BASE}/api/send-frequent`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ friend_uuid: friendUuid, token: kakaoToken || '', top, subject: currentSubject }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `전송 실패 (${res.status})`);
    }
    const data = await res.json();
    showToast(`${data.sent_count}문제를 카카오톡으로 전송했습니다!`, 'success');
  } catch (e) {
    showToast(e.message || '전송에 실패했습니다.', 'error');
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
