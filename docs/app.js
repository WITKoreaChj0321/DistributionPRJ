/* =============================================================
   유통관리사 오답 분석기 - app.js
   흐름: 카카오 연동(1) → 사진 업로드(2) → 결과 확인(3)
   ============================================================= */

'use strict';

// ---------------------------------------------------------------
// CONFIG
// ---------------------------------------------------------------
const API_BASE         = '';
const POLL_INTERVAL_MS = 2000;
const POLL_MAX_TRIES   = 60;

// ---------------------------------------------------------------
// DOM REFS
// ---------------------------------------------------------------
const uploadArea        = document.getElementById('upload-area');
const fileInput         = document.getElementById('file-input');
const uploadBtn         = document.getElementById('upload-btn');
const changeFileBtn     = document.getElementById('change-file-btn');
const uploadPlaceholder = document.getElementById('upload-placeholder');
const uploadPreview     = document.getElementById('upload-preview');
const previewImg        = document.getElementById('preview-img');
const previewInfo       = document.getElementById('preview-info');
const analyzeBtn        = document.getElementById('analyze-btn');

const sectionUpload   = document.getElementById('section-upload');
const sectionKakao    = document.getElementById('section-kakao');
const sectionProgress = document.getElementById('section-progress');
const sectionResults  = document.getElementById('section-results');

const kakaoLoginArea  = document.getElementById('kakao-login-area');
const kakaoFriendArea = document.getElementById('kakao-friend-area');
const kakaoLoginBtn   = document.getElementById('kakao-login-btn');
const kakaoLogoutBtn  = document.getElementById('kakao-logout-btn');
const skipKakaoBtn    = document.getElementById('skip-kakao-btn');
const goUploadBtn     = document.getElementById('go-upload-btn');    // "사진 업로드하기" 버튼
const sendKakaoBtn    = document.getElementById('send-kakao-btn');   // 더미 (호환성)
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

const wrongCountEl  = document.getElementById('wrong-count');
const similarCountEl= document.getElementById('similar-count');
const wrongList     = document.getElementById('wrong-list');
const similarList   = document.getElementById('similar-list');

const toast     = document.getElementById('toast');
const toastIcon = document.getElementById('toast-icon');
const toastMsg  = document.getElementById('toast-msg');

const step1El   = document.getElementById('step-1');
const step2El   = document.getElementById('step-2');
const step3El   = document.getElementById('step-3');
const stepLines = document.querySelectorAll('.step-line');

// ---------------------------------------------------------------
// STATE
// ---------------------------------------------------------------
let selectedFile  = null;
let currentTaskId = null;
let pollTimer     = null;
let kakaoLoggedIn = false;
let kakaoToken    = null;
let resultData    = null;
let toastTimer    = null;   // showToast()보다 먼저 선언 (TDZ 에러 방지)

// ---------------------------------------------------------------
// INIT — 카카오 OAuth 콜백 처리
// ---------------------------------------------------------------
(function init() {
  const params = new URLSearchParams(window.location.search);
  const token  = params.get('token');
  const error  = params.get('error');

  if (token) {
    kakaoToken = token;
    handleKakaoLoginSuccess({
      nickname:      params.get('nickname')      || '카카오 사용자',
      profile_image: params.get('profile_image') || '',
    });
    history.replaceState({}, '', window.location.pathname);
  }
  if (error) {
    showToast('카카오 로그인 실패: ' + error, 'error');
    history.replaceState({}, '', window.location.pathname);
  }
})();

// ---------------------------------------------------------------
// STEP INDICATOR
// ---------------------------------------------------------------
function setStep(num) {
  [step1El, step2El, step3El].forEach((el, i) => {
    el.classList.remove('active', 'done');
    if (i + 1 < num)  el.classList.add('done');
    if (i + 1 === num) el.classList.add('active');
  });
  stepLines.forEach((line, i) => {
    line.classList.toggle('done', i + 1 < num);
  });
}

