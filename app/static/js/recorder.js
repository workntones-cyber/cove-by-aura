/* ══════════════════════════════════════════════════
   AURA - recorder.js
   録音制御・プレイヤー制御（index.html 専用）
   ══════════════════════════════════════════════════ */

// ── 状態 ──────────────────────────────────────────
let isRecording = false;
let currentRecordId = null;
let timerInterval = null;
let seconds = 0;

const audio = new Audio();
let currentPlayerId = null;
let isDragging = false;
let dragId = null;
const speeds = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0];

// ── 初期化 ────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  buildVisualizer();
  loadHistory();
  checkApiKey();

  document.addEventListener('mousemove', e => {
    if (!isDragging || dragId === null) return;
    seekTo(e, dragId);
  });
  document.addEventListener('mouseup', () => { isDragging = false; dragId = null; });
});

// ── APIキーチェック ───────────────────────────────
async function checkApiKey() {
  try {
    const res  = await fetch('/api/settings');
    const data = await res.json();

    // ビジネス用モードはAPIキー不要
    if (data.ai_mode === 'business') return;

    // 個人用モードでAPIキー未設定の場合
    if (!data.has_groq_key) {
      // バナーを表示
      document.getElementById('apiWarningBanner').style.display = 'flex';
      // 録音ボタンを無効化
      const btn = document.getElementById('recordBtn');
      btn.disabled = true;
      btn.title = 'APIキーを設定してください';
      document.getElementById('recordLabel').textContent = '設定画面でAPIキーを入力してください';
    }
  } catch (e) {
    // 設定取得失敗時は何もしない
  }
}

// ── 波形ビジュアライザー ──────────────────────────
function buildVisualizer() {
  const v = document.getElementById('visualizer');
  for (let i = 0; i < 40; i++) {
    const bar = document.createElement('div');
    bar.className = 'visualizer-bar';
    v.appendChild(bar);
  }
}

// ── 録音トグル ────────────────────────────────────
async function toggleRecording() {
  if (!isRecording) await startRecording();
  else await stopRecording();
}

async function startRecording() {
  const res  = await fetch('/api/record/start', { method: 'POST' });
  const data = await res.json();
  if (data.status !== 'started') { showToast('❌ ' + (data.message || '録音開始に失敗しました')); return; }

  isRecording = true;
  seconds = 0;
  document.getElementById('recordBtn').classList.add('recording');
  document.getElementById('recordBtn').textContent = '⏹️';
  document.getElementById('recordLabel').textContent = '録音中... タップして停止';
  document.getElementById('recordTimer').classList.add('visible');
  document.getElementById('visualizer').classList.add('recording');

  timerInterval = setInterval(() => {
    seconds++;
    const m = String(Math.floor(seconds / 60)).padStart(2, '0');
    const s = String(seconds % 60).padStart(2, '0');
    document.getElementById('recordTimer').textContent = `${m}:${s}`;
  }, 1000);
}

async function stopRecording() {
  clearInterval(timerInterval);
  isRecording = false;
  document.getElementById('recordBtn').classList.remove('recording');
  document.getElementById('recordBtn').textContent = '🎙️';
  document.getElementById('recordLabel').textContent = 'タップして録音開始';
  document.getElementById('recordTimer').classList.remove('visible');
  document.getElementById('visualizer').classList.remove('recording');

  const title = document.getElementById('titleInput').value || '無題';
  const memo  = document.getElementById('memoInput').value  || '';

  const res  = await fetch('/api/record/stop', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, memo }),
  });
  const data = await res.json();
  if (data.status !== 'stopped') { showToast('❌ ' + (data.message || '録音停止に失敗しました')); return; }

  currentRecordId = data.record_id;
  showToast(`✅ 録音完了（${data.duration}秒）`);
  await runTranscribe(currentRecordId);
}

