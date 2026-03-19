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
  checkBlackHole();
  updateSettingsBadge();
  checkModelReady();
  restoreInputs();
  checkOllama();

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
  // ビジネス用モードの場合、要約をスキップ表示
  let isBusinessMode = false;
  try {
    const settingsRes2 = await fetch('/api/settings');
    const settings2    = await settingsRes2.json();
    isBusinessMode = settings2.ai_mode === 'business';
    if (isBusinessMode) {
      step2.querySelector('span').textContent = '要約スキップ（ビジネス用：完全ローカル処理）';
    }
  } catch (e) {}
  await new Promise(r => setTimeout(r, 300));
  step2.classList.remove('active'); step2.classList.add('done');
  step2.querySelector('.step-icon').textContent = isBusinessMode ? '–' : '✓';
  step2.querySelector('span').textContent = isBusinessMode ? '要約スキップ（Ollama導入後に対応予定）' : 'AI要約完了';

  document.getElementById('transcriptBody').textContent = data.transcript;
  document.getElementById('summaryBody').textContent    = data.ai_summary;
  document.getElementById('resultSection').classList.add('visible');

  document.getElementById('titleInput').value = '';
  document.getElementById('memoInput').value  = '';
  sessionStorage.removeItem('aura_title');
  sessionStorage.removeItem('aura_memo');

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