// ---------------------------------------------------------------
// SECTION VISIBILITY
// ---------------------------------------------------------------
function showSection(name) {
  sectionKakao.classList.add('hidden');
  sectionUpload.classList.add('hidden');
  sectionProgress.classList.add('hidden');
  sectionResults.classList.add('hidden');

  if (name === 'kakao')    sectionKakao.classList.remove('hidden');
  if (name === 'upload')   sectionUpload.classList.remove('hidden');
  if (name === 'progress') sectionProgress.classList.remove('hidden');
  if (name === 'results')  sectionResults.classList.remove('hidden');

  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ---------------------------------------------------------------
// KAKAO — Step 1
// ---------------------------------------------------------------
kakaoLoginBtn.addEventListener('click', () => {
  window.location.href = `${API_BASE}/auth/kakao`;
});

kakaoLogoutBtn.addEventListener('click', () => {
  kakaoLoggedIn = false;
  kakaoToken    = null;
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
  showToast(`${userInfo.nickname || '사용자'}님 환영합니다! 이제 사진을 업로드하세요.`, 'success');
}

// "사진 업로드하기" / "로그인 없이 계속하기" → 업로드 단계
function goToUpload() {
  showSection('upload');
  setStep(2);
}

goUploadBtn.addEventListener('click',  goToUpload);
skipKakaoBtn.addEventListener('click', goToUpload);

// ---------------------------------------------------------------
// LOAD FRIENDS
// ---------------------------------------------------------------
async function loadFriends() {
  if (!kakaoToken) return;
  try {
    const res  = await fetch(`${API_BASE}/api/kakao/friends?token=${encodeURIComponent(kakaoToken)}`);
    if (!res.ok) return;
    const data = await res.json();
    const friends = data.friends || [];
    const resultSelect = document.getElementById('friend-select-result');

    friends.forEach((f) => {
      // 카카오 섹션 드롭다운
      const o1 = document.createElement('option');
      o1.value = f.uuid; o1.textContent = f.nickname || '알 수 없음';
      friendSelect.appendChild(o1);
      // 결과 화면 드롭다운
      if (resultSelect) {
        const o2 = document.createElement('option');
        o2.value = f.uuid; o2.textContent = f.nickname || '알 수 없음';
        resultSelect.appendChild(o2);
      }
    });

    // 친구가 있으면 결과 화면 전송 대상 선택 UI 표시
    if (friends.length) {
      const wrap = document.getElementById('result-send-target');
      if (wrap) wrap.classList.remove('hidden');
    }
  } catch (e) {
    console.warn('친구 목록 로드 실패:', e.message);
  }
}

// ---------------------------------------------------------------
// FILE UPLOAD — Step 2
// upload-area 가 <label for="file-input"> 이므로
// 클릭 시 브라우저가 자동으로 파일 다이얼로그를 엶 (JS 불필요)
// ---------------------------------------------------------------
// Drag & Drop 은 JS 필요 — label 기본 클릭 동작은 유지

// 파일 선택 완료
fileInput.addEventListener('change', () => {
  console.log('[DEBUG] fileInput changed, files:', fileInput.files.length);
  if (fileInput.files.length > 0) handleFile(fileInput.files[0]);
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
  console.log('[DEBUG] handleFile:', file.name, file.type, file.size);
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
  reader.onload = (ev) => {
    previewImg.src = ev.target.result;
    previewInfo.textContent = `${file.name} · ${formatBytes(file.size)}`;
    uploadPlaceholder.classList.add('hidden');
    uploadPreview.classList.remove('hidden');
    // 사진 변경 버튼 표시
    const changeWrap = document.getElementById('change-wrap');
    if (changeWrap) changeWrap.classList.remove('hidden');
    analyzeBtn.disabled = false;
    console.log('[DEBUG] 파일 미리보기 완료, 분석 버튼 활성화');
  };
  reader.readAsDataURL(file);
}

function formatBytes(bytes) {
  if (bytes < 1024)        return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// ---------------------------------------------------------------
// ANALYZE — Step 2 → 3
// ---------------------------------------------------------------
async function runAnalysis() {
  // 다중 파일: window._selectedFiles (인라인 핸들러가 설정), 폴백: 단일
  let files = window._selectedFiles
    || (selectedFile ? [selectedFile] : (window._selectedFile ? [window._selectedFile] : []));
  if (!files.length) {
    showToast('이미지를 먼저 선택해주세요.', 'error');
    return;
  }
  try {
    analyzeBtn.disabled = true;
    const btnText = analyzeBtn.querySelector('.btn-text');
    if (btnText) btnText.textContent = `전송 중... (${files.length}장)`;

    const formData = new FormData();
    files.forEach((f) => formData.append('images', f));

    // 틀린 번호 / 연도 / 회차 직접 입력 (선택)
    const wnEl = document.getElementById('wrong-numbers-input');
    const yEl  = document.getElementById('exam-year-input');
    const rEl  = document.getElementById('exam-round-input');
    formData.append('wrong_numbers', wnEl ? wnEl.value : '');
    formData.append('exam_year',  yEl && yEl.value ? yEl.value : '0');
    formData.append('exam_round', rEl && rEl.value ? rEl.value : '0');

    const res = await fetch(`${API_BASE}/api/analyze`, {
      method: 'POST',
      body:   formData,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `서버 오류 (${res.status})`);
    }

    const data    = await res.json();
    currentTaskId = data.task_id;

    // 업로드 성공 → 분석 진행 화면
    showSection('progress');
    setStep(3);
    startPolling();

  } catch (err) {
    showToast(err.message || '업로드에 실패했습니다.', 'error');
    analyzeBtn.disabled = false;
    const btnText = analyzeBtn.querySelector('.btn-text');
    if (btnText) btnText.textContent = '오답 분석 시작';
  }
}

// 전역 노출 (인라인 onclick 백업용)
window.runAnalysis = runAnalysis;

analyzeBtn.addEventListener('click', runAnalysis);

// ---------------------------------------------------------------
// POLLING — Step 3
// ---------------------------------------------------------------
function startPolling() {
  // 기존 타이머가 남아있으면 반드시 정리 (중복 폴링·중복 전송 방지)
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }

  let tries = 0;
  setProgress(5, 'AI가 이미지를 분석하고 있습니다...');
  setProgStep('ocr');

  pollTimer = setInterval(async () => {
    tries++;
    if (tries > POLL_MAX_TRIES) {
      clearInterval(pollTimer);
      showToast('분석 시간이 초과됐습니다. 다시 시도해주세요.', 'error');
      showSection('upload');
      setStep(2);
      return;
    }
    try {
      const res  = await fetch(`${API_BASE}/api/result/${currentTaskId}`);
      if (!res.ok) throw new Error(`결과 조회 실패 (${res.status})`);
      handlePollResponse(await res.json());
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
      // 자동 전송 제거 — 사용자가 '카카오톡으로 전송' 버튼을 눌러야 전송 (중복 방지)
    }, 600);
  } else if (status === 'error' || status === 'failed') {
    clearInterval(pollTimer);
    showToast(data.detail || '분석 중 오류가 발생했습니다.', 'error');
    showSection('upload');
    setStep(2);
  }
}

function setProgress(pct, msg) {
  progressFill.style.width  = pct + '%';
  progressStatus.textContent = msg;
}

function setProgStep(active) {
  const map   = { ocr: progOcr, detect: progDetect, similar: progSimilar };
  const order = ['ocr', 'detect', 'similar'];
  const idx   = order.indexOf(active);
  order.forEach((key, i) => {
    const el = map[key];
    if (!el) return;
    el.classList.remove('active', 'done');
    if (active === 'done')    el.classList.add('done');
    else if (i < idx)         el.classList.add('done');
    else if (i === idx)       el.classList.add('active');
  });
}

// ---------------------------------------------------------------
// RESULTS
// ---------------------------------------------------------------
function renderResults(data) {
  const wrong   = data.wrong_questions   || [];
  const similar = data.similar_questions || [];
  wrongCountEl.textContent   = wrong.length;
  similarCountEl.textContent = similar.length;

  // 연도/자동감지 안내
  const yr = data.exam_year ? `${data.exam_year}년${data.exam_round ? ' '+data.exam_round+'회' : ''}` : '';
  const auto = (data.auto_detected || []);
  let infoEl = document.getElementById('result-info');
  if (!infoEl) {
    infoEl = document.createElement('p');
    infoEl.id = 'result-info';
    infoEl.style.cssText = 'font-size:.82rem;color:#64748B;margin:-12px 0 16px;text-align:center;';
    const summary = document.getElementById('result-summary');
    if (summary && summary.parentNode) summary.parentNode.insertBefore(infoEl, summary.nextSibling);
  }
  const parts = [];
  if (yr) parts.push(`📅 ${yr} 인식`);
  if (auto.length) parts.push(`자동 감지: ${auto.join(', ')}번`);
  infoEl.textContent = parts.join('  ·  ');

  renderWrongQuestions(wrong);
  renderSimilarQuestions(similar);
}

function renderWrongQuestions(list) {
  wrongList.innerHTML = '';
  if (!list.length) {
    wrongList.innerHTML = '<p style="color:#9E9E9E;font-size:.9rem;padding:8px 0;">틀린 문제가 없습니다. 위에서 사진을 다시 올리거나 틀린 번호를 직접 입력해보세요.</p>';
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
        <span class="wrong-your">내 답: ${q.your_answer ?? '-'}번</span>
        <span class="wrong-correct">정답: ${q.correct_answer ?? '-'}번</span>
      </div>`;
    wrongList.appendChild(card);
  });
}

function renderSimilarQuestions(list) {
  similarList.innerHTML = '';
  if (!list.length) {
    similarList.innerHTML = '<p style="color:#9E9E9E;font-size:.9rem;padding:8px 0;">유사 기출문제가 없습니다.</p>';
    return;
  }
  list.forEach((q, idx) => {
    const pct  = Math.round((q.similarity || 0) * 100);
    const card = document.createElement('div');
    card.className = 'similar-card';

    const optsHtml = (q.options || []).map((opt, i) =>
      `<li class="${(i + 1) === q.answer ? 'is-answer' : ''}">${escapeHtml(opt)}</li>`
    ).join('');

    const expHtml = (q.explanation && q.explanation.trim())
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
      <ul class="similar-options">${optsHtml}</ul>
      <p class="similar-answer-line">&#10003; 정답: ${q.answer}번</p>
      ${expHtml}`;
    similarList.appendChild(card);
  });

  similarList.querySelectorAll('.explanation-toggle').forEach((btn) => {
    btn.addEventListener('click', () => {
      const box = document.getElementById(`exp-${btn.dataset.idx}`);
      if (!box) return;
      const hidden = box.classList.contains('hidden');
      box.classList.toggle('hidden', !hidden);
      btn.textContent = hidden ? '해설 닫기 ▴' : '해설 보기 ▾';
    });
  });
}

// ---------------------------------------------------------------
// KAKAO SEND (결과 화면)
// ---------------------------------------------------------------
resendKakaoBtn.addEventListener('click', () => sendToKakao());

let _kakaoSending = false;   // 중복 전송 방지 플래그

async function sendToKakao() {
  if (_kakaoSending) return;  // 이미 전송 중이면 무시
  if (!currentTaskId) { showToast('분석 결과가 없습니다.', 'error'); return; }
  if (!kakaoLoggedIn) { showToast('카카오 로그인이 필요합니다.', 'info'); return; }

  // 전송 대상: 결과 화면 드롭다운 우선, 없으면 카카오 섹션 드롭다운
  const resultSelect = document.getElementById('friend-select-result');
  const friendUuid = (resultSelect && resultSelect.value) || friendSelect.value || 'me';
  try {
    _kakaoSending = true;
    resendKakaoBtn.disabled = true;
    const res = await fetch(`${API_BASE}/api/send-kakao`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ task_id: currentTaskId, friend_uuid: friendUuid, token: kakaoToken || '' }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `전송 실패 (${res.status})`);
    }
    showToast('카카오톡으로 전송했습니다!', 'success');
  } catch (err) {
    showToast(err.message || '카카오톡 전송에 실패했습니다.', 'error');
  } finally {
    resendKakaoBtn.disabled = false;
    _kakaoSending = false;
  }
}

