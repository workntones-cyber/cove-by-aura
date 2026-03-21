/* ══════════════════════════════════════════════════
   AURA - settings.js
   設定画面の制御（settings.html 専用）
   ══════════════════════════════════════════════════ */

let currentMode = 'personal';
let apiKeyVisible = false;

// ── 初期化 ────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  await loadSettings();
  await loadCategories();
});


// ══════════════════════════════════════════════════
//  カテゴリ管理
// ══════════════════════════════════════════════════

let _categories = [];

async function loadCategories() {
  try {
    const res  = await fetch('/api/categories');
    _categories = await res.json();
    renderCategoryList();
    renderDeleteByCategorySelect();
  } catch (e) {
    console.error('カテゴリ取得エラー', e);
  }
}

function renderCategoryList() {
  const el = document.getElementById('categoryList');
  if (!el) return;

  if (_categories.length === 0) {
    el.innerHTML = '<p style="color:var(--muted);font-size:12px;">カテゴリがありません</p>';
    return;
  }

  el.innerHTML = _categories.map(cat => `
    <div style="display:flex; align-items:center; gap:8px; padding:8px 0; border-bottom:1px solid var(--border);">
      <span style="width:16px;height:16px;border-radius:50%;background:${cat.color};flex-shrink:0;"></span>
      ${cat.id === 1
        ? `<span style="flex:1; font-size:13px; color:var(--muted);">${escHtml(cat.name)}（削除不可）</span>`
        : `<input class="api-key-input" value="${escHtml(cat.name)}" id="cat-name-${cat.id}"
            style="flex:1; padding:4px 8px; font-size:13px;" maxlength="20" />
           <input type="color" value="${cat.color}" id="cat-color-${cat.id}"
            style="width:32px;height:32px;border:none;border-radius:6px;cursor:pointer;background:none;" />
           <button onclick="saveCategory(${cat.id})"
            style="padding:4px 10px;font-size:12px;border-radius:6px;border:1px solid var(--accent);
                   background:transparent;color:var(--accent);cursor:pointer;">保存</button>
           <button onclick="deleteCategory(${cat.id})"
            style="padding:4px 10px;font-size:12px;border-radius:6px;border:1px solid #dc3545;
                   background:transparent;color:#dc3545;cursor:pointer;">削除</button>`
      }
    </div>
  `).join('');
}

function renderDeleteByCategorySelect() {
  const sel = document.getElementById('deleteByCategorySelect');
  if (!sel) return;
  sel.innerHTML = _categories.map(cat =>
    `<option value="${cat.id}">${cat.name}</option>`
  ).join('');
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

async function addCategory() {
  const nameEl  = document.getElementById('newCategoryName');
  const colorEl = document.getElementById('newCategoryColor');
  const name    = nameEl.value.trim();
  if (!name) { showToast('❌ カテゴリ名を入力してください'); return; }

  const res  = await fetch('/api/categories', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, color: colorEl.value }),
  });
  const data = await res.json();
  if (data.status === 'ok') {
    nameEl.value = '';
    colorEl.value = '#6B7280';
    showToast('✅ カテゴリを追加しました');
    await loadCategories();
  } else {
    showToast('❌ ' + (data.message || 'エラーが発生しました'));
  }
}

async function saveCategory(id) {
  const name  = document.getElementById(`cat-name-${id}`)?.value.trim();
  const color = document.getElementById(`cat-color-${id}`)?.value;
  if (!name) { showToast('❌ カテゴリ名を入力してください'); return; }

  const res  = await fetch(`/api/categories/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, color }),
  });
  const data = await res.json();
  if (data.status === 'ok') {
    showToast('✅ カテゴリを更新しました');
    await loadCategories();
  } else {
    showToast('❌ ' + (data.message || 'エラーが発生しました'));
  }
}

async function deleteCategory(id) {
  const cat = _categories.find(c => c.id === id);
  if (!cat) return;
  if (!confirm(`カテゴリ「${cat.name}」を削除しますか？\nこのカテゴリのデータは「未分類」に移動します。`)) return;

  const res  = await fetch(`/api/categories/${id}`, { method: 'DELETE' });
  const data = await res.json();
  if (data.status === 'ok') {
    showToast('✅ カテゴリを削除しました');
    await loadCategories();
  } else {
    showToast('❌ ' + (data.message || 'エラーが発生しました'));
  }
}

async function confirmDeleteByCategory() {
  const sel = document.getElementById('deleteByCategorySelect');
  if (!sel) return;
  const id  = parseInt(sel.value);
  const cat = _categories.find(c => c.id === id);
  if (!cat) return;
  if (!confirm(`カテゴリ「${cat.name}」の録音データをすべて削除しますか？\nこの操作は取り消せません。`)) return;

  const res  = await fetch(`/api/categories/${id}/recordings`, { method: 'DELETE' });
  const data = await res.json();
  if (data.status === 'ok') {
    showToast(`✅ ${data.deleted}件の録音データを削除しました`);
  } else {
    showToast('❌ ' + (data.message || 'エラーが発生しました'));
  }
}

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

    // Ollamaモデル一覧を取得して反映
    await loadOllamaModels(data.ollama_model || 'llama3.1:8b');

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
    document.getElementById('ollamaSection').style.display = 'none';
  } else {
    document.getElementById('card-business').classList.add('active-business');
    if (showNotice) {
      document.getElementById('businessNotice').classList.add('visible');
    }
    document.getElementById('groqSection').style.display = 'none';
    document.getElementById('ollamaSection').style.display = 'block';
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
      ollama_model:     (document.getElementById('ollamaModelSelect') || {}).value || 'llama3.1:8b',
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
    // ビジネス用モードの場合はモデルダウンロード進捗を表示
    if (currentMode === 'business') {
      startModelStatusPolling();
    } else {
      hideModelStatus();
    }
  } else {
    showToast('❌ 保存に失敗しました');
  }
}

