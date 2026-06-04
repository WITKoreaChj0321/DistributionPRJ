/* =============================================================
   유통관리사 최빈출 퀴즈 - quiz.js
   - frequent.json(보기 포함)을 객관식 퀴즈로 출제
   - 정답/오답 즉시 판별, 해설 표시
   - 틀린 문제를 localStorage("DB")에 기록 → 가중치로 재출제 빈도↑
   ============================================================= */
'use strict';

const STORAGE_KEY = 'vqs_quiz_stats_v1'; // { "subject|qtext": { w:오답수, c:정답수 } }
const WRONG_BOOST = 3;                   // 오답 1회당 출제 가중치 가산
const MASTERED_DECAY = 0.3;              // 오답없이 2회+ 맞춘 문제 가중치 감소

// ── 상태 ───────────────────────────────────────
let allPool       = [];     // 보기 있는 전체 문항
let stats         = loadStats();
let current       = null;   // 현재 문항
let currentChoices = [];    // 셔플된 보기 [{text, correct}]
let lastId        = null;
let answered      = false;
let currentSubject = '전체';
let wrongOnly     = false;

// ── DOM ────────────────────────────────────────
const elQText   = document.getElementById('quiz-qtext');
const elChoices = document.getElementById('quiz-choices');
const elFeedback = document.getElementById('quiz-feedback');
const elExplain = document.getElementById('quiz-explain');
const elSubjectBadge = document.getElementById('quiz-subject');
const elFreqBadge = document.getElementById('quiz-freq');
const elNextBtn = document.getElementById('quiz-next-btn');
const elStatTotal = document.getElementById('stat-total');
const elStatCorrect = document.getElementById('stat-correct');
const elStatAcc = document.getElementById('stat-acc');
const elStatWrong = document.getElementById('stat-wrong');
const elWrongOnly = document.getElementById('wrong-only');
const elResetBtn = document.getElementById('reset-btn');
const toast = document.getElementById('toast');
const toastIcon = document.getElementById('toast-icon');
const toastMsg = document.getElementById('toast-msg');
let toastTimer = null;

// ── INIT ───────────────────────────────────────
(async function init() {
  bindUI();
  await loadData();
  refreshStats();
  nextQuestion();
})();

function bindUI() {
  document.querySelectorAll('.subject-tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.subject-tab').forEach((t) => t.classList.remove('active'));
      tab.classList.add('active');
      currentSubject = tab.dataset.subject;
      nextQuestion();
    });
  });
  elNextBtn.addEventListener('click', nextQuestion);
  elWrongOnly.addEventListener('change', () => {
    wrongOnly = elWrongOnly.checked;
    nextQuestion();
  });
  elResetBtn.addEventListener('click', () => {
    if (!confirm('풀이 기록(정답·오답)을 모두 초기화할까요?')) return;
    stats = {};
    saveStats();
    refreshStats();
    showToast('기록을 초기화했습니다.', 'info');
    nextQuestion();
  });
}

// ── 데이터 로드 (정적 JSON, 서버 불필요) ─────────
async function loadData() {
  const urls = ['data/frequent.json', '/static/data/frequent.json'];
  let data = null;
  for (const u of urls) {
    try {
      const r = await fetch(u);
      if (r.ok) { data = await r.json(); break; }
    } catch (e) { /* 다음 경로 */ }
  }
  const questions = (data && data.questions) || [];
  // 보기 2개 이상 + 정답번호 유효 문항만 퀴즈 풀에 포함
  allPool = questions.filter(
    (q) => Array.isArray(q.options) && q.options.length >= 2 &&
           q.answer >= 1 && q.answer <= q.options.length
  );
  if (!allPool.length) {
    elQText.textContent = '퀴즈 데이터를 불러오지 못했습니다.';
  }
}

// ── 기록(localStorage = DB) ─────────────────────
function loadStats() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; }
  catch (e) { return {}; }
}
function saveStats() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(stats)); } catch (e) { /* */ }
}
function qid(q) { return `${q.subject}|${q.question_text}`; }
function recOf(q) { return stats[qid(q)] || { w: 0, c: 0 }; }

// ── 출제 가중치: 틀린 문제일수록 ↑ ───────────────
function weightOf(q) {
  const s = recOf(q);
  let wt = 1 + WRONG_BOOST * s.w;          // 오답 누적 → 가중치 증가
  if (s.w === 0 && s.c >= 2) wt *= MASTERED_DECAY; // 잘 맞히는 문제 → 감소
  return Math.max(0.2, wt);
}

function candidatePool() {
  let cand = currentSubject === '전체'
    ? allPool
    : allPool.filter((q) => q.subject === currentSubject);
  if (wrongOnly) cand = cand.filter((q) => recOf(q).w > 0);
  return cand;
}