// ---------------------------------------------------------------
// RESTART
// ---------------------------------------------------------------
restartBtn.addEventListener('click', () => {
  selectedFile  = null;
  currentTaskId = null;
  resultData    = null;
  if (pollTimer) clearInterval(pollTimer);

  fileInput.value          = '';
  previewImg.src           = '';
  previewInfo.textContent  = '';
  uploadPlaceholder.classList.remove('hidden');
  uploadPreview.classList.add('hidden');
  const changeWrap = document.getElementById('change-wrap');
  if (changeWrap) changeWrap.classList.add('hidden');
  analyzeBtn.disabled = true;
  analyzeBtn.querySelector('.btn-text').textContent = '오답 분석 시작';
  wrongList.innerHTML    = '';
  similarList.innerHTML  = '';
  progressFill.style.width = '0%';

  showSection('kakao');
  setStep(1);
});

// ---------------------------------------------------------------
// TOAST
// ---------------------------------------------------------------
function showToast(msg, type = 'info') {
  const icons = { success: '✓', error: '✕', info: 'ℹ' };
  toastIcon.textContent = icons[type] || '';
  toastMsg.textContent  = msg;
  toast.className = `toast ${type}`;
  void toast.offsetWidth;
  toast.classList.add('show');
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 3200);
}

// ---------------------------------------------------------------
// UTIL
// ---------------------------------------------------------------
function escapeHtml(str) {
  if (typeof str !== 'string') return '';
  return str
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// ---------------------------------------------------------------
// 인라인 onclick 백업용 전역 노출 (app.js 리스너 미등록 대비)
// ---------------------------------------------------------------
window.sendToKakao = sendToKakao;
window.appReady    = true;   // app.js 끝까지 실행됐다는 플래그
console.log('[app.js] 로드 완료 (v8)');
