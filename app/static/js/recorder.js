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

// ── 文字起こし & クリーニング & 要約 ──────────────
async function runTranscribe(recordId) {
  const processSection = document.getElementById('processSection');
  const step1 = document.getElementById('step1');
  const step2 = document.getElementById('step2');
  const step3 = document.getElementById('step3');

  // エラー表示をリセット
  const errorDetail = document.getElementById('transcribeError');
  if (errorDetail) { errorDetail.classList.remove('visible'); errorDetail.textContent = ''; }

  processSection.classList.add('visible');
  [step1, step2, step3].forEach(s => { if(s) s.classList.remove('error'); });
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
    showTranscribeError('ネットワークエラーが発生しました。サーバーが起動しているか確認してください。');
    return;
  }

  if (data.status === 'error') {
    showTranscribeError(data.message || 'エラーが発生しました。');
    await loadHistory();
    return;
  }

  // step1 完了
  step1.classList.remove('active'); step1.classList.add('done');
  step1.querySelector('.step-icon').textContent = '✓';
  step1.querySelector('span').textContent = '文字起こし完了';

  // step2 クリーニング
  if (step2) {
    step2.classList.add('active');
    step2.querySelector('span').textContent = 'クリーニング中...';
    await new Promise(r => setTimeout(r, 300));
    step2.classList.remove('active'); step2.classList.add('done');
    step2.querySelector('.step-icon').textContent = '✓';
    step2.querySelector('span').textContent = 'クリーニング完了';
  }

  // step3 要約
  if (step3) {
    step3.classList.add('active');
    await new Promise(r => setTimeout(r, 300));
    step3.classList.remove('active'); step3.classList.add('done');
    step3.querySelector('.step-icon').textContent = '✓';
    step3.querySelector('span').textContent = 'AI要約完了';
  }

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

function showTranscribeError(message) {
  const step1 = document.getElementById('step1');
  const step2 = document.getElementById('step2');
  const step3 = document.getElementById('step3');
  if (step1) { step1.classList.remove('active'); step1.classList.add('error');
    step1.querySelector('.step-icon').textContent = '✕';
    step1.querySelector('span').textContent = '処理に失敗しました'; }
  if (step2) { step2.classList.add('error');
    step2.querySelector('.step-icon').textContent = '–'; }
  if (step3) { step3.classList.add('error');
    step3.querySelector('.step-icon').textContent = '–'; }
  if (step2) step2.querySelector('span').textContent = 'スキップ';

  const errorDetail = document.getElementById('transcribeError');
  if (errorDetail) {
    errorDetail.textContent = '❌ ' + message;
    errorDetail.classList.add('visible');
  }
  // 再試行ボタンを表示
  const retryBtn = document.getElementById('retryAfterError');
  if (retryBtn) retryBtn.style.display = 'block';
  showToast('❌ ' + message);
}

// 最新録音の再試行
async function retryLatestTranscribe() {
  // 最新のrecord_idを取得
  try {
    const res  = await fetch('/api/recordings');
    const data = await res.json();
    if (!data.length) return;
    const latest = data[0];  // 最新が先頭

    // 再試行ボタンを隠す
    const retryBtn = document.getElementById('retryAfterError');
    if (retryBtn) retryBtn.style.display = 'none';

    // エラー表示をリセット
    const errorDetail = document.getElementById('transcribeError');
    if (errorDetail) { errorDetail.classList.remove('visible'); errorDetail.textContent = ''; }

    // 処理ステップをリセット
    const step1 = document.getElementById('step1');
    const step2 = document.getElementById('step2');
    const step3 = document.getElementById('step3');
    step1.className = 'process-step active';
    step1.querySelector('.step-icon').textContent = '①';
    step1.querySelector('span').textContent = '文字起こし中...';
    step2.className = 'process-step';
    step2.querySelector('.step-icon').textContent = '②';
    step2.querySelector('span').textContent = 'クリーニング中...';
    if (step3) { step3.className = 'process-step';
      step3.querySelector('.step-icon').textContent = '③';
      step3.querySelector('span').textContent = 'AI要約中...'; }

    await runTranscription(latest.id);
  } catch (e) {
    showToast('❌ 再試行に失敗しました');
  }
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
  // 現在開いているアコーディオンのIDを記憶
  const openIds = [...document.querySelectorAll('.history-item.open')]
    .map(el => el.id.replace('history-', ''));
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

        <!-- 文字起こし / クリーニング / 要約 タブ -->
        ${(r.transcript || r.cleaned_transcript || r.ai_summary) ? `
          <div class="content-tabs">
            ${r.transcript ? `<div class="content-tab active" id="tab-tr-${r.id}" onclick="showTab(${r.id},'transcript')">📝 文字起こし</div>` : ''}
            ${r.cleaned_transcript ? `<div class="content-tab" id="tab-cl-${r.id}" onclick="showTab(${r.id},'cleaned')">🧹 クリーニング済み</div>` : ''}
            ${r.ai_summary ? `<div class="content-tab" id="tab-su-${r.id}" onclick="showTab(${r.id},'summary')">✨ AI要約</div>` : ''}
          </div>
          ${r.transcript ? `
            <div class="content-panel active" id="panel-transcript-${r.id}">
              <div class="history-content">${escHtml(r.transcript)}</div>
            </div>` : ''}
          ${r.cleaned_transcript ? `
            <div class="content-panel" id="panel-cleaned-${r.id}">
              <div class="history-content">${escHtml(r.cleaned_transcript)}</div>
            </div>` : ''}
          ${r.ai_summary ? `
            <div class="content-panel" id="panel-summary-${r.id}">
              <div class="history-content">${escHtml(r.ai_summary)}</div>
            </div>` : ''}
        ` : ''}

        <div class="extra-prompt-row">
          <input class="extra-prompt-input" id="extra-prompt-${r.id}"
            placeholder="🔄 再要約への追加指示（例：技術的な専門用語を優先して記載してください）" />
        </div>
        <div class="history-actions">
          <button class="btn btn-retry btn-retry-transcript" onclick="retryTranscribe(${r.id})">🔄 文字起こし</button>
          <button class="btn btn-retry btn-retry-clean" onclick="retryClean(${r.id})">🧹 再クリーニング</button>
          <button class="btn btn-retry btn-retry-summary" onclick="retrySummary(${r.id})">🔄 再要約</button>
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
  ['transcript', 'cleaned', 'summary'].forEach(t => {
    const tabId = t === 'transcript' ? `tab-tr-${id}` : t === 'cleaned' ? `tab-cl-${id}` : `tab-su-${id}`;
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

// ── 文字起こし・要約の再実行 ─────────────────────
async function retryClean(recordId) {
  if (!confirm('クリーニングを再実行しますか？')) return;
  setRetryState(recordId, 'cleaning');
  try {
    const res  = await fetch('/api/clean', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ record_id: recordId }),
    });
    const data = await res.json();
    if (data.status === 'done') {
      showToast('✅ クリーニングが完了しました');
      await loadHistory();
    } else {
      setRetryState(recordId, 'idle');
      showToast('❌ 失敗: ' + (data.message || 'エラーが発生しました'));
    }
  } catch (e) {
    setRetryState(recordId, 'idle');
    showToast('❌ ネットワークエラーが発生しました');
  }
}