// ── Ollamaモデル一覧を動的取得 ────────────────────
async function loadOllamaModels(currentModel) {
  const sel = document.getElementById('ollamaModelSelect');
  if (!sel) return;
  try {
    const res  = await fetch('/api/ollama/models');
    const data = await res.json();
    if (data.models && data.models.length > 0) {
      sel.innerHTML = data.models.map(m =>
        `<option value="${m}" ${m === currentModel ? 'selected' : ''}>${getModelLabel(m)}</option>`
      ).join('');
    } else {
      sel.innerHTML = `<option value="${currentModel}">${currentModel}</option>`;
    }
  } catch (e) {
    sel.innerHTML = `<option value="${currentModel}">${currentModel}</option>`;
  }
}

// ── Ollamaモデルの表示名変換 ──────────────────────
function getModelLabel(modelName) {
  const labels = {
    'llama3.1:8b':  '標準モード（処理が速い）',
    'llama3.1:70b': '高精度モード（処理に時間がかかる）',
    'llama3.3:70b': '高精度モード・最新版（処理に時間がかかる）',
    'gemma3:27b':   '高精度モード・日本語特化（処理に時間がかかる）',
    'gemma3:12b':   'バランスモード・日本語特化',
    'gemma3:4b':    '軽量モード・日本語特化（処理が速い）',
    'mistral:7b':   '標準モード',
    'mixtral:8x7b': '高精度モード',
  };
  return labels[modelName] || modelName;
}

// ── モデルダウンロード進捗 ────────────────────────
let _modelPollingTimer = null;

function startModelStatusPolling() {
  if (_modelPollingTimer) return; // すでにポーリング中
  showModelStatus('⏳ AIモデルを確認中...');
  _modelPollingTimer = setInterval(async () => {
    try {
      const res  = await fetch('/api/model/status');
      const data = await res.json();
      if (data.status === 'loading') {
        showModelStatus('⏳ AIモデルをロード中です。このまましばらくお待ちください...');
      } else if (data.status === 'ready') {
        showModelStatus('✅ AIモデルの準備が完了しました。録音を開始できます。', 'ready');
        clearInterval(_modelPollingTimer);
        _modelPollingTimer = null;
        setTimeout(hideModelStatus, 5000);
      } else if (data.status === 'error') {
        showModelStatus(`❌ モデルのロードに失敗しました: ${data.error}`, 'error');
        clearInterval(_modelPollingTimer);
        _modelPollingTimer = null;
      }
      // idle の場合はまだ開始前なので継続
    } catch (e) {}
  }, 3000);
}

function showModelStatus(msg, type = '') {
  let el = document.getElementById('modelStatusBar');
  if (!el) {
    el = document.createElement('div');
    el.id = 'modelStatusBar';
    el.className = 'model-status-bar';
    const notice = document.getElementById('businessNotice');
    if (notice) notice.appendChild(el);
  }
  el.textContent  = msg;
  el.className    = 'model-status-bar' + (type ? ' model-status-' + type : '');
}

function hideModelStatus() {
  const el = document.getElementById('modelStatusBar');
  if (el) el.remove();
}

// ページ読み込み時にビジネス用モードなら状態確認
async function checkModelStatusOnLoad() {
  try {
    const res  = await fetch('/api/model/status');
    const data = await res.json();
    if (data.status === 'loading') {
      startModelStatusPolling();
    } else if (data.status === 'ready') {
      showModelStatus('✅ AIモデルの準備が完了しています。', 'ready');
      setTimeout(hideModelStatus, 3000);
    }
  } catch (e) {}
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

    // Step3・4・5はチェックボックスの保存済み状態を復元
    [3, 4, 5].forEach(n => {
      const saved = localStorage.getItem(`macStep${n}`) === 'true';
      const cb    = document.getElementById(`checkStep${n}`);
      if (cb) cb.checked = saved;
      if (saved) markStepDone(n);
    });

    // 全ステップ完了済みなら完了表示
    if (hasBlackHole) checkAllStepsDone();

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
  if (checked) {
    markStepDone(n);
    checkAllStepsDone();
  } else {
    // チェックを外したら元に戻す
    const numEl = document.getElementById(`macStepNum${n}`);
    if (numEl) {
      numEl.textContent      = String(n);
      numEl.style.background = '';
    }
    const stepEl = document.getElementById(`macStep${n}`);
    if (stepEl) stepEl.style.opacity = '1';
    // 完了表示を非表示に戻す
    const allDone = document.getElementById('macAllDone');
    const steps   = document.getElementById('macGuideSteps');
    if (allDone) allDone.style.display = 'none';
    if (steps)   steps.style.opacity   = '1';
  }
}

function checkAllStepsDone() {
  const allChecked = [3, 4, 5].every(n =>
    localStorage.getItem(`macStep${n}`) === 'true'
  );
  if (!allChecked) return;

  // ステップをフェードアウト
  const steps = document.getElementById('macGuideSteps');
  if (steps) {
    steps.style.transition = 'opacity 0.8s';
    steps.style.opacity    = '0';
    setTimeout(() => {
      steps.style.display = 'none';
      // 完了メッセージを表示
      const allDone = document.getElementById('macAllDone');
      if (allDone) allDone.style.display = 'block';
    }, 800);
  }
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