// ── 가중치 랜덤 추출 (직전 문제 회피) ────────────
function pickWeighted(cand) {
  let pickFrom = cand.length > 1 ? cand.filter((q) => qid(q) !== lastId) : cand;
  if (!pickFrom.length) pickFrom = cand;
  const weights = pickFrom.map(weightOf);
  const total = weights.reduce((a, b) => a + b, 0);
  let r = Math.random() * total;
  for (let i = 0; i < pickFrom.length; i++) {
    r -= weights[i];
    if (r <= 0) return pickFrom[i];
  }
  return pickFrom[pickFrom.length - 1];
}

// ── 다음 문제 ──────────────────────────────────
function nextQuestion() {
  const cand = candidatePool();
  if (!cand.length) {
    current = null;
    elQText.textContent = wrongOnly
      ? '틀린 문제가 없습니다. 다른 과목을 풀거나 일반 모드로 전환하세요. 🎉'
      : '출제할 문제가 없습니다.';
    elChoices.innerHTML = '';
    elFeedback.classList.add('hidden');
    elExplain.classList.add('hidden');
    elNextBtn.classList.add('hidden');
    elSubjectBadge.textContent = '';
    elFreqBadge.textContent = '';
    return;
  }
  current = pickWeighted(cand);
  lastId = qid(current);
  answered = false;
  renderQuestion(current);
}

function renderQuestion(q) {
  elSubjectBadge.textContent = q.subject || '';
  elFreqBadge.textContent = `${q.frequency}개년 반복`;
  elQText.textContent = q.question_text || '';
  elFeedback.classList.add('hidden');
  elExplain.classList.add('hidden');
  elNextBtn.classList.add('hidden');

  // 보기 셔플 (정답 위치 암기 방지)
  currentChoices = q.options.map((text, i) => ({ text, correct: i + 1 === q.answer }));
  shuffle(currentChoices);

  elChoices.innerHTML = '';
  currentChoices.forEach((c, idx) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'choice-btn';
    btn.innerHTML = `<span class="choice-num">${idx + 1}</span><span class="choice-text">${escapeHtml(c.text)}</span>`;
    btn.addEventListener('click', () => onChoice(c, btn));
    elChoices.appendChild(btn);
  });
}

// ── 정답/오답 판별 ─────────────────────────────
function onChoice(choice, btn) {
  if (answered || !current) return;
  answered = true;

  const buttons = Array.from(elChoices.querySelectorAll('.choice-btn'));
  buttons.forEach((b, i) => {
    b.disabled = true;
    if (currentChoices[i].correct) b.classList.add('correct');
  });
  if (!choice.correct) btn.classList.add('wrong');

  // 기록 갱신 (DB)
  const id = qid(current);
  const s = stats[id] || { w: 0, c: 0 };
  if (choice.correct) s.c += 1; else s.w += 1;
  stats[id] = s;
  saveStats();
  refreshStats();

  // 피드백
  elFeedback.className = `quiz-feedback ${choice.correct ? 'ok' : 'no'}`;
  elFeedback.classList.remove('hidden');
  if (choice.correct) {
    elFeedback.innerHTML = '&#10003; 정답입니다!';
  } else {
    const ans = currentChoices.find((c) => c.correct);
    elFeedback.innerHTML = `&#10007; 오답입니다. 정답: <b>${escapeHtml(ans ? ans.text : '')}</b>`;
  }
  // 해설
  const exp = (current.explanation || '').trim();
  if (exp) {
    elExplain.innerHTML = `<b>해설</b> · ${escapeHtml(exp)}`;
    elExplain.classList.remove('hidden');
  }
  elNextBtn.classList.remove('hidden');
}

// ── 통계 표시 ──────────────────────────────────
function refreshStats() {
  let total = 0, correct = 0, wrongUnique = 0;
  for (const id in stats) {
    const s = stats[id];
    total += (s.w || 0) + (s.c || 0);
    correct += (s.c || 0);
    if ((s.w || 0) > 0) wrongUnique += 1;
  }
  elStatTotal.textContent = total;
  elStatCorrect.textContent = correct;
  elStatAcc.textContent = total ? Math.round((correct / total) * 100) + '%' : '–';
  elStatWrong.textContent = wrongUnique;
}

// ── UTIL ───────────────────────────────────────
function shuffle(arr) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

function showToast(msg, type = 'info') {
  const icons = { success: '✓', error: '✕', info: 'ℹ' };
  toastIcon.textContent = icons[type] || '';
  toastMsg.textContent = msg;
  toast.className = `toast ${type}`;
  void toast.offsetWidth;
  toast.classList.add('show');
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 2600);
}

function escapeHtml(str) {
  if (typeof str !== 'string') return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}