// ── 文字起こし & 要約 ─────────────────────────────
async function runTranscribe(recordId) {
  const processSection = document.getElementById('processSection');
  const step1 = document.getElementById('step1');
  const step2 = document.getElementById('step2');

  // エラー表示をリセット
  const errorDetail = document.getElementById('transcribeError');
  if (errorDetail) { errorDetail.classList.remove('visible'); errorDetail.textContent = ''; }

  processSection.classList.add('visible');
  step1.classList.remove('error'); step2.classList.remove('error');
  step1.classList.add('active');

  let data;
  try {
    const res = await fetch('/api/transcribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ record_id: recordId }),
    });
    data = await res.json();
  } catch (e) {
    showTranscribeError(step1, step2, 'ネットワークエラーが発生しました。サーバーが起動しているか確認してください。');
    return;
  }

  if (data.status === 'error') {
    showTranscribeError(step1, step2, data.message || 'エラーが発生しました。');
    await loadHistory();
    return;
  }

  step1.classList.remove('active'); step1.classList.add('done');
  step1.querySelector('.step-icon').textContent = '✓';
  step1.querySelector('span').textContent = '文字起こし完了';

  step2.classList.add('active');
  await new Promise(r => setTimeout(r, 500));
  step2.classList.remove('active'); step2.classList.add('done');
  step2.querySelector('.step-icon').textContent = '✓';
  step2.querySelector('span').textContent = 'AI要約完了';

  document.getElementById('transcriptBody').textContent = data.transcript;
  document.getElementById('summaryBody').textContent    = data.ai_summary;
  document.getElementById('resultSection').classList.add('visible');

  document.getElementById('titleInput').value = '';
  document.getElementById('memoInput').value  = '';

  await loadHistory();
  showToast('🎉 完了しました！');
}

function showTranscribeError(step1, step2, message) {
  step1.classList.remove('active'); step1.classList.add('error');
  step1.querySelector('.step-icon').textContent = '✕';
  step1.querySelector('span').textContent = '処理に失敗しました';
  step2.classList.add('error');
  step2.querySelector('.step-icon').textContent = '–';
  step2.querySelector('span').textContent = 'スキップ';

  const errorDetail = document.getElementById('transcribeError');
  if (errorDetail) {
    errorDetail.textContent = '❌ ' + message;
    errorDetail.classList.add('visible');
  }
  showToast('❌ ' + message);
}

// ── 過去データ一覧 ────────────────────────────────
async function loadHistory() {
  const res  = await fetch('/api/recordings');
  const list = await res.json();
  const container = document.getElementById('historyList');

  if (list.length === 0) {
    container.innerHTML = '<div class="empty-state">📭 録音データがありません</div>';
    return;
  }

  container.innerHTML = list.map(r => `
    <div class="history-item" id="history-${r.id}">
      <div class="history-header" onclick="toggleHistory(${r.id})">
        <div class="history-icon">🎙️</div>
        <div class="history-meta">
          <div class="history-title">${escHtml(r.title)}</div>
          <div class="history-date">${r.created_at}</div>
        </div>
        <div class="history-chevron">▾</div>
      </div>

      <div class="history-body">
        <div class="history-divider"></div>

        <div class="history-edit-row">
          <input class="history-edit-input" id="edit-title-${r.id}"
            type="text" value="${escHtml(r.title)}" placeholder="タイトル" />
        </div>
        <div class="history-edit-row">
          <input class="history-edit-input" id="edit-memo-${r.id}"
            type="text" value="${escHtml(r.memo)}" placeholder="概要メモ" />
        </div>

        <!-- フルオーディオプレイヤー -->
        <div class="audio-player">
          <div class="player-top">
            <button class="play-btn" id="play-btn-${r.id}"
              onclick="togglePlay(${r.id}, '/api/audio/${escHtml(r.wav_file)}')">▶</button>
            <div class="player-right">
              <div class="player-times">
                <span id="cur-${r.id}">0:00</span>
                <span id="dur-${r.id}">--:--</span>
              </div>
              <div class="seek-bar" id="seek-${r.id}"
                onclick="seekTo(event, ${r.id})"
                onmousedown="startDrag(${r.id})">
                <div class="seek-progress" id="prog-${r.id}" style="width:0%"></div>
                <div class="seek-thumb"    id="thumb-${r.id}" style="left:0%"></div>
              </div>
            </div>
          </div>
          <div class="player-bottom">
            <span class="speed-label">速度：</span>
            ${speeds.map(s => `
              <button class="speed-btn ${s === 1.0 ? 'active' : ''}"
                id="speed-${r.id}-${s.toString().replace('.','_')}"
                onclick="setSpeed(${r.id}, ${s})">
                ${s}x
              </button>
            `).join('')}
          </div>
        </div>

        <!-- 文字起こし / 要約 タブ -->
        ${(r.transcript || r.ai_summary) ? `
          <div class="content-tabs">
            ${r.transcript ? `<div class="content-tab active" id="tab-tr-${r.id}" onclick="showTab(${r.id},'transcript')">📝 文字起こし</div>` : ''}
            ${r.ai_summary ? `<div class="content-tab ${!r.transcript ? 'active' : ''}" id="tab-su-${r.id}" onclick="showTab(${r.id},'summary')">✨ AI要約</div>` : ''}
          </div>
          ${r.transcript ? `
            <div class="content-panel active" id="panel-transcript-${r.id}">
              <div class="history-content">${escHtml(r.transcript)}</div>
            </div>` : ''}
          ${r.ai_summary ? `
            <div class="content-panel ${!r.transcript ? 'active' : ''}" id="panel-summary-${r.id}">
              <div class="history-content">${escHtml(r.ai_summary)}</div>
            </div>` : ''}
        ` : ''}

        <div class="history-actions">
          <button class="btn btn-save"   onclick="saveHistory(${r.id})">💾 保存</button>
          <button class="btn btn-delete" onclick="deleteHistory(${r.id})">🗑️ 削除</button>
        </div>
      </div>
    </div>
  `).join('');
}