// ── BlackHole チェック（Mac・システム音声モード時） ──
async function checkBlackHole() {
  // Mac以外はスキップ
  const isMac = navigator.platform.toUpperCase().includes('MAC');
  if (!isMac) return;

  try {
    // 設定を取得してシステム音声モードか確認
    const settingsRes = await fetch('/api/settings');
    const settings    = await settingsRes.json();
    const isSystemAudio = settings.recording_device_id !== "";
    if (!isSystemAudio) return;

    // デバイス一覧を取得してBlackHoleが存在するか確認
    const devRes  = await fetch('/api/devices');
    const devices = await devRes.json();
    const hasBlackHole = devices.some(d =>
      d.name.toLowerCase().includes('blackhole')
    );

    if (!hasBlackHole) {
      document.getElementById('blackholeBanner').style.display = 'flex';
      // 録音ボタンも無効化
      const btn = document.getElementById('recordBtn');
      btn.disabled = true;
      btn.title = 'BlackHoleをインストールしてください';
      document.getElementById('recordLabel').textContent =
        'BlackHoleをインストールしてください';
    }
  } catch (e) {
    // 取得失敗時は何もしない
  }
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

// ── 現在の設定状態バッジ ─────────────────────────
async function updateSettingsBadge() {
  try {
    const res      = await fetch('/api/settings');
    const settings = await res.json();

    const isSystem   = settings.recording_source === 'system';
    const isBusiness = settings.ai_mode === 'business';

    const rows = [
      {
        badgeClass: isSystem ? 'settings-badge settings-badge-system' : 'settings-badge',
        badgeText:  isSystem ? '🖥️ システム音声' : '🎤 マイク入力',
        noticeIcon: isSystem ? '🔊' : '⚠️',
        noticeText: isSystem ? 'PCのすべての音声を録音します' : 'オンライン会議の音声は録音されません',
      },
      {
        badgeClass: isBusiness ? 'settings-badge settings-badge-business' : 'settings-badge',
        badgeText:  isBusiness ? '🏢 ビジネス用（faster-whisper）' : '⚡ 個人用（Groq API）',
        noticeIcon: isBusiness ? '🔒' : '☁️',
        noticeText: isBusiness ? '音声データはクラウドに送信されません' : '音声データはクラウドに送信されます',
      },
    ];

    const rowEl = document.getElementById('settingsBadgesRow');
    if (rowEl) {
      rowEl.innerHTML = rows.map(r => `
        <div class="settings-badge-group">
          <span class="${r.badgeClass}">${r.badgeText}</span>
          <div class="settings-notice-item">
            <span class="settings-notice-icon">${r.noticeIcon}</span>
            <span>${r.noticeText}</span>
          </div>
        </div>`
      ).join('');
    }

  } catch (e) {}
}

// ── モデル準備チェック（ビジネス用モード） ──────────
let _modelReadyTimer = null;

async function checkModelReady() {
  try {
    const settingsRes = await fetch('/api/settings');
    const settings    = await settingsRes.json();
    if (settings.ai_mode !== 'business') return; // 個人用モードは不要

    const res  = await fetch('/api/model/status');
    const data = await res.json();

    if (data.status === 'ready') {
      hideModelBanner();
      return;
    }

    // ロード中またはidle（まだ開始前）→ ロック
    lockForModel(data.status);
    _modelReadyTimer = setInterval(async () => {
      try {
        const r = await fetch('/api/model/status');
        const d = await r.json();
        if (d.status === 'ready') {
          clearInterval(_modelReadyTimer);
          _modelReadyTimer = null;
          hideModelBanner();
        } else if (d.status === 'error') {
          clearInterval(_modelReadyTimer);
          _modelReadyTimer = null;
          showModelBanner(
            `❌ AIモデルのロードに失敗しました。設定画面で再度ビジネス用モードを保存してください。`,
            'error'
          );
        }
      } catch (e) {}
    }, 3000);

  } catch (e) {}
}

function lockForModel(status) {
  const btn = document.getElementById('recordBtn');
  if (btn) {
    btn.disabled = true;
    btn.style.opacity = '0.4';
    btn.style.cursor  = 'not-allowed';
  }
  const msg = status === 'loading'
    ? '⏳ AIモデルをロード中です。完了後に録音できます...'
    : '⏳ AIモデルを準備中です。しばらくお待ちください...';
  showModelBanner(msg, 'loading');
}

function hideModelBanner() {
  // バナーを非表示
  const banner = document.getElementById('modelReadyBanner');
  if (banner) banner.style.display = 'none';
  // 録音ボタンを再有効化
  const btn = document.getElementById('recordBtn');
  if (btn) {
    btn.disabled      = false;
    btn.style.opacity = '';
    btn.style.cursor  = '';
  }
  showToast('✅ AIモデルの準備が完了しました。録音を開始できます。');
}

function showModelBanner(msg, type) {
  let banner = document.getElementById('modelReadyBanner');
  if (!banner) {
    banner = document.createElement('div');
    banner.id = 'modelReadyBanner';
    // APIバナーの後に挿入
    const ref = document.getElementById('blackholeBanner') || document.querySelector('main');
    ref.insertAdjacentElement('afterend', banner);
  }
  banner.className  = 'api-warning-banner model-ready-banner model-ready-' + type;
  banner.style.display = 'flex';
  banner.innerHTML  = `<div class="api-warning-icon">${type === 'error' ? '❌' : '⏳'}</div>
    <div class="api-warning-text">${msg}</div>`;
}

// ── sessionStorage による入力保持 ────────────────
function restoreInputs() {
  const titleEl = document.getElementById('titleInput');
  const memoEl  = document.getElementById('memoInput');
  if (!titleEl || !memoEl) return;

  // 保存済みの値を復元
  const savedTitle = sessionStorage.getItem('aura_title');
  const savedMemo  = sessionStorage.getItem('aura_memo');
  if (savedTitle !== null) titleEl.value = savedTitle;
  if (savedMemo  !== null) memoEl.value  = savedMemo;

  // 入力のたびにsessionStorageに保存
  titleEl.addEventListener('input', () => {
    sessionStorage.setItem('aura_title', titleEl.value);
  });
  memoEl.addEventListener('input', () => {
    sessionStorage.setItem('aura_memo', memoEl.value);
  });
}

// ── Ollama起動チェック（ビジネス用モード） ──────────
async function checkOllama() {
  try {
    const settingsRes = await fetch('/api/settings');
    const settings    = await settingsRes.json();
    if (settings.ai_mode !== 'business') return;

    const res  = await fetch('/api/ollama/status');
    const data = await res.json();
    if (data.status !== 'running') {
      document.getElementById('ollamaBanner').style.display = 'flex';
    }
  } catch (e) {}
}

// ── アプリ終了 ────────────────────────────────────
async function shutdownApp() {
  if (!confirm('AURAを終了しますか？')) return;
  try {
    await fetch('/api/shutdown', { method: 'POST' });
  } catch (e) {
    // サーバー終了でfetchが失敗するのは正常
  }
  window.close();
  // window.closeが効かないブラウザ向けのフォールバック
  setTimeout(() => {
    document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:Arial;color:#888;font-size:18px;">AURAを終了しました。このタブを閉じてください。</div>';
  }, 500);
}
