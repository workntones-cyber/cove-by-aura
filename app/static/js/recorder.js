/* ══════════════════════════════════════════════════
   COVE - recorder.js
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
document.addEventListener('DOMContentLoaded', async () => {
  buildVisualizer();
  loadCategories();
  loadHistory();
  checkApiKey();
  checkBlackHole();
  updateSettingsBadge();
  checkModelReady();
  restoreInputs();
  checkOllama();
  loadDiskStatus(); // ディスク容量を取得して表示

  document.addEventListener('mousemove', e => {
    if (!isDragging || dragId === null) return;
    seekTo(e, dragId);
  });
  document.addEventListener('mouseup', () => { isDragging = false; dragId = null; });
});

// ── ディスク空き容量表示 ─────────────────────────────
async function loadDiskStatus() {
  const textEl = document.getElementById('diskStatusText');
  const fillEl = document.getElementById('diskStatusFill');
  const pctEl  = document.getElementById('diskStatusPct');
  const warnEl = document.getElementById('diskStatusWarn');
  if(!textEl) return;

  try {
    const res  = await fetch('/api/disk/status');
    const data = await res.json();
    if(data.error) { textEl.textContent = '💿 容量取得失敗'; return; }

    const freeGb  = data.free_gb;
    const totalGb = data.total_gb;
    const usedPct = data.percent_used;
    const freePct = 100 - usedPct;

    // 1時間分のWAV容量（44.1kHz 16bit ステレオ）≈ 約600MB = 0.6GB
    const HOUR_GB = 0.6;
    const canRecord1h = freeGb >= HOUR_GB;

    // 録音可能時間を計算
    const recMinutes = Math.floor(data.free / (1024**3) / HOUR_GB * 60);
    let recTimeStr;
    if(recMinutes >= 60) {
      const h = Math.floor(recMinutes / 60);
      const m = recMinutes % 60;
      recTimeStr = m > 0 ? `約${h}時間${m}分` : `約${h}時間`;
    } else if(recMinutes > 0) {
      recTimeStr = `約${recMinutes}分`;
    } else {
      recTimeStr = '録音不可';
    }

    // バーの色
    const color = !canRecord1h ? '#E24B4A' : freePct < 20 ? '#EF9F27' : '#1D9E75';

    textEl.textContent      = `💿 空き ${freeGb} GB / ${totalGb} GB　録音可能時間：${recTimeStr}`;
    fillEl.style.width      = `${usedPct}%`;
    fillEl.style.background = color;
    pctEl.textContent       = `使用 ${usedPct}%`;
    pctEl.style.color       = color;

    // 1時間録音できない場合に警告を表示
    if(warnEl) warnEl.style.display = canRecord1h ? 'none' : 'block';

  } catch(e) {
    if(textEl) textEl.textContent = '💿 容量取得失敗';
  }
}

// ── エラーモーダル（録音画面用） ────────────────────
function showErrorModal(icon, title, body, btnLabel, btnAction) {
  document.getElementById('errorModalIcon').textContent  = icon;
  document.getElementById('errorModalTitle').textContent = title;
  document.getElementById('errorModalMsg').innerHTML     = body;
  document.getElementById('errorModalBtn').textContent   = btnLabel;
  document.getElementById('errorModalBtn').dataset.action = btnAction;
  document.getElementById('errorModal').style.display   = 'flex';
}

function closeErrorModal() {
  const action = document.getElementById('errorModalBtn').dataset.action || 'close';
  document.getElementById('errorModal').style.display = 'none';
  if(action === 'settings') {
    window.location.href = '/settings';
  } else if(action.startsWith('help:')) {
    const anchor = action.split(':')[1];
    window.open(`/help#${anchor}`, '_blank');
  }
}

// ── APIキーチェック ───────────────────────────────
async function checkApiKey() {
  try {
    const res  = await fetch('/api/settings');
    const data = await res.json();

    // Ollamaモードはキー不要
    if (data.ai_mode === 'ollama') return;

    // クラウドモードでGroqキー未設定の場合（文字起こしに必要）
    if (!data.has_groq_key) {
      document.getElementById('apiWarningBanner').style.display = 'flex';
      const btn = document.getElementById('recordBtn');
      btn.disabled = true;
      btn.title = 'Groq APIキーを設定してください';
      document.getElementById('recordLabel').textContent = '設定画面でGroq APIキーを入力してください';
    }
  } catch (e) {
    // 設定取得失敗時は何もしない
  }
}

// ── 波形ビジュアライザー ──────────────────────────
function buildVisualizer() {
  const v = document.getElementById('visualizer');
  if (!v) return; // visualizer要素がない画面では何もしない
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

  // 🧪 動作検証フラグのチェック
  if(sessionStorage.getItem('cove_debug_disk_error')) {
    showToast(humanizeError('no space left on disk', '録音保存'), true);
    return;
  }

  const title      = document.getElementById('titleInput').value || '無題';
  const memo       = document.getElementById('memoInput').value  || '';
  const categoryId = parseInt(document.getElementById('categorySelect')?.value || '1');

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
  // 🧪 動作検証フラグのチェック
  if(sessionStorage.getItem('cove_debug_model_not_found')) {
    showErrorModal(
      '🤖', 'AIモデルが見つかりません',
      'AIモデルがインストールされていません。<br>設定画面でモデルをダウンロードしてください。',
      '設定へ', 'settings'
    );
    return;
  }

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
  sessionStorage.removeItem('cove_title');
  sessionStorage.removeItem('cove_memo');

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
          <div class="history-title">${escHtml(r.title)}
            ${(() => { const cat = getCategoryById(r.category_id || 1); return `<span style="display:inline-block;padding:1px 8px;border-radius:99px;font-size:11px;background:${cat.color}22;color:${cat.color};border:1px solid ${cat.color}44;margin-left:6px;">${cat.name}</span>`; })()}
          </div>
          <div class="history-date">${r.created_at}</div>
        </div>
        <div class="history-chevron">▾</div>
      </div>

      <div class="history-body">
        <div class="history-divider"></div>

        <div class="history-edit-row">
          <select class="history-edit-input" id="edit-category-${r.id}"
            style="cursor:pointer;" onchange="updateRecordingCategory(${r.id}, this.value)">
            ${_categories.map(cat =>
              `<option value="${cat.id}" ${cat.id === (r.category_id || 1) ? 'selected' : ''}>${cat.name}</option>`
            ).join('')}
          </select>
        </div>
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
          <button class="btn btn-retry"  onclick="openTrimmer(${r.id},'${r.wav_file}','${(r.title||'録音').replace(/'/g,'&apos;')}')">✂️ トリミング</button>
          <button class="btn btn-delete" onclick="deleteHistory(${r.id})">🗑️ 削除</button>
        </div>
      </div>
    </div>
  `).join('');
}

// ══════════════════════════════════════════════════
//  トリマーモーダル
// ══════════════════════════════════════════════════
let _trimRecordId = null;
let _trimAudio    = null;
let _trimAudioCtx = null;
let _trimBuffer   = null;
let _trimDuration = 0;
let _trimStart    = 0;
let _trimEnd      = 1;
let _trimPlaying  = false;
let _trimSource   = null;
let _trimAnimId   = null;

function openTrimmer(id, wavFile, title) {
  // 🧪 動作検証フラグのチェック
  if(sessionStorage.getItem('cove_debug_ffmpeg_not_found')) {
    showErrorModal(
      '🎬', 'ffmpegが見つかりません',
      'トリミング機能にはffmpegが必要です。<br>取扱説明書のインストール手順をご確認ください。',
      '取扱説明書を開く', 'help:trouble-ffmpeg'
    );
    return;
  }

  _trimRecordId = id;
  _trimStart    = 0;
  _trimEnd      = 1;
  _trimPlaying  = false;

  // モーダルを生成（未存在なら）
  let modal = document.getElementById('trimmerModal');
  if(!modal) {
    modal = document.createElement('div');
    modal.id = 'trimmerModal';
    modal.style.cssText = 'display:none;position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:9999;align-items:center;justify-content:center;backdrop-filter:blur(4px);';
    modal.innerHTML = `
      <div style="background:#1e1e2e;border:1px solid #444;border-radius:16px;padding:24px;width:90%;max-width:640px;color:#e0e0e0;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
          <div style="font-size:15px;font-weight:700;" id="trimTitle">トリミング</div>
          <button onclick="closeTrimmer()" style="background:none;border:none;color:#aaa;font-size:20px;cursor:pointer;">✕</button>
        </div>

        <!-- 波形 -->
        <div style="position:relative;margin-bottom:12px;">
          <canvas id="trimWaveform" style="width:100%;height:80px;border-radius:8px;background:#0d0d1a;display:block;"></canvas>
          <!-- 選択範囲オーバーレイ -->
          <canvas id="trimOverlay" style="position:absolute;top:0;left:0;width:100%;height:80px;border-radius:8px;cursor:crosshair;"></canvas>
        </div>

        <!-- 再生ヘッド時刻 -->
        <div style="text-align:center;font-size:11px;color:#aaa;margin-bottom:8px;" id="trimTimeDisplay">00:00.0 / 00:00.0</div>

        <!-- 開始・終了スライダー -->
        <div style="margin-bottom:8px;">
          <div style="display:flex;justify-content:space-between;font-size:11px;color:#aaa;margin-bottom:4px;">
            <span>開始: <span id="trimStartLabel">0.0s</span></span>
            <span>終了: <span id="trimEndLabel">0.0s</span></span>
          </div>
          <div style="position:relative;height:36px;padding:0 8px;">
            <input type="range" id="trimStartSlider" min="0" max="1000" value="0" step="1"
              style="position:absolute;width:calc(100% - 16px);accent-color:#7C6AF7;z-index:3;pointer-events:none;left:8px;"
              oninput="onTrimSlider('start',this.value)">
            <input type="range" id="trimEndSlider" min="0" max="1000" value="1000" step="1"
              style="position:absolute;width:calc(100% - 16px);accent-color:#EF9F27;z-index:3;pointer-events:none;left:8px;"
              oninput="onTrimSlider('end',this.value)">
            <div id="trimSliderZone" style="position:absolute;inset:0;z-index:4;cursor:pointer;"
              onmousedown="onTrimZoneDown(event)" ontouchstart="onTrimZoneDown(event)"></div>
          </div>
          <!-- カラートラック -->
          <div id="trimTrack" style="height:6px;border-radius:3px;margin:0 8px 4px;transition:background .05s;
            background:linear-gradient(to right,rgba(180,30,30,0.7) 0%,#1D9E75 0%,#1D9E75 100%,rgba(180,30,30,0.7) 100%);"></div>
        </div>

        <!-- 選択時間 -->
        <div style="text-align:center;font-size:12px;color:#7C6AF7;margin-bottom:16px;" id="trimDurationLabel">選択: 0.0秒</div>

        <!-- コントロール -->
        <div style="display:flex;gap:8px;justify-content:center;margin-bottom:16px;">
          <button id="trimPlayBtn" onclick="toggleTrimPlay()"
            style="padding:8px 20px;border-radius:8px;border:none;background:#7C6AF7;color:#fff;cursor:pointer;font-size:13px;font-family:inherit;">
            ▶ 再生
          </button>
          <button onclick="previewTrimRange()"
            style="padding:8px 20px;border-radius:8px;border:1px solid #7C6AF7;color:#7C6AF7;background:none;cursor:pointer;font-size:13px;font-family:inherit;">
            ✂️ 範囲のみ再生
          </button>
        </div>

        <!-- 実行ボタン -->
        <div style="display:flex;gap:8px;justify-content:flex-end;">
          <button onclick="closeTrimmer()"
            style="padding:8px 20px;border-radius:8px;border:1px solid #555;color:#ccc;background:#2a2a3e;cursor:pointer;font-family:inherit;">
            キャンセル
          </button>
          <button onclick="executeTrim()"
            style="padding:8px 20px;border-radius:8px;border:none;background:#E24B4A;color:#fff;cursor:pointer;font-family:inherit;font-weight:600;">
            ✂️ トリミング実行（上書き保存）
          </button>
        </div>
        <div style="font-size:10px;color:#666;text-align:center;margin-top:8px;">⚠️ 選択範囲のみを残して上書き保存します。元に戻せません。</div>
      </div>`;
    document.body.appendChild(modal);
  }

  document.getElementById('trimTitle').textContent = `✂️ トリミング：${title}`;
  modal.style.display = 'flex';
  document.getElementById('trimWaveform').width  = 0; // リセット
  document.getElementById('trimStartSlider').value = 0;
  document.getElementById('trimEndSlider').value   = 1000;
  document.getElementById('trimPlayBtn').textContent = '▶ 再生';

  // 音声読み込み＆波形描画
  loadTrimAudio(`/api/audio/${wavFile}`);
}

async function loadTrimAudio(url) {
  _trimAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
  document.getElementById('trimTimeDisplay').textContent = '読み込み中…';
  try {
    const res    = await fetch(url);
    const buf    = await res.arrayBuffer();
    _trimBuffer  = await _trimAudioCtx.decodeAudioData(buf);
    _trimDuration = _trimBuffer.duration;
    _trimEnd     = 1;

    drawTrimWaveform();
    drawTrimOverlay();
    updateTrimLabels();
  } catch(e) {
    document.getElementById('trimTimeDisplay').textContent = '音声の読み込みに失敗しました';
  }
}

function drawTrimWaveform() {
  const canvas = document.getElementById('trimWaveform');
  const W = canvas.parentElement.offsetWidth;
  const H = 80;
  canvas.width  = W;
  canvas.height = H;
  document.getElementById('trimOverlay').width  = W;
  document.getElementById('trimOverlay').height = H;

  const ctx  = canvas.getContext('2d');
  const data = _trimBuffer.getChannelData(0);
  const step = Math.ceil(data.length / W);

  ctx.fillStyle = '#0d0d1a';
  ctx.fillRect(0, 0, W, H);

  ctx.beginPath();
  ctx.strokeStyle = '#7C6AF7';
  ctx.lineWidth   = 1;

  for(let x = 0; x < W; x++) {
    let max = 0;
    for(let i = 0; i < step; i++) {
      const v = Math.abs(data[x * step + i] || 0);
      if(v > max) max = v;
    }
    const y = (1 - max) * H / 2;
    const h = max * H;
    ctx.fillStyle = '#5B4AF7';
    ctx.fillRect(x, y, 1, h);
  }
}

function drawTrimOverlay() {
  const canvas = document.getElementById('trimOverlay');
  if(!canvas.width) return;
  const W   = canvas.width;
  const H   = canvas.height;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, W, H);

  const sx = Math.round(_trimStart * W);
  const ex = Math.round(_trimEnd   * W);

  // カットされる部分（選択範囲外）を赤みがかった暗色で塗る
  ctx.fillStyle = 'rgba(180,30,30,0.55)';
  ctx.fillRect(0,  0, sx,     H);  // 開始前（カット）
  ctx.fillRect(ex, 0, W - ex, H);  // 終了後（カット）

  // 選択範囲の枠線
  ctx.strokeStyle = '#ffffff';
  ctx.lineWidth   = 1.5;
  ctx.strokeRect(sx, 1, ex - sx, H - 2);

  // 開始ハンドル（紫・縦線）
  ctx.fillStyle = '#7C6AF7';
  ctx.fillRect(sx - 3, 0, 6, H);

  // 終了ハンドル（橙・縦線）
  ctx.fillStyle = '#EF9F27';
  ctx.fillRect(ex - 3, 0, 6, H);

  // スライダートラックの色も更新
  updateTrimTrack();
}

function updateTrimTrack() {
  const startPct = (_trimStart * 100).toFixed(2);
  const endPct   = (_trimEnd   * 100).toFixed(2);
  const track    = document.getElementById('trimTrack');
  if(track) {
    track.style.background =
      `linear-gradient(to right,
        rgba(180,30,30,0.7) 0%,
        rgba(180,30,30,0.7) ${startPct}%,
        #1D9E75 ${startPct}%,
        #1D9E75 ${endPct}%,
        rgba(180,30,30,0.7) ${endPct}%,
        rgba(180,30,30,0.7) 100%)`;
  }
}

let _trimDragging = null; // 'start' or 'end'

function onTrimZoneDown(e) {
  e.preventDefault();
  const zone  = document.getElementById('trimSliderZone');
  const rect  = zone.getBoundingClientRect();
  const cx    = (e.touches ? e.touches[0].clientX : e.clientX) - rect.left;
  const ratio = cx / rect.width;

  // 開始・終了どちらに近いかで判定
  const distToStart = Math.abs(ratio - _trimStart);
  const distToEnd   = Math.abs(ratio - _trimEnd);
  _trimDragging = distToStart < distToEnd ? 'start' : 'end';

  onTrimZoneMove(e);

  const moveEv = e.touches ? 'touchmove' : 'mousemove';
  const upEv   = e.touches ? 'touchend'  : 'mouseup';
  const onMove = (ev) => onTrimZoneMove(ev);
  const onUp   = () => {
    _trimDragging = null;
    document.removeEventListener(moveEv, onMove);
    document.removeEventListener(upEv, onUp);
  };
  document.addEventListener(moveEv, onMove);
  document.addEventListener(upEv, onUp);
}

function onTrimZoneMove(e) {
  if(!_trimDragging) return;
  const zone  = document.getElementById('trimSliderZone');
  const rect  = zone.getBoundingClientRect();
  const cx    = (e.touches ? e.touches[0].clientX : e.clientX) - rect.left;
  const ratio = Math.max(0, Math.min(1, cx / rect.width));
  onTrimSlider(_trimDragging, Math.round(ratio * 1000));

  // スライダーの見た目も更新
  if(_trimDragging === 'start') {
    document.getElementById('trimStartSlider').value = Math.round(_trimStart * 1000);
  } else {
    document.getElementById('trimEndSlider').value = Math.round(_trimEnd * 1000);
  }
}

function onTrimSlider(type, val) {
  const ratio = val / 1000;
  if(type === 'start') {
    _trimStart = Math.min(ratio, _trimEnd - 0.01);
    document.getElementById('trimStartSlider').value = Math.round(_trimStart * 1000);
  } else {
    _trimEnd = Math.max(ratio, _trimStart + 0.01);
    document.getElementById('trimEndSlider').value = Math.round(_trimEnd * 1000);
  }
  drawTrimOverlay();
  updateTrimLabels();
}

function updateTrimLabels() {
  const s = (_trimStart * _trimDuration).toFixed(1);
  const e = (_trimEnd   * _trimDuration).toFixed(1);
  const d = ((_trimEnd - _trimStart) * _trimDuration).toFixed(1);
  document.getElementById('trimStartLabel').textContent   = `${s}s`;
  document.getElementById('trimEndLabel').textContent     = `${e}s`;
  document.getElementById('trimDurationLabel').textContent = `選択: ${d}秒`;
  document.getElementById('trimTimeDisplay').textContent  = `${formatTrimTime(s)} 〜 ${formatTrimTime(e)} / ${formatTrimTime(_trimDuration.toFixed(1))}`;
}

function formatTrimTime(sec) {
  const s = parseFloat(sec);
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2,'0')}:${(s % 60).toFixed(1).padStart(4,'0')}`;
}

function toggleTrimPlay() {
  if(_trimPlaying) {
    stopTrimPlay();
  } else {
    playTrimFrom(_trimStart * _trimDuration);
  }
}

function playTrimFrom(startSec) {
  stopTrimPlay();
  _trimSource = _trimAudioCtx.createBufferSource();
  _trimSource.buffer = _trimBuffer;
  _trimSource.connect(_trimAudioCtx.destination);
  _trimSource.start(0, startSec);
  _trimSource.onended = () => { _trimPlaying = false; document.getElementById('trimPlayBtn').textContent = '▶ 再生'; };
  _trimPlaying = true;
  document.getElementById('trimPlayBtn').textContent = '⏹ 停止';
}

function previewTrimRange() {
  playTrimFrom(_trimStart * _trimDuration);
  // 終了位置で自動停止
  const duration = (_trimEnd - _trimStart) * _trimDuration;
  setTimeout(() => stopTrimPlay(), duration * 1000);
}

function stopTrimPlay() {
  if(_trimSource) { try { _trimSource.stop(); } catch(e){} _trimSource = null; }
  _trimPlaying = false;
  const btn = document.getElementById('trimPlayBtn');
  if(btn) btn.textContent = '▶ 再生';
}

function closeTrimmer() {
  stopTrimPlay();
  if(_trimAudioCtx) { _trimAudioCtx.close(); _trimAudioCtx = null; }
  _trimBuffer = null;
  document.getElementById('trimmerModal').style.display = 'none';
}

async function executeTrim() {
  if(!confirm(`選択範囲（${document.getElementById('trimStartLabel').textContent} 〜 ${document.getElementById('trimEndLabel').textContent}）のみを残して上書き保存します。\n\nこの操作は元に戻せません。続けますか？`)) return;

  // 🧪 動作検証フラグのチェック
  if(sessionStorage.getItem('cove_debug_ffmpeg_not_found')) {
    showErrorModal(
      '🎬', 'ffmpegが見つかりません',
      'トリミング機能にはffmpegが必要です。<br>取扱説明書のインストール手順をご確認ください。',
      '取扱説明書を開く', 'help:trouble-ffmpeg'
    );
    return;
  }

  const startSec = _trimStart * _trimDuration;
  const endSec   = _trimEnd   * _trimDuration;

  stopTrimPlay();
  try {
    const res  = await fetch(`/api/recordings/${_trimRecordId}/trim`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ start: startSec, end: endSec }),
    });
    const data = await res.json();
    if(data.status === 'ok') {
      showToast('✅ トリミングしました');
      closeTrimmer();
      loadHistory();
    } else {
      showToast('❌ ' + (data.message || 'トリミングに失敗しました'));
    }
  } catch(e) {
    showToast('❌ 通信エラーが発生しました');
  }
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
  a.href = URL.createObjectURL(blob); a.download = 'cove_summary.txt'; a.click();
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

    const isSystem  = settings.recording_source === 'system';
    const isLocal   = settings.ai_mode === 'ollama';
    const modeLabels = {
      ollama: '🏠 Ollama（完全ローカル）',
      groq:   '⚡ Groq (Llama-3.3-70b)',
      openai: '🤖 OpenAI (GPT-4o)',
      gemini: '✨ Google (Gemini)',
      claude: '🔷 Anthropic (Claude)',
    };
    const modeLabel = modeLabels[settings.ai_mode] || settings.ai_mode;

    const rows = [
      {
        badgeClass: isSystem ? 'settings-badge settings-badge-system' : 'settings-badge',
        badgeText:  isSystem ? '🖥️ システム音声' : '🎤 マイク入力',
        noticeIcon: isSystem ? '🔊' : '⚠️',
        noticeText: isSystem ? 'PCのすべての音声を録音します' : 'オンライン会議の音声は録音されません',
      },
      {
        badgeClass: isLocal ? 'settings-badge settings-badge-business' : 'settings-badge',
        badgeText:  modeLabel,
        noticeIcon: isLocal ? '🔒' : '☁️',
        noticeText: isLocal ? '音声データはクラウドに送信されません' : '音声データはクラウドに送信されます',
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
    if (settings.ai_mode !== 'ollama') return; // Ollamaモード以外は不要

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

// ── カテゴリ管理 ──────────────────────────────────
let _categories = [];

async function loadCategories() {
  try {
    const res = await fetch('/api/categories');
    _categories = await res.json();
    renderCategorySelect();
  } catch (e) {}
}

function renderCategorySelect() {
  const sel = document.getElementById('categorySelect');
  if (!sel) return;
  const current = sel.value;
  sel.innerHTML = _categories.map(cat =>
    `<option value="${cat.id}" ${cat.id == current ? 'selected' : ''}>${cat.name}</option>`
  ).join('');
}

function getCategoryById(id) {
  return _categories.find(c => c.id === parseInt(id)) || { name: '未分類', color: '#6B7280' };
}

// ── sessionStorage による入力保持 ────────────────
function restoreInputs() {
  const titleEl = document.getElementById('titleInput');
  const memoEl  = document.getElementById('memoInput');
  if (!titleEl || !memoEl) return;

  // 保存済みの値を復元
  const savedTitle = sessionStorage.getItem('cove_title');
  const savedMemo  = sessionStorage.getItem('cove_memo');
  if (savedTitle !== null) titleEl.value = savedTitle;
  if (savedMemo  !== null) memoEl.value  = savedMemo;

  // 入力のたびにsessionStorageに保存
  titleEl.addEventListener('input', () => {
    sessionStorage.setItem('cove_title', titleEl.value);
  });
  memoEl.addEventListener('input', () => {
    sessionStorage.setItem('cove_memo', memoEl.value);
  });
}

// ── 文字起こし・要約の再実行 ─────────────────────
// ── エラーメッセージを人間が理解できる言葉に変換 ──
function humanizeError(msg, context) {
  if(!msg) return '不明なエラーが発生しました。ページを再読み込みしてください。';
  const m = msg.toLowerCase();
  const ctx = context || '処理';

  if(m.includes('connection refused') || m.includes('connect') || m.includes('11434'))
    return `Ollamaとの接続が切れました。「${ctx}」ボタンを再度押してください。`;
  if(m.includes('timeout') || m.includes('timed out'))
    return `${ctx}がタイムアウトしました。音声が長すぎる場合はトリミングしてから再試行してください。`;
  if(m.includes('out of memory') || m.includes('cuda out'))
    return `メモリ不足です。他のアプリを閉じてから${ctx}を再試行してください。`;
  if(m.includes('model') && m.includes('not found'))
    return 'AIモデルが見つかりません。設定画面でモデルを確認してください。';
  if(m.includes('disk') || m.includes('storage') || m.includes('no space'))
    return 'ディスクの空き容量が不足しています。不要なファイルを削除してください。';
  if(m.includes('ffmpeg'))
    return 'ffmpegが見つかりません。インストール後にページを再読み込みしてください。';
  if(m.includes('network') || m.includes('socket'))
    return `ネットワークエラーが発生しました。接続状況を確認して${ctx}を再試行してください。`;

  return `エラーが発生しました：${msg}`;
}

// ── 進捗バー表示 ──────────────────────────────────
let _progressTimer = null;

function startProgressPolling(recordId) {
  stopProgressPolling();
  showProgressBar(recordId, '処理開始…', 0, 0);
  _progressTimer = setInterval(async () => {
    try {
      const res  = await fetch('/api/transcribe/progress');
      const data = await res.json();
      if(data.record_id !== recordId) return;
      const elapsed = data.elapsed || 0;
      showProgressBar(recordId, data.message || '', data.progress || 0, elapsed);
      if(data.status === 'done' || data.status === 'error') {
        stopProgressPolling();
        hideProgressBar(recordId);
      }
    } catch(e) {}
  }, 1500);
}

function stopProgressPolling() {
  if(_progressTimer) { clearInterval(_progressTimer); _progressTimer = null; }
}

function showProgressBar(recordId, message, pct, elapsed) {
  let bar = document.getElementById(`progress-bar-${recordId}`);
  if(!bar) {
    const item = document.getElementById(`history-${recordId}`);
    if(!item) return;
    bar = document.createElement('div');
    bar.id = `progress-bar-${recordId}`;
    bar.style.cssText = 'margin:8px 0 4px;';
    const actionsEl = item.querySelector('.history-actions');
    if(actionsEl) actionsEl.insertAdjacentElement('beforebegin', bar);
    else item.appendChild(bar);
  }
  const min     = String(Math.floor(elapsed / 60)).padStart(2,'0');
  const sec     = String(elapsed % 60).padStart(2,'0');
  const timeStr = elapsed > 0 ? ` (${min}:${sec})` : '';
  bar.innerHTML = `
    <div style="font-size:11px;color:#aaa;margin-bottom:4px;">${message}${timeStr}</div>
    <div style="background:#2a2a3e;border-radius:4px;height:8px;overflow:hidden;">
      <div style="height:100%;background:linear-gradient(90deg,#7C6AF7,#5B4AF7);border-radius:4px;
                  width:${pct}%;transition:width .4s ease;"></div>
    </div>`;
}

function hideProgressBar(recordId) {
  const bar = document.getElementById(`progress-bar-${recordId}`);
  if(bar) bar.remove();
}

async function retryClean(recordId) {
  if (!confirm('クリーニングを再実行しますか？')) return;
  setRetryState(recordId, 'cleaning');
  startProgressPolling(recordId);
  try {
    const res  = await fetch('/api/clean', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ record_id: recordId }),
    });
    const data = await res.json();
    stopProgressPolling();
    hideProgressBar(recordId);
    if(data.status === 'done') {
      showToast('✅ クリーニングが完了しました');
      await loadHistory();
    } else {
      setRetryState(recordId, 'idle');
      showToast('❌ 失敗: ' + (data.message || 'エラー'));
    }
  } catch(e) {
    stopProgressPolling(); hideProgressBar(recordId);
    setRetryState(recordId, 'idle');
    showToast('❌ ネットワークエラー');
  }
}

async function retryTranscribe(recordId) {
  if (!confirm('文字起こしと要約を再実行しますか？')) return;
  setRetryState(recordId, 'transcribing');
  startProgressPolling(recordId);
  try {
    const res  = await fetch('/api/transcribe', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ record_id: recordId }),
    });
    const data = await res.json();
    stopProgressPolling();
    hideProgressBar(recordId);
    if(data.status === 'done') {
      showToast('✅ 文字起こし・要約が完了しました');
      await loadHistory();
    } else {
      setRetryState(recordId, 'idle');
      showToast('❌ 失敗: ' + (data.message || 'エラー'));
    }
  } catch(e) {
    stopProgressPolling(); hideProgressBar(recordId);
    setRetryState(recordId, 'idle');
    showToast('❌ ネットワークエラー');
  }
}

async function retrySummary(recordId) {
  if (!confirm('要約を再実行しますか？')) return;
  const extraPromptEl = document.getElementById(`extra-prompt-${recordId}`);
  const extraPrompt   = extraPromptEl ? extraPromptEl.value.trim() : '';
  setRetryState(recordId, 'summarizing');
  startProgressPolling(recordId);
  try {
    const res  = await fetch('/api/summarize', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ record_id: recordId, extra_prompt: extraPrompt }),
    });
    const data = await res.json();
    stopProgressPolling();
    hideProgressBar(recordId);
    if(data.status === 'done') {
      showToast('✅ 要約が完了しました');
      await loadHistory();
    } else {
      setRetryState(recordId, 'idle');
      showToast('❌ 失敗: ' + (data.message || 'エラー'));
    }
  } catch(e) {
    stopProgressPolling(); hideProgressBar(recordId);
    setRetryState(recordId, 'idle');
    showToast('❌ ネットワークエラー');
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

async function updateRecordingCategory(recordId, categoryId) {
  try {
    await fetch(`/api/recordings/${recordId}/category`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category_id: parseInt(categoryId) }),
    });
    showToast('✅ カテゴリを変更しました');
    await loadHistory();
  } catch (e) {
    showToast('❌ カテゴリの変更に失敗しました');
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
  if (!confirm('COVEを終了しますか？')) return;
  try {
    await fetch('/api/shutdown', { method: 'POST' });
  } catch (e) {
    // サーバー終了でfetchが失敗するのは正常
  }
  window.close();
  // window.closeが効かないブラウザ向けのフォールバック
  setTimeout(() => {
    document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:Arial;color:#888;font-size:18px;">COVEを終了しました。このタブを閉じてください。</div>';
  }, 500);
}