function toggleHistory(id) {
  document.getElementById(`history-${id}`).classList.toggle('open');
}

function showTab(id, type) {
  ['transcript', 'summary'].forEach(t => {
    const tabId = t === 'transcript' ? `tab-tr-${id}` : `tab-su-${id}`;
    const tab   = document.getElementById(tabId);
    const panel = document.getElementById(`panel-${t}-${id}`);
    if (tab)   tab.classList.toggle('active',   t === type);
    if (panel) panel.classList.toggle('active', t === type);
  });
}

// ── プレイヤー制御 ────────────────────────────────
function startDrag(id) { isDragging = true; dragId = id; }

function togglePlay(id, src) {
  const btn = document.getElementById(`play-btn-${id}`);

  if (currentPlayerId === id && !audio.paused) {
    audio.pause(); btn.textContent = '▶'; return;
  }

  if (currentPlayerId && currentPlayerId !== id) {
    const prev = document.getElementById(`play-btn-${currentPlayerId}`);
    if (prev) prev.textContent = '▶';
    audio.pause();
  }

  currentPlayerId = id;

  if (audio.getAttribute('data-src') !== src) {
    audio.src = src;
    audio.setAttribute('data-src', src);
    audio.load();
  }

  audio.play().catch(() => showToast('❌ 音声ファイルを読み込めませんでした'));
  btn.textContent = '⏸';

  audio.ontimeupdate     = () => updateUI(id);
  audio.onloadedmetadata = () => {
    document.getElementById(`dur-${id}`).textContent = fmtTime(audio.duration);
  };
  audio.onended = () => {
    btn.textContent = '▶';
    document.getElementById(`prog-${id}`).style.width = '0%';
    document.getElementById(`thumb-${id}`).style.left = '0%';
    document.getElementById(`cur-${id}`).textContent  = '0:00';
  };
}

function updateUI(id) {
  if (!audio.duration) return;
  const pct = (audio.currentTime / audio.duration) * 100;
  document.getElementById(`prog-${id}`).style.width = `${pct}%`;
  document.getElementById(`thumb-${id}`).style.left = `${pct}%`;
  document.getElementById(`cur-${id}`).textContent  = fmtTime(audio.currentTime);
}

function seekTo(e, id) {
  if (currentPlayerId !== id) return;
  const bar  = document.getElementById(`seek-${id}`);
  const rect = bar.getBoundingClientRect();
  const pct  = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
  audio.currentTime = pct * audio.duration;
}

function setSpeed(id, speed) {
  audio.playbackRate = speed;
  speeds.forEach(s => {
    const btn = document.getElementById(`speed-${id}-${s.toString().replace('.', '_')}`);
    if (btn) btn.classList.toggle('active', s === speed);
  });
}

// ── 保存・削除 ────────────────────────────────────
async function saveHistory(id) {
  const title = document.getElementById(`edit-title-${id}`).value;
  const memo  = document.getElementById(`edit-memo-${id}`).value;
  const res   = await fetch(`/api/recordings/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, memo }),
  });
  const data = await res.json();
  if (data.status === 'updated') { showToast('✅ 保存しました'); await loadHistory(); }
  else { showToast('❌ ' + (data.message || '保存に失敗しました')); }
}

async function deleteHistory(id) {
  if (!confirm('このデータを削除しますか？')) return;
  const res  = await fetch(`/api/recordings/${id}`, { method: 'DELETE' });
  const data = await res.json();
  if (data.status === 'deleted') { showToast('🗑️ 削除しました'); await loadHistory(); }
  else { showToast('❌ ' + (data.message || '削除に失敗しました')); }
}

// ── ユーティリティ ────────────────────────────────
function copyText(id) {
  navigator.clipboard.writeText(document.getElementById(id).textContent);
  showToast('📋 コピーしました');
}

function exportText() {
  const text = document.getElementById('summaryBody').textContent;
  const blob = new Blob([text], { type: 'text/plain' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = 'aura_summary.txt'; a.click();
}

function fmtTime(sec) {
  if (!sec || isNaN(sec)) return '0:00';
  return `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, '0')}`;
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 3000);
}

function escHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