async function retryTranscribe(recordId) {
  if (!confirm('文字起こしと要約を再実行しますか？')) return;
  // 文字起こし中: 文字起こしボタン→処理中、再要約ボタン→非活性
  setRetryState(recordId, 'transcribing');
  try {
    const res  = await fetch('/api/transcribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ record_id: recordId }),
    });
    const data = await res.json();
    if (data.status === 'done') {
      showToast('✅ 文字起こし・要約が完了しました');
      await loadHistory();
    } else {
      setRetryState(recordId, 'idle');
      showToast('❌ 失敗: ' + (data.message || 'エラーが発生しました'));
    }
  } catch (e) {
    setRetryState(recordId, 'idle');
    showToast('❌ ネットワークエラーが発生しました');
  }
}

async function retrySummary(recordId) {
  if (!confirm('要約を再実行しますか？')) return;
  const extraPromptEl = document.getElementById(`extra-prompt-${recordId}`);
  const extraPrompt   = extraPromptEl ? extraPromptEl.value.trim() : '';
  // 要約中: 文字起こしボタン→非活性、再要約ボタン→処理中
  setRetryState(recordId, 'summarizing');
  try {
    const res  = await fetch('/api/summarize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ record_id: recordId, extra_prompt: extraPrompt }),
    });
    const data = await res.json();
    if (data.status === 'done') {
      showToast('✅ 要約が完了しました');
      await loadHistory();
    } else {
      setRetryState(recordId, 'idle');
      showToast('❌ 失敗: ' + (data.message || 'エラーが発生しました'));
    }
  } catch (e) {
    setRetryState(recordId, 'idle');
    showToast('❌ ネットワークエラーが発生しました');
  }
}

function setRetryState(recordId, state) {
  // state: 'idle' | 'transcribing' | 'cleaning' | 'summarizing'
  const item = document.getElementById(`history-${recordId}`);
  if (!item) return;
  const transcribeBtn = item.querySelector('.btn-retry-transcript');
  const cleanBtn      = item.querySelector('.btn-retry-clean');
  const summaryBtn    = item.querySelector('.btn-retry-summary');
  if (!transcribeBtn || !summaryBtn) return;

  // まず全ボタンをリセット
  [transcribeBtn, cleanBtn, summaryBtn].forEach(btn => {
    if (!btn) return;
    btn.disabled      = false;
    btn.style.opacity = '';
  });
  transcribeBtn.textContent = '🔄 文字起こし';
  if (cleanBtn) cleanBtn.textContent = '🧹 再クリーニング';
  summaryBtn.textContent    = '🔄 再要約';

  switch (state) {
    case 'transcribing':
      transcribeBtn.disabled    = true;
      transcribeBtn.textContent = '⏳ 文字起こし中...';
      if (cleanBtn) { cleanBtn.disabled = true; cleanBtn.style.opacity = '0.3'; }
      summaryBtn.disabled       = true;
      summaryBtn.style.opacity  = '0.3';
      break;
    case 'cleaning':
      transcribeBtn.disabled      = true;
      transcribeBtn.style.opacity = '0.3';
      if (cleanBtn) { cleanBtn.disabled = true; cleanBtn.textContent = '⏳ クリーニング中...'; }
      summaryBtn.disabled         = true;
      summaryBtn.style.opacity    = '0.3';
      break;
    case 'summarizing':
      transcribeBtn.disabled      = true;
      transcribeBtn.style.opacity = '0.3';
      if (cleanBtn) { cleanBtn.disabled = true; cleanBtn.style.opacity = '0.3'; }
      summaryBtn.disabled         = true;
      summaryBtn.textContent      = '⏳ 要約中...';
      break;
  }
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
