/* =============================================================
   유통관리사 오답 분석기 - app.js
   ============================================================= */

'use strict';

// ---------------------------------------------------------------
// CONFIG
// ---------------------------------------------------------------
const API_BASE = '';           // 백엔드 동일 origin 기준 (필요 시 변경)
const POLL_INTERVAL_MS = 2000; // 폴링 간격
const POLL_MAX_TRIES   = 60;   // 최대 2분

// ---------------------------------------------------------------
// DOM REFS
// ---------------------------------------------------------------
const uploadArea      = document.getElementById('upload-area');
const fileInput       = document.getElementById('file-input');
const uploadBtn       = document.getElementById('upload-btn');
const changeFileBtn   = document.getElementById('change-file-btn');
const uploadPlaceholder = document.getElementById('upload-placeholder');
const uploadPreview   = document.getElementById('upload-preview');
const previewImg      = document.getElementById('preview-img');
const previewInfo     = document.getElementById('preview-info');
const analyzeBtn      = document.getElementById('analyze-btn');

const sectionUpload   = document.getElementById('section-upload');
const sectionKakao    = document.getElementById('section-kakao');
const sectionProgress = document.getElementById('section-progress');
const sectionResults  = document.getElementById('section-results');

const kakaoLoginArea  = document.getElementById('kakao-login-area');
const kakaoFriendArea = document.getElementById('kakao-friend-area');
const kakaoLoginBtn   = document.getElementById('kakao-login-btn');
const kakaoLogoutBtn  = document.getElementById('kakao-logout-btn');
const skipKakaoBtn    = document.getElementById('skip-kakao-btn');
const sendKakaoBtn    = document.getElementById('send-kakao-btn');
const resendKakaoBtn  = document.getElementById('resend-kakao-btn');
const restartBtn      = document.getElementById('restart-btn');
const friendSelect    = document.getElementById('friend-select');
const userNameEl      = document.getElementById('user-name');
const userAvatarEl    = document.getElementById('user-avatar');

const progressFill    = document.getElementById('progress-fill');
const progressStatus  = document.getElementById('progress-status');
const progOcr         = document.getElementById('prog-ocr');
const progDetect      = document.getElementById('prog-detect');
const progSimilar     = document.getElementById('prog-similar');

const wrongCountEl    = document.getElementById('wrong-count');
const similarCountEl  = document.getElementById('similar-count');
const wrongList       = document.getElementById('wrong-list');
const similarList     = document.getElementById('similar-list');

const toast           = document.getElementById('toast');
const toastIcon       = document.getElementById('toast-icon');
const toastMsg        = document.getElementById('toast-msg');

const step1El = document.getElementById('step-1');
const step2El = document.getElementById('step-2');
const step3El = document.getElementById('step-3');
const stepLines = document.querySelectorAll('.step-line');

// ---------------------------------------------------------------
// STATE
// ---------------------------------------------------------------
let selectedFile   = null;
let currentTaskId  = null;
let pollTimer      = null;
let kakaoLoggedIn  = false;
let kakaoToken     = null;  // OAuth 후 발급된 액세스 토큰
let resultData     = null;

// ---------------------------------------------------------------
// INIT
// ---------------------------------------------------------------
(function init() {
  // 카카오 OAuth 콜백 체크: 서버가 /?token={access_token} 으로 리다이렉트
  const params = new URLSearchParams(window.location.search);
  const token = params.get('token');
  const error = params.get('error');

  if (token) {
    kakaoToken = token;
    handleKakaoLoginSuccess({
      nickname:      params.get('nickname')      || '카카오 사용자',
      profile_image: params.get('profile_image') || '',
    });
    history.replaceState({}, '', window.location.pathname);
  }
  if (error) {
    showToast('카카오 로그인에 실패했습니다: ' + (error || ''), 'error');
    history.replaceState({}, '', window.location.pathname);
  }
})();

// ---------------------------------------------------------------
// STEP INDICATOR
// ---------------------------------------------------------------
function setStep(num) {
  const steps  = [step1El, step2El, step3El];
  steps.forEach((el, i) => {
    el.classList.remove('active', 'done');
    if (i + 1 < num)  el.classList.add('done');
    if (i + 1 === num) el.classList.add('active');
  });
  stepLines.forEach((line, i) => {
    line.classList.toggle('done', i + 1 < num);
  });
}

// ---------------------------------------------------------------
// FILE UPLOAD
// ---------------------------------------------------------------
uploadArea.addEventListener('click', (e) => {
  if (e.target === changeFileBtn || changeFileBtn.contains(e.target)) return;
  fileInput.click();
});

uploadBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  fileInput.click();
});

changeFileBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  fileInput.click();
});

fileInput.addEventListener('change', () => {
  if (fileInput.files.length > 0) {
    handleFile(fileInput.files[0]);
  }
});

// Drag & Drop
uploadArea.addEventListener('dragover', (e) => {
  e.preventDefault();
  uploadArea.classList.add('dragover');
});

uploadArea.addEventListener('dragleave', () => {
  uploadArea.classList.remove('dragover');
});

uploadArea.addEventListener('drop', (e) => {
  e.preventDefault();
  uploadArea.classList.remove('dragover');
  const file = e.dataTransfer.files[0];
  if (file) handleFile(file);
});

function handleFile(file) {
  if (!file.type.startsWith('image/')) {
    showToast('이미지 파일만 업로드할 수 있습니다.', 'error');
    return;
  }
  if (file.size > 20 * 1024 * 1024) {
    showToast('파일 크기는 20MB 이하여야 합니다.', 'error');
    return;
  }

  selectedFile = file;
  const reader = new FileReader();
  reader.onload = (e) => {
    previewImg.src = e.target.result;
    const sizeStr = formatBytes(file.size);
    previewInfo.textContent = `${file.name} · ${sizeStr}`;
    uploadPlaceholder.classList.add('hidden');
    uploadPreview.classList.remove('hidden');
    analyzeBtn.disabled = false;
  };
  reader.readAsDataURL(file);
}

function formatBytes(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// ---------------------------------------------------------------
// ANALYZE
// ---------------------------------------------------------------
analyzeBtn.addEventListener('click', async () => {
  if (!selectedFile) return;
  try {
    analyzeBtn.disabled = true;
    analyzeBtn.querySelector('.btn-text').textContent = '전송 중...';

    const formData = new FormData();
    formData.append('image', selectedFile);

    const res = await fetch(`${API_BASE}/api/analyze`, {
      method: 'POST',
      body: formData
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.message || `서버 오류 (${res.status})`);
    }

    const data = await res.json();
    currentTaskId = data.task_id;

    // 카카오 섹션으로 이동
    showSection('kakao');
    setStep(2);
  } catch (err) {
    showToast(err.message || '업로드에 실패했습니다.', 'error');
    analyzeBtn.disabled = false;
    analyzeBtn.querySelector('.btn-text').textContent = '오답 분석 시작';
  }
});

// ---------------------------------------------------------------
// SECTION VISIBILITY
// ---------------------------------------------------------------
function showSection(name) {
  sectionUpload.classList.add('hidden');
  sectionKakao.classList.add('hidden');
  sectionProgress.classList.add('hidden');
  sectionResults.classList.add('hidden');

  if (name === 'upload')    sectionUpload.classList.remove('hidden');
  if (name === 'kakao')     sectionKakao.classList.remove('hidden');
  if (name === 'progress')  sectionProgress.classList.remove('hidden');
  if (name === 'results')   sectionResults.classList.remove('hidden');

  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ---------------------------------------------------------------
// KAKAO LOGIN
// ---------------------------------------------------------------
kakaoLoginBtn.addEventListener('click', () => {
  window.location.href = `${API_BASE}/auth/kakao`;
});

kakaoLogoutBtn.addEventListener('click', () => {
  kakaoLoggedIn = false;
  kakaoFriendArea.classList.add('hidden');
  kakaoLoginArea.classList.remove('hidden');
  showToast('로그아웃했습니다.', 'info');
});

function handleKakaoLoginSuccess(userInfo) {
  kakaoLoggedIn = true;
  userNameEl.textContent = userInfo.nickname || '사용자';

  if (userInfo.profile_image) {
    userAvatarEl.innerHTML = `<img src="${userInfo.profile_image}" alt="프로필" />`;
  }

  kakaoLoginArea.classList.add('hidden');
  kakaoFriendArea.classList.remove('hidden');

  loadFriends();
  showToast(`${userInfo.nickname || '사용자'}님, 환영합니다!`, 'success');
}

// ---------------------------------------------------------------
// LOAD FRIENDS
// ---------------------------------------------------------------
async function loadFriends() {
  if (!kakaoToken) return;
  try {
    const res = await fetch(`${API_BASE}/api/kakao/friends?token=${encodeURIComponent(kakaoToken)}`);
    if (!res.ok) throw new Error('친구 목록을 불러오지 못했습니다.');
    const data = await res.json();

    // 기존 나에게 보내기 옵션 유지, 친구 추가
    const friends = data.friends || [];
    friends.forEach((friend) => {
      const opt = document.createElement('option');
      opt.value = friend.uuid;
      opt.textContent = friend.nickname || '알 수 없음';  // API 응답 필드명: nickname
      friendSelect.appendChild(opt);
    });
  } catch (err) {
    // 친구 목록 실패는 무시 (나에게 보내기만 사용 가능)
    console.warn('친구 목록 로드 실패:', err.message);
  }
}

friendSelect.addEventListener('change', () => {
  sendKakaoBtn.disabled = !friendSelect.value;
});

// ---------------------------------------------------------------
// KAKAO SEND
// ---------------------------------------------------------------
sendKakaoBtn.addEventListener('click', () => startAnalysisWithKakao());
skipKakaoBtn.addEventListener('click', () => startAnalysisWithKakao());
resendKakaoBtn.addEventListener('click', () => sendToKakao());

async function startAnalysisWithKakao() {
  showSection('progress');
  setStep(3);
  startPolling();
}

async function sendToKakao() {
  if (!currentTaskId) {
    showToast('분석 결과가 없습니다.', 'error');
    return;
  }
  if (!kakaoLoggedIn) {
    showSection('kakao');
    setStep(2);
    return;
  }

  const friendUuid = friendSelect.value || 'me';

  try {
    resendKakaoBtn.disabled = true;
    const res = await fetch(`${API_BASE}/api/send-kakao`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: currentTaskId, friend_uuid: friendUuid, token: kakaoToken || '' })
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.message || `전송 실패 (${res.status})`);
    }

    showToast('카카오톡으로 전송했습니다!', 'success');
  } catch (err) {
    showToast(err.message || '카카오톡 전송에 실패했습니다.', 'error');
  } finally {
    resendKakaoBtn.disabled = false;
  }
}

