/* ══════════════════════════════════════════════════
   AURA - settings.js
   設定画面の制御（settings.html 専用）
   ══════════════════════════════════════════════════ */

let currentMode = 'personal';
let apiKeyVisible = false;

// ── 初期化 ────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  await loadSettings();
});

async function loadSettings() {
  try {
    const res = await fetch('/api/settings');
    if (!res.ok) return;
    const data = await res.json();

    // AIモードを反映
    selectMode(data.ai_mode || 'personal', false);

    // APIキーを反映
    if (data.groq_api_key) {
      document.getElementById('apiKeyInput').value = data.groq_api_key;
    }

    // 録音ソースを反映
    const recSource = data.recording_source || 'mic';
    selectRecSource(recSource, false);
    if (recSource === 'system') {
      await loadDevices(data.recording_device_id || '');
    }
  } catch (e) {
    // 設定未保存の場合はデフォルト値のまま
  }
}

// ── モード選択 ────────────────────────────────────
function selectMode(mode, showNotice = true) {
  currentMode = mode;

  document.getElementById('card-personal').className = 'mode-card';
  document.getElementById('card-business').className = 'mode-card';

  if (mode === 'personal') {
    document.getElementById('card-personal').classList.add('active-personal');
    document.getElementById('businessNotice').classList.remove('visible');
    document.getElementById('groqSection').style.display = 'block';
  } else {
    document.getElementById('card-business').classList.add('active-business');
    if (showNotice) {
      document.getElementById('businessNotice').classList.add('visible');
    }
    document.getElementById('groqSection').style.display = 'none';
  }
}

// ── APIキー表示切替 ───────────────────────────────
function toggleApiKeyVisibility() {
  apiKeyVisible = !apiKeyVisible;
  const input = document.getElementById('apiKeyInput');
  const btn   = document.querySelector('.api-key-toggle');
  input.type  = apiKeyVisible ? 'text' : 'password';
  btn.textContent = apiKeyVisible ? '隠す' : '表示';
}

// ── 設定保存 ──────────────────────────────────────
async function saveSettings() {
  const apiKey = document.getElementById('apiKeyInput').value.trim();

  if (currentMode === 'personal' && !apiKey) {
    showToast('❌ Groq APIキーを入力してください');
    return;
  }

  const res = await fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ai_mode:          currentMode,
      groq_api_key:     apiKey,
      recording_source: currentRecSource,
    }),
  });

  const data = await res.json();
  if (data.status === 'saved') {
    const btn = document.getElementById('saveBtn');
    btn.textContent = '✓ 保存しました';
    btn.classList.add('saved');
    setTimeout(() => {
      btn.textContent = '設定を保存';
      btn.classList.remove('saved');
    }, 2000);
    showToast('✅ 設定を保存しました');
  } else {
    showToast('❌ 保存に失敗しました');
  }
}

// ── ユーティリティ ────────────────────────────────
function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 3000);
}

// ── 全削除モーダル ────────────────────────────────
function confirmDeleteAll() {
  document.getElementById('deleteModal').classList.add('visible');
}

function closeModal() {
  document.getElementById('deleteModal').classList.remove('visible');
}

async function deleteAll() {
  closeModal();

  try {
    const res  = await fetch('/api/recordings/all', { method: 'DELETE' });
    const data = await res.json();
    if (data.status === 'deleted') {
      showToast(`🗑️ ${data.count}件のデータを削除しました`);
    } else {
      showToast('❌ ' + (data.message || '削除に失敗しました'));
    }
  } catch (e) {
    showToast('❌ ネットワークエラーが発生しました');
  }
}

// モーダル外クリックで閉じる
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('deleteModal').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeModal();
  });
});

// ── 録音ソース切替 ───────────────────────────────
let currentRecSource = 'system';

function selectRecSource(source, loadDev = true) {
  currentRecSource = source;

  document.querySelectorAll('.rec-source-card').forEach(c => c.classList.remove('selected'));
  document.getElementById(`src-${source}`)?.classList.add('selected');

  const area = document.getElementById('deviceSelectArea');
  if (source === 'system') {
    area.classList.add('visible');
    const isMac = navigator.platform.toUpperCase().includes('MAC') ||
                  navigator.userAgent.includes('Mac');
    // Windows
    document.getElementById('windowsNotice').style.display = isMac ? 'none' : 'block';
    // Mac
    const macGuide = document.getElementById('macGuide');
    if (macGuide) {
      macGuide.style.display = isMac ? 'block' : 'none';
      if (isMac) checkBlackHoleInSettings();
    }
  } else {
    area.classList.remove('visible');
  }
}

async function loadDevices(selectedId) {
  const select = document.getElementById('deviceSelect');
  try {
    const res     = await fetch('/api/devices');
    const devices = await res.json();
    select.innerHTML = '';

    // デフォルト選択肢
    const defOpt = document.createElement('option');
    defOpt.value = ''; defOpt.textContent = '-- デバイスを選択 --';
    select.appendChild(defOpt);

    devices.forEach(dev => {
      const opt = document.createElement('option');
      opt.value = dev.id;
      opt.textContent = dev.is_system_audio
        ? `⭐ ${dev.name} （システム音声）`
        : dev.name;
      if (dev.is_system_audio) opt.className = 'system-audio';
      if (String(dev.id) === String(selectedId)) opt.selected = true;
      select.appendChild(opt);
    });

    // システム音声デバイスが未選択なら自動で最初のものを選ぶ
    if (!selectedId) {
      const sysDev = devices.find(d => d.is_system_audio);
      if (sysDev) select.value = sysDev.id;
    }
  } catch (e) {
    select.innerHTML = '<option value="">デバイスの取得に失敗しました</option>';
  }
}

// ── Mac: 設定画面でのBlackHole検出チェック ──────
async function checkBlackHoleInSettings() {
  try {
    const res      = await fetch('/api/devices');
    const devices  = await res.json();
    const hasBlackHole = devices.some(d =>
      d.name.toLowerCase().includes('blackhole')
    );

    // Step1・2はBlackHole検出済みなら完了マーク
    if (hasBlackHole) {
      markStepDone(1);
      markStepDone(2);
      // タイトルを更新
      const title = document.getElementById('macGuideTitle');
      if (title) {
        title.innerHTML = '✅ <strong>BlackHole を検出しました。</strong>残りの手順を完了してください。';
        title.style.color = '#6EE7B7';
      }
    }

    // Step3・4はチェックボックスの保存済み状態を復元
    [3, 4].forEach(n => {
      const saved = localStorage.getItem(`macStep${n}`) === 'true';
      const cb    = document.getElementById(`checkStep${n}`);
      if (cb) cb.checked = saved;
      if (saved) markStepDone(n);
    });

  } catch (e) {}
}

function markStepDone(n) {
  const numEl = document.getElementById(`macStepNum${n}`);
  if (numEl) {
    numEl.textContent   = '✓';
    numEl.style.background = '#34D399';
  }
  const stepEl = document.getElementById(`macStep${n}`);
  if (stepEl) stepEl.style.opacity = '0.6';
}

function saveMacStepCheck(n, checked) {
  localStorage.setItem(`macStep${n}`, checked);
  if (checked) markStepDone(n);
  else {
    // チェックを外したら元に戻す
    const numEl = document.getElementById(`macStepNum${n}`);
    if (numEl) {
      numEl.textContent      = String(n);
      numEl.style.background = '';
    }
    const stepEl = document.getElementById(`macStep${n}`);
    if (stepEl) stepEl.style.opacity = '1';
  }
}