// ---------------------------------------------------------------
// POLLING
// ---------------------------------------------------------------
function startPolling() {
  let tries = 0;
  setProgress(5, 'AI가 이미지를 분석하고 있습니다...');
  setProgStep('ocr');

  pollTimer = setInterval(async () => {
    tries++;
    if (tries > POLL_MAX_TRIES) {
      clearInterval(pollTimer);
      showToast('분석 시간이 초과되었습니다. 다시 시도해 주세요.', 'error');
      showSection('upload');
      setStep(1);
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/api/result/${currentTaskId}`);
      if (!res.ok) throw new Error(`결과 조회 실패 (${res.status})`);
      const data = await res.json();

      handlePollResponse(data);
    } catch (err) {
      console.warn('폴링 오류:', err.message);
    }
  }, POLL_INTERVAL_MS);
}

function handlePollResponse(data) {
  const { status } = data;

  if (status === 'ocr') {
    setProgress(25, '문자를 인식하고 있습니다...');
    setProgStep('ocr');
  } else if (status === 'detecting') {
    setProgress(55, '오답을 탐지하고 있습니다...');
    setProgStep('detect');
  } else if (status === 'searching') {
    setProgress(80, '유사 기출문제를 검색하고 있습니다...');
    setProgStep('similar');
  } else if (status === 'done' || status === 'completed') {
    setProgress(100, '분석이 완료되었습니다!');
    setProgStep('done');
    clearInterval(pollTimer);

    setTimeout(() => {
      resultData = data;
      renderResults(data);
      showSection('results');

      // 카카오 로그인 상태면 자동 전송
      if (kakaoLoggedIn && friendSelect.value) {
        sendToKakao();
      }
    }, 600);
  } else if (status === 'error' || status === 'failed') {
    clearInterval(pollTimer);
    showToast(data.message || '분석 중 오류가 발생했습니다.', 'error');
    showSection('upload');
    setStep(1);
  }
}

function setProgress(pct, msg) {
  progressFill.style.width = pct + '%';
  progressStatus.textContent = msg;
}

function setProgStep(active) {
  const map = { ocr: progOcr, detect: progDetect, similar: progSimilar };
  // 이전 단계 done 처리
  const order = ['ocr', 'detect', 'similar'];
  const idx = order.indexOf(active);
  order.forEach((key, i) => {
    const el = map[key];
    if (!el) return;
    el.classList.remove('active', 'done');
    if (active === 'done') {
      el.classList.add('done');
    } else if (i < idx) {
      el.classList.add('done');
    } else if (i === idx) {
      el.classList.add('active');
    }
  });
}

// ---------------------------------------------------------------
// RENDER RESULTS
// ---------------------------------------------------------------
function renderResults(data) {
  const wrong   = data.wrong_questions   || [];
  const similar = data.similar_questions || [];

  wrongCountEl.textContent   = wrong.length;
  similarCountEl.textContent = similar.length;

  renderWrongQuestions(wrong);
  renderSimilarQuestions(similar);
}

function renderWrongQuestions(list) {
  wrongList.innerHTML = '';
  if (list.length === 0) {
    wrongList.innerHTML = '<p style="color:#9E9E9E;font-size:.9rem;padding:8px 0;">오답이 발견되지 않았습니다.</p>';
    return;
  }
  list.forEach((q) => {
    const card = document.createElement('div');
    card.className = 'wrong-card';
    card.innerHTML = `
      <div class="wrong-card-header">
        <span class="wrong-qnum">${q.question_num}번</span>
        <span class="wrong-qtext">${escapeHtml(q.question_text || '')}</span>
      </div>
      <div class="wrong-answers">
        <span class="wrong-your">내 답: ${q.your_answer}번</span>
        <span class="wrong-correct">정답: ${q.correct_answer}번</span>
      </div>
    `;
    wrongList.appendChild(card);
  });
}

function renderSimilarQuestions(list) {
  similarList.innerHTML = '';
  if (list.length === 0) {
    similarList.innerHTML = '<p style="color:#9E9E9E;font-size:.9rem;padding:8px 0;">유사 기출문제가 없습니다.</p>';
    return;
  }
  list.forEach((q, idx) => {
    const pct = Math.round((q.similarity || 0) * 100);
    const card = document.createElement('div');
    card.className = 'similar-card';

    const optionsHtml = (q.options || []).map((opt, i) => {
      const isAnswer = (i + 1) === q.answer;
      return `<li class="${isAnswer ? 'is-answer' : ''}">${escapeHtml(opt)}</li>`;
    }).join('');

    const hasExplanation = q.explanation && q.explanation.trim();
    const explanationHtml = hasExplanation
      ? `<button class="explanation-toggle" data-idx="${idx}">해설 보기 ▾</button>
         <div class="explanation-box hidden" id="exp-${idx}">${escapeHtml(q.explanation)}</div>`
      : '';

    card.innerHTML = `
      <div class="similar-card-header">
        <div class="similar-meta">
          <span class="badge badge-year">${q.year}년 ${q.round}회</span>
          <span class="badge badge-subject">${escapeHtml(q.subject || '')}</span>
        </div>
        <span class="similarity-badge">유사도 ${pct}%</span>
      </div>
      <p class="similar-qnum-line">${q.question_num}번</p>
      <p class="similar-qtext">${escapeHtml(q.question_text || '')}</p>
      <ul class="similar-options">${optionsHtml}</ul>
      <p class="similar-answer-line">&#10003; 정답: ${q.answer}번</p>
      ${explanationHtml}
    `;
    similarList.appendChild(card);
  });

  // 해설 토글
  similarList.querySelectorAll('.explanation-toggle').forEach((btn) => {
    btn.addEventListener('click', () => {
      const i  = btn.dataset.idx;
      const box = document.getElementById(`exp-${i}`);
      if (!box) return;
      const isHidden = box.classList.contains('hidden');
      box.classList.toggle('hidden', !isHidden);
      btn.textContent = isHidden ? '해설 닫기 ▴' : '해설 보기 ▾';
    });
  });
}

// ---------------------------------------------------------------
// RESTART
// ---------------------------------------------------------------
restartBtn.addEventListener('click', () => {
  // 상태 초기화
  selectedFile  = null;
  currentTaskId = null;
  resultData    = null;
  if (pollTimer) clearInterval(pollTimer);

  // UI 초기화
  fileInput.value = '';
  previewImg.src  = '';
  previewInfo.textContent = '';
  uploadPlaceholder.classList.remove('hidden');
  uploadPreview.classList.add('hidden');
  analyzeBtn.disabled = true;
  analyzeBtn.querySelector('.btn-text').textContent = '오답 분석 시작';

  wrongList.innerHTML   = '';
  similarList.innerHTML = '';
  progressFill.style.width = '0%';

  showSection('upload');
  setStep(1);
});

// ---------------------------------------------------------------
// TOAST
// ---------------------------------------------------------------
let toastTimer = null;

function showToast(msg, type = 'info') {
  const icons = { success: '✓', error: '✕', info: 'ℹ' };
  toastIcon.textContent = icons[type] || '';
  toastMsg.textContent  = msg;

  toast.className = `toast ${type}`;
  // Force reflow
  void toast.offsetWidth;
  toast.classList.add('show');

  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toast.classList.remove('show');
  }, 3200);
}

// ---------------------------------------------------------------
// UTIL
// ---------------------------------------------------------------
function escapeHtml(str) {
  if (typeof str !== 'string') return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
