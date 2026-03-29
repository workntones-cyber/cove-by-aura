/* ══════════════════════════════════════════════════
   COVE - settings.js
   設定画面の制御（settings.html 専用）
   ══════════════════════════════════════════════════ */

let currentMode = 'ollama';
let apiKeyVisible = false;
let _providers = [];  // サーバーから取得したプロバイダー一覧

// ── 初期化 ────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  await loadProviders();
  await loadSettings();
  await loadCategories();
});

// ── LLMプロバイダー一覧をサーバーから取得して動的描画 ──
async function loadProviders() {
  try {
    const res = await fetch('/api/llm/providers');
    if (!res.ok) return;
    _providers = await res.json();
    renderModeCards();
  } catch (e) {
    console.error('プロバイダー取得エラー', e);
  }
}

// renderModeCards は不要（ドロップダウン形式のため削除）
function renderModeCards() { /* 廃止・ドロップダウン形式に移行 */ }

// ── プロバイダー表示メタ情報 ─────────────────────
const _PROVIDER_META = {
  ollama: { icon: '🏠', sub: '完全ローカル・無料'          },
  groq:   { icon: '⚡', sub: '高速クラウド・無料枠あり'     },
  openai: { icon: '🤖', sub: 'GPT-4o・従量課金'            },
  gemini: { icon: '✨', sub: 'Google Gemini・従量課金'      },
  claude: { icon: '🔷', sub: 'Anthropic Claude・従量課金'   },
};


// ── プロバイダーのスペック定義 ────────────────────
const _PROVIDER_SPECS = {
  ollama: [
    ['処理', '🏠 完全ローカル'],
    ['速度', '⚙️ GPU・メモリ性能に依存'],
    ['機密', '🔒 完全秘匿'],
    ['費用', '無料'],
  ],
  groq: [
    ['処理', '☁️ クラウド'],
    ['速度', '⚡ 高速・高精度'],
    ['機密', '📋 利用規約に準拠'],
    ['費用', '無料枠あり'],
  ],
  openai: [
    ['処理', '☁️ クラウド'],
    ['速度', '⚡ 高速・高精度'],
    ['機密', '📋 利用規約に準拠'],
    ['費用', '従量課金'],
  ],
  gemini: [
    ['処理', '☁️ クラウド'],
    ['速度', '⚡ 高速・高精度'],
    ['機密', '📋 利用規約に準拠'],
    ['費用', '従量課金'],
  ],
  claude: [
    ['処理', '☁️ クラウド'],
    ['速度', '⚡ 高速・高精度'],
    ['機密', '📋 利用規約に準拠'],
    ['費用', '従量課金'],
  ],
};

// ── クラウド／ローカル 切替 ───────────────────────
function selectLlmType(type, skipFlash = false) {
  document.getElementById('typeBtn-cloud').classList.toggle('active', type === 'cloud');
  document.getElementById('typeBtn-local').classList.toggle('active', type === 'local');

  const dropdownArea = document.getElementById('llmDropdownArea');
  if (!dropdownArea) return;
  dropdownArea.style.display = 'block';

  const filtered = type === 'local'
    ? _providers.filter(p => p.id === 'ollama')
    : _providers.filter(p => p.id !== 'ollama');

  _buildCustomOptions(filtered);
  // 先頭を選択
  if (filtered.length > 0) selectCustomOption(filtered[0].id, skipFlash);
}

// ── カスタムドロップダウン操作 ───────────────────
function _buildCustomOptions(providers) {
  const container = document.getElementById('cstOptions');
  if (!container) return;
  container.innerHTML = providers.map(p => {
    const meta = _PROVIDER_META[p.id] || { icon: '🤖', sub: '' };
    return `
      <div class="custom-select-option" id="cso-${p.id}" onclick="selectCustomOption('${p.id}')">
        <span class="cso-icon">${meta.icon}</span>
        <span class="cso-body">
          <div class="cso-name">${escHtml(p.name)}</div>
          <div class="cso-sub">${meta.sub}</div>
        </span>
        <span class="cso-check" id="cso-check-${p.id}" style="display:none;">✓</span>
      </div>`;
  }).join('');
}

function toggleCustomSelect() {
  const trigger = document.getElementById('cstTrigger');
  const options = document.getElementById('cstOptions');
  if (!trigger || !options) return;
  const isOpen = options.classList.contains('open');
  trigger.classList.toggle('open', !isOpen);
  options.classList.toggle('open', !isOpen);
}

function selectCustomOption(id, skipFlash = false) {
  // オプション一覧を閉じる
  document.getElementById('cstTrigger')?.classList.remove('open');
  document.getElementById('cstOptions')?.classList.remove('open');

  // チェックマーク更新
  document.querySelectorAll('.cso-check').forEach(el => el.style.display = 'none');
  document.querySelectorAll('.custom-select-option').forEach(el => el.classList.remove('selected'));
  const checkEl = document.getElementById('cso-check-' + id);
  if (checkEl) checkEl.style.display = 'block';
  const optEl = document.getElementById('cso-' + id);
  if (optEl) optEl.classList.add('selected');

  // トリガー表示を更新
  const meta = _PROVIDER_META[id] || { icon: '🤖', sub: '' };
  const p    = _providers.find(x => x.id === id);
  document.getElementById('cstIcon').textContent = meta.icon;
  document.getElementById('cstName').textContent = p ? p.name : id;

  currentMode = id;
  _updateSpecArea(id);
  _updateApiKeyArea(id);
  _updateOllamaSection(id);
}

// ドロップダウン外クリックで閉じる
document.addEventListener('click', e => {
  const sel = document.getElementById('customProviderSelect');
  if (sel && !sel.contains(e.target)) {
    document.getElementById('cstTrigger')?.classList.remove('open');
    document.getElementById('cstOptions')?.classList.remove('open');
  }
});

// ── onProviderSelectChange: 旧select用（後方互換・実質未使用） ──
function onProviderSelectChange(skipFlash = false) {}

// スペック説明を更新
function _updateSpecArea(mode) {
  const area    = document.getElementById('llmSpecArea');
  const content = document.getElementById('llmSpecContent');
  if (!area || !content) return;

  const specs = _PROVIDER_SPECS[mode];
  if (!specs) { area.style.display = 'none'; return; }

  const rows = specs.map(([label, value]) =>
    `<div class="mode-spec-row"><span class="mode-spec-label">${label}</span><span class="mode-spec-value">${value}</span></div>`
  ).join('');
  content.innerHTML = `<div class="llm-spec-box">${rows}</div>`;
  area.style.display = 'block';
}

// APIキー入力エリアを更新（Groq共通 → 固有APIキーの順）
function _updateApiKeyArea(mode) {
  const inlineArea = document.getElementById('apiKeyInlineArea');
  if (!inlineArea) return;

  if (mode === 'ollama') {
    inlineArea.style.display = 'none';
    return;
  }

  inlineArea.style.display = 'block';

  // Groq共通キー欄は常に先頭（クラウドモード時は常に表示）
  const groqInline = document.getElementById('apiInlineGroq');
  if (groqInline) {
    inlineArea.insertBefore(groqInline, inlineArea.firstChild);
  }

  // Groqキーの説明文をモードに応じて切り替え
  const groqDesc = document.getElementById('groqKeyDesc');
  if (groqDesc) {
    if (mode === 'groq') {
      groqDesc.textContent = '文字起こし・クリーニング・要約・相談・照会・保管庫整形すべてに使用します';
    } else {
      groqDesc.textContent = '文字起こしに使用します（クラウドモード共通）';
    }
  }

  // 固有キー欄：選択したAPIのみ表示（Groq選択時は非表示）
  ['openai', 'gemini', 'claude'].forEach(id => {
    const el = document.getElementById('apiInlineSection-' + id);
    if (!el) return;
    el.style.display = (mode === id) ? 'block' : 'none';
    // 固有キー欄はGroqの次に配置
    if (mode === id) inlineArea.appendChild(el);
  });
}

// Ollamaセクション（モデル選択・注意書き）の表示切替
function _updateOllamaSection(mode) {
  // 外部のollamaSectionは削除済み（枠内のollamaModelInlineで制御）
  const modelInline = document.getElementById('ollamaModelInline');
  if (modelInline) modelInline.style.display = mode === 'ollama' ? 'block' : 'none';

  const notice = document.getElementById('businessNotice');
  if (notice) {
    if (mode === 'ollama') {
      notice.classList.add('visible');
      notice.innerHTML = '⚠️ <strong>Ollama（ローカル）の動作要件</strong><br>GPU（VRAM 8GB以上）を推奨します。GPUがない場合もCPUで動作しますが、処理に数分かかる場合があります。初回起動時にモデルファイル（約3GB〜）を自動ダウンロードします。';
    } else {
      notice.classList.remove('visible');
      notice.innerHTML = '';
    }
  }
}


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
      ${cat.id === 1 || cat.name === '利用者情報'
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
  if (!confirm(`カテゴリ「${cat.name}」の録音・メモ・ファイル・Webデータをすべて削除しますか？\nこの操作は取り消せません。`)) return;

  const res  = await fetch(`/api/categories/${id}/data`, { method: 'DELETE' });
  const data = await res.json();
  if (data.status === 'ok') {
    showToast(`✅ ${data.deleted}件のデータを削除しました`);
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
    selectMode(data.ai_mode || 'ollama', false);

    // APIキーを反映（各フィールドに設定）
    const keyMap = {
      'groq_api_key':      'apiKeyGroq',
      'openai_api_key':    'apiKeyOpenai',
      'gemini_api_key':    'apiKeyGemini',
      'anthropic_api_key': 'apiKeyClaude',
    };
    Object.entries(keyMap).forEach(([dataKey, elId]) => {
      const el = document.getElementById(elId);
      if (el && data[dataKey]) el.value = data[dataKey];
    });

    // Ollamaモデル一覧を取得して反映
    await loadOllamaModels(data.ollama_model || 'gemma3:27b');

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

// ── selectMode: ドロップダウン形式への橋渡し ────────
// loadSettings から呼ばれる（初期値復元用）
function selectMode(mode, showNotice = true) {
  currentMode = mode;
  const type = (mode === 'ollama') ? 'local' : 'cloud';

  // スイッチボタンの見た目だけ更新（selectLlmTypeは呼ばない＝先頭自動選択を防ぐ）
  document.getElementById('typeBtn-cloud')?.classList.toggle('active', type === 'cloud');
  document.getElementById('typeBtn-local')?.classList.toggle('active', type === 'local');

  // ドロップダウンを正しいプロバイダーで構築してから値をセット
  const dropdownArea = document.getElementById('llmDropdownArea');
  if (dropdownArea) dropdownArea.style.display = 'block';

  const filtered = type === 'local'
    ? _providers.filter(p => p.id === 'ollama')
    : _providers.filter(p => p.id !== 'ollama');
  _buildCustomOptions(filtered);

  // 指定のmodeを選択状態にする
  selectCustomOption(mode, true); // skipFlash=true
}

// _flashApiKeySection: 点滅不要につき空実装
function _flashApiKeySection(el) {}

// ── APIキー表示切替（汎用） ──────────────────────
function toggleApiKeyVisibility(inputId, btn) {
  const input = document.getElementById(inputId);
  if (!input) return;
  const isPass = input.type === 'password';
  input.type   = isPass ? 'text' : 'password';
  if (btn) btn.textContent = isPass ? '隠す' : '表示';
}

// ── 設定保存 ──────────────────────────────────────
async function saveSettings() {
  // クラウドモード時はGroqキー必須（文字起こし共通）
  if (currentMode !== 'ollama') {
    const groqEl  = document.getElementById('apiKeyGroq');
    const groqKey = groqEl ? groqEl.value.trim() : '';
    if (!groqKey) {
      showToast('❌ Groq APIキーを入力してください（文字起こしに必要です）');
      return;
    }
  }

  const payload = {
    ai_mode:             currentMode,
    groq_api_key:        (document.getElementById('apiKeyGroq')    || {}).value || '',
    openai_api_key:      (document.getElementById('apiKeyOpenai')  || {}).value || '',
    gemini_api_key:      (document.getElementById('apiKeyGemini')  || {}).value || '',
    anthropic_api_key:   (document.getElementById('apiKeyClaude')  || {}).value || '',
    recording_source:    currentRecSource,
    ollama_model:        (document.getElementById('ollamaModelSelect') || {}).value || 'gemma3:27b',
  };

  const res  = await fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
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
    // Ollamaモードの場合はモデルダウンロード進捗を表示
    if (currentMode === 'ollama') {
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
    const nb = document.getElementById('businessNotice'); if (nb) nb.after(el);
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

// ══════════════════════════════════════════════════
//  ペルソナ管理
// ══════════════════════════════════════════════════

// ══════════════════════════════════════════════════
//  ペルソナ管理（CRUD）
// ══════════════════════════════════════════════════
let _personas = [];
let _editingPersonaName = null; // null=新規, string=編集中の元の名前

// ── デフォルトアイコンマップ（council.htmlと同期） ──
const PERSONA_IMG_MAP = {
  '戦略家':       'strategist',
  'リスク管理者': 'risk',
  'アナリスト':   'analyst',
  'クリエイター': 'creator',
  '法務・コンプラ':'legal',
  'ユーザー視点': 'user',
  'クレーマー':   'complainer',
  'マーケッター': 'marketer',
  'アーカイバー': 'archiver',
};

async function loadPersonas() {
  const list = document.getElementById('personaList');
  if(!list) return;
  try {
    const res = await fetch('/api/personas');
    _personas = await res.json();
    list.innerHTML = '';
    _personas.forEach(p => {
      // アーカイバーは照会室専用 → 設定画面に表示しない
      if(p.persona_name === 'アーカイバー') return;
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;align-items:center;gap:10px;padding:10px 12px;background:var(--bg2);border-radius:10px;border:1px solid var(--border);';

      const iconKey    = btoa(unescape(encodeURIComponent(p.persona_name))).replace(/=/g,'');
      const defaultKey = PERSONA_IMG_MAP[p.persona_name];
      const defaultSrc = defaultKey ? `/static/img/personas/${defaultKey}_wait.png` : null;
      const silhouetteSvg = `<svg viewBox="0 0 56 56" width="44" height="44"><circle cx="28" cy="28" r="28" fill="#9CA3AF"/><circle cx="28" cy="20" r="10" fill="#4B5563"/><ellipse cx="28" cy="46" rx="16" ry="12" fill="#4B5563"/></svg>`;
      const iconDivStyle = `width:44px;height:44px;border-radius:50%;border:2px solid var(--border);flex-shrink:0;overflow:hidden;background:#9CA3AF center/cover no-repeat;`;

      row.innerHTML = `
        <div style="flex-shrink:0;">
          <div id="icon-preview-${iconKey}" onclick="openPersonaModal('${escHtml(p.persona_name)}')"
            title="クリックして編集"
            style="${iconDivStyle}${defaultSrc ? `background-image:url('${defaultSrc}');` : ''}cursor:pointer;transition:opacity .2s;"
            onmouseover="this.style.opacity='.75'" onmouseout="this.style.opacity='1'">
            ${defaultSrc ? '' : silhouetteSvg}
          </div>
        </div>
        <div style="flex:1;min-width:0;">
          <div style="font-size:13px;font-weight:600;color:var(--text);">${escHtml(p.persona_name)}</div>
          <div style="font-size:11px;color:var(--muted);margin-top:2px;">${escHtml(p.role||'役割未設定')}</div>
        </div>
        <label style="display:flex;align-items:center;gap:6px;cursor:pointer;flex-shrink:0;">
          <span style="font-size:11px;color:var(--muted);" id="ptag-${escHtml(p.persona_name)}">${p.enabled ? 'ON' : 'OFF'}</span>
          <div style="position:relative;width:36px;height:20px;">
            <input type="checkbox" ${p.enabled ? 'checked' : ''}
              onchange="togglePersonaEnabled('${escHtml(p.persona_name)}', this)"
              style="opacity:0;position:absolute;width:100%;height:100%;cursor:pointer;margin:0;z-index:1;">
            <div style="position:absolute;inset:0;background:${p.enabled ? '#7C6AF7' : 'var(--border)'};border-radius:10px;transition:background .2s;" class="ptoggle-track"></div>
            <div style="position:absolute;top:2px;left:${p.enabled ? '18px' : '2px'};width:16px;height:16px;background:#fff;border-radius:50%;transition:left .2s;" class="ptoggle-thumb"></div>
          </div>
        </label>
        <button onclick="openPersonaModal('${escHtml(p.persona_name)}')"
          style="padding:4px 10px;border-radius:6px;border:1px solid var(--border);background:transparent;
                 color:var(--text);cursor:pointer;font-size:11px;font-family:inherit;flex-shrink:0;">✏️ 編集</button>
        <button onclick="deletePersona('${escHtml(p.persona_name)}')"
          style="padding:4px 10px;border-radius:6px;border:1px solid #dc3545;background:transparent;
                 color:#dc3545;cursor:pointer;font-size:11px;font-family:inherit;flex-shrink:0;">🗑️</button>`;
      list.appendChild(row);

      // カスタムアイコンがあれば上書き
      fetch(`/api/personas/${encodeURIComponent(p.persona_name)}/icon`)
        .then(r => r.json())
        .then(data => {
          const url = data.wait || data.think;
          if(url) {
            const el = document.getElementById(`icon-preview-${iconKey}`);
            if(el) {
              el.style.backgroundImage = `url('${url}?t=${Date.now()}')`;
              el.innerHTML = '';
            }
          }
        }).catch(()=>{});
    });
  } catch(e) {
    console.error('ペルソナ読み込みエラー:', e);
  }
}

async function togglePersonaEnabled(name, checkbox) {
  const enabled = checkbox.checked;
  const wrap    = checkbox.parentElement;
  wrap.querySelector('.ptoggle-track').style.background = enabled ? '#7C6AF7' : 'var(--border)';
  wrap.querySelector('.ptoggle-thumb').style.left       = enabled ? '18px' : '2px';
  const tag = document.getElementById(`ptag-${name}`);
  if(tag) tag.textContent = enabled ? 'ON' : 'OFF';
  try {
    await fetch(`/api/personas/${encodeURIComponent(name)}`, {
      method:'PUT', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ enabled }),
    });
    showToast(`${name} を${enabled ? 'ON' : 'OFF'}にしました`);
  } catch(e) { showToast('保存に失敗しました'); }
}

function openPersonaModal(nameOrNull) {
  _editingPersonaName = nameOrNull;
  const modal = document.getElementById('personaModal');
  modal.style.display = 'flex';

  // アイコンをリセット
  _resetModalIcon();

  // グループ選択肢を構築
  const pGroupSel = document.getElementById('pGroup');
  if (pGroupSel) {
    pGroupSel.innerHTML = _groups
      .filter(g => g.id !== 0)
      .map(g => `<option value="${g.id}">${escHtml(g.name)}</option>`)
      .join('');
  }

  if(nameOrNull) {
    const p = _personas.find(x => x.persona_name === nameOrNull);
    document.getElementById('personaModalTitle').textContent = 'ペルソナを編集';
    document.getElementById('pName').value    = p ? p.persona_name   : '';
    document.getElementById('pRole').value    = p ? (p.role || '')   : '';
    document.getElementById('pPrompt').value  = p ? (p.system_prompt || '') : '';
    document.getElementById('pEnabled').checked = p ? !!p.enabled    : true;
    // 現在所属しているグループを選択
    if (pGroupSel && nameOrNull) {
      const currentGroup = _groups.find(g => g.members.includes(nameOrNull));
      if (currentGroup) pGroupSel.value = currentGroup.id;
    }
    // 既存アイコンをプレビュー表示
    fetch(`/api/personas/${encodeURIComponent(nameOrNull)}/icon`)
      .then(r => r.json())
      .then(data => {
        if(data.wait)  {
          _setModalIconPreviewEl('wait',  data.wait);
        } else {
          // カスタムなし → デフォルトPNGがあれば表示
          const defaultKey = PERSONA_IMG_MAP[nameOrNull];
          if(defaultKey) _setModalIconPreviewEl('wait', `/static/img/personas/${defaultKey}_wait.png`);
        }
        if(data.think) _setModalIconPreviewEl('think', data.think);
        else if(PERSONA_IMG_MAP[nameOrNull]) {
          _setModalIconPreviewEl('think', `/static/img/personas/${PERSONA_IMG_MAP[nameOrNull]}_think.png`);
        }
      }).catch(()=>{});
  } else {
    document.getElementById('personaModalTitle').textContent = 'ペルソナを追加';
    document.getElementById('pName').value    = '';
    document.getElementById('pRole').value    = '';
    document.getElementById('pPrompt').value  = '';
    document.getElementById('pEnabled').checked = true;
  }
}

function closePersonaModal() {
  document.getElementById('personaModal').style.display = 'none';
  _editingPersonaName = null;
}

let _modalIconFiles  = { wait: null, think: null };
let _modalIconDelete = { wait: false, think: false };

function _resetModalIcon() {
  _modalIconFiles  = { wait: null, think: null };
  _modalIconDelete = { wait: false, think: false };
  _setModalIconPreviewEl('wait',  null);
  _setModalIconPreviewEl('think', null);
  const wi = document.getElementById('pIconWaitFile');
  const ti = document.getElementById('pIconThinkFile');
  if(wi) wi.value = '';
  if(ti) ti.value = '';
}

function _setModalIconPreviewEl(variant, url) {
  const previewId = variant === 'wait' ? 'pIconWaitPreview' : 'pIconThinkPreview';
  const delBtnId  = variant === 'wait' ? 'pIconWaitDelBtn'  : 'pIconThinkDelBtn';
  const silFill   = '#9CA3AF';
  const silDark   = '#4B5563';
  const preview   = document.getElementById(previewId);
  const delBtn    = document.getElementById(delBtnId);
  if(!preview) return;
  if(url) {
    // blob: URL にはキャッシュバスター不要、通常URLのみ付与
    const src = url.startsWith('blob:') ? url : `${url}?t=${Date.now()}`;
    preview.innerHTML = `<img src="${src}" style="width:100%;height:100%;object-fit:cover;">`;
    if(delBtn) delBtn.style.display = 'inline-block';
  } else {
    preview.innerHTML = `<svg viewBox="0 0 56 56" width="72" height="72"><circle cx="28" cy="28" r="28" fill="${silFill}"/><circle cx="28" cy="20" r="10" fill="${silDark}"/><ellipse cx="28" cy="46" rx="16" ry="12" fill="${silDark}"/></svg>`;
    if(delBtn) delBtn.style.display = 'none';
  }
}

function previewModalIcon(variant, input) {
  const file = input.files[0];
  if(!file) return;
  if(file.size > 2 * 1024 * 1024) { showToast('2MB以内のファイルを選択してください'); input.value=''; return; }
  _modalIconFiles[variant]  = file;
  _modalIconDelete[variant] = false;
  _setModalIconPreviewEl(variant, URL.createObjectURL(file));
}

function clearModalIcon(variant) {
  _modalIconFiles[variant]  = null;
  _modalIconDelete[variant] = true;
  _setModalIconPreviewEl(variant, null);
}

async function savePersona() {
  const name    = document.getElementById('pName').value.trim();
  const role    = document.getElementById('pRole').value.trim();
  const prompt  = document.getElementById('pPrompt').value.trim();
  const enabled = document.getElementById('pEnabled').checked;

  if(!name) { showToast('名前を入力してください'); return; }

  try {
    let res;
    if(_editingPersonaName) {
      res = await fetch(`/api/personas/${encodeURIComponent(_editingPersonaName)}`, {
        method:'PUT', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ persona_name: name, role, system_prompt: prompt, enabled }),
      });
    } else {
      res = await fetch('/api/personas', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ persona_name: name, role, system_prompt: prompt }),
      });
    }
    const data = await res.json();
    if(data.status !== 'ok') { showToast('エラー: ' + (data.message || '保存に失敗しました')); return; }

    // アイコンの処理（wait/think それぞれ）
    const targetName = name;
    for(const variant of ['wait', 'think']) {
      if(_modalIconDelete[variant]) {
        await fetch(`/api/personas/${encodeURIComponent(targetName)}/icon?variant=${variant}`, { method:'DELETE' }).catch(()=>{});
      } else if(_modalIconFiles[variant]) {
        const form = new FormData();
        form.append('file', _modalIconFiles[variant]);
        form.append('variant', variant);
        const iconRes  = await fetch(`/api/personas/${encodeURIComponent(targetName)}/icon`, { method:'POST', body:form }).catch(()=>null);
        if(iconRes) {
          const iconData = await iconRes.json().catch(()=>({}));
          if(iconData.status !== 'ok') showToast(`アイコン(${variant})の保存に失敗: ` + (iconData.message||''));
        }
      }
    }

    // グループ変更を反映
    const pGroupSel = document.getElementById('pGroup');
    if (pGroupSel) {
      const newGroupId  = parseInt(pGroupSel.value);
      const targetGroup = _groups.find(g => g.id === newGroupId);
      if (targetGroup) {
        // 旧名前・新名前どちらも除いてから新名前で追加（名前変更対応）
        const oldName    = _editingPersonaName || name;
        const cleanMembers = targetGroup.members.filter(m => m !== oldName && m !== name);
        const newMembers   = [...cleanMembers, name];
        await fetch(`/api/persona_groups/${newGroupId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: targetGroup.name, members: newMembers }),
        });
        await loadGroups();
      }
    }
    showToast(_editingPersonaName ? '更新しました ✓' : '追加しました ✓');
    closePersonaModal();
    await loadPersonas();
  } catch(e) { showToast('通信エラーが発生しました'); }
}

async function deletePersona(name) {
  if(!confirm(`ペルソナ「${name}」を削除しますか？\nこの操作は取り消せません。`)) return;
  try {
    await fetch(`/api/personas/${encodeURIComponent(name)}`, { method:'DELETE' });
    showToast(`${name} を削除しました`);
    await loadPersonas();
  } catch(e) { showToast('削除に失敗しました'); }
}

// モーダル外クリックで閉じる
document.addEventListener('click', (e) => {
  const modal = document.getElementById('personaModal');
  if(modal && e.target === modal) closePersonaModal();
});

// ページ読み込み時にペルソナも取得
document.addEventListener('DOMContentLoaded', () => {
  loadPersonas();
});

// ── 動作検証フラグ管理 ──────────────────────────────
function setDebugFlag(key, value) {
  if(value) {
    sessionStorage.setItem('cove_debug_' + key, '1');
  } else {
    sessionStorage.removeItem('cove_debug_' + key);
  }
  const label = { 
    ollama_disconnect: 'Ollama切断',
    memory_error:      'メモリ不足',
    disk_error:        'ディスク不足',
    model_not_found:   'モデル未インストール',
    ffmpeg_not_found:  'ffmpeg未インストール'
  }[key] || key;
  showToast(value ? `🧪 ${label} ON` : `✅ ${label} OFF`);
}

function resetAllDebugFlags() {
  ['ollama_disconnect','memory_error','disk_error','model_not_found','ffmpeg_not_found'].forEach(k => {
    sessionStorage.removeItem('cove_debug_' + k);
  });
  document.querySelectorAll('[id^="debug-"]').forEach(el => el.checked = false);
  showToast('✅ すべてのデバッグフラグをOFFにしました');
}

// 設定画面を開いたときにフラグの状態を反映
document.addEventListener('DOMContentLoaded', () => {
  const map = {
    'ollama_disconnect': 'debug-ollama',
    'memory_error':      'debug-memory',
    'disk_error':        'debug-disk',
    'model_not_found':   'debug-model',
    'ffmpeg_not_found':  'debug-ffmpeg',
  };
  Object.entries(map).forEach(([key, id]) => {
    const el = document.getElementById(id);
    if(el) el.checked = !!sessionStorage.getItem('cove_debug_' + key);
  });
});


// ══════════════════════════════════════════════════
//  グループ管理
// ══════════════════════════════════════════════════

let _groups        = [];
let _editingGroupId = null;

async function loadGroups() {
  try {
    const res = await fetch('/api/persona_groups');
    _groups   = await res.json();
    renderGroupList();
  } catch (e) {
    console.error('グループ取得エラー', e);
  }
}

function renderGroupList() {
  const el = document.getElementById('groupList');
  if (!el) return;
  el.innerHTML = _groups.map(g => {
    const isSystem = g.is_system === 1;
    return `
      <div style="display:inline-flex;align-items:center;gap:6px;padding:6px 12px;
                  border-radius:20px;border:1px solid var(--border);background:var(--bg);font-size:12px;">
        <span style="color:#e0e0e0;">${escHtml(g.name)}</span>
        <span style="color:var(--muted);font-size:10px;">${g.members.length}名</span>
        ${!isSystem ? `
          <button onclick="openGroupModal(${g.id})"
            style="background:transparent;border:none;color:#7C6AF7;cursor:pointer;font-size:11px;padding:0 2px;">✏️</button>
          <button onclick="deleteGroup(${g.id})"
            style="background:transparent;border:none;color:#E24B4A;cursor:pointer;font-size:11px;padding:0 2px;">🗑️</button>
        ` : `<span style="font-size:10px;color:var(--muted);">（固定）</span>`}
      </div>`;
  }).join('');
}

function openGroupModal(groupIdOrNull) {
  _editingGroupId = groupIdOrNull;
  const modal = document.getElementById('groupModal');
  modal.style.display = 'flex';

  const title = document.getElementById('groupModalTitle');
  const nameEl = document.getElementById('gName');

  if (groupIdOrNull) {
    const g = _groups.find(x => x.id === groupIdOrNull);
    title.textContent = 'グループを編集';
    nameEl.value = g ? g.name : '';
    _renderGroupMemberList(g ? g.members : []);
  } else {
    title.textContent = 'グループを追加';
    nameEl.value = '';
    _renderGroupMemberList([]);
  }
}

function _renderGroupMemberList(selectedMembers) {
  const el = document.getElementById('gMemberList');
  if (!el) return;
  // アーカイバーを除外したペルソナ一覧
  const personas = _personas.filter(p => p.persona_name !== 'アーカイバー');
  el.innerHTML = personas.map(p => {
    const checked = selectedMembers.includes(p.persona_name);
    return `
      <label style="display:flex;align-items:center;gap:6px;padding:4px 8px;border-radius:6px;
                    background:${checked ? 'rgba(124,106,247,0.15)' : 'var(--bg)'};
                    border:1px solid ${checked ? '#7C6AF7' : 'var(--border)'};cursor:pointer;font-size:12px;"
             id="gmLabel-${escHtml(p.persona_name)}">
        <input type="checkbox" value="${escHtml(p.persona_name)}"
          ${checked ? 'checked' : ''}
          onchange="onGroupMemberChange()"
          style="accent-color:#7C6AF7;">
        ${escHtml(p.persona_name)}
      </label>`;
  }).join('');
  _updateGroupMemberCount();
}

function onGroupMemberChange() {
  // 14名上限チェック
  const checked = document.querySelectorAll('#gMemberList input[type="checkbox"]:checked');
  if (checked.length > 14) {
    // 最後にチェックしたものを外す
    event.target.checked = false;
    showToast('❌ 1グループの上限は14名です');
    return;
  }
  // ラベルの色を更新
  document.querySelectorAll('#gMemberList input[type="checkbox"]').forEach(cb => {
    const label = cb.parentElement;
    if (cb.checked) {
      label.style.background = 'rgba(124,106,247,0.15)';
      label.style.borderColor = '#7C6AF7';
    } else {
      label.style.background = 'var(--bg)';
      label.style.borderColor = 'var(--border)';
    }
  });
  _updateGroupMemberCount();
}

function _updateGroupMemberCount() {
  const el      = document.getElementById('gMemberCount');
  const checked = document.querySelectorAll('#gMemberList input[type="checkbox"]:checked').length;
  if (el) el.textContent = `${checked} / 14名選択中`;
}

function closeGroupModal() {
  document.getElementById('groupModal').style.display = 'none';
  _editingGroupId = null;
}

async function saveGroup() {
  const name = document.getElementById('gName').value.trim();
  if (!name) { showToast('❌ グループ名を入力してください'); return; }

  const members = [...document.querySelectorAll('#gMemberList input[type="checkbox"]:checked')]
    .map(cb => cb.value);

  try {
    let res;
    if (_editingGroupId) {
      res = await fetch(`/api/persona_groups/${_editingGroupId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, members }),
      });
    } else {
      res = await fetch('/api/persona_groups', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
      const created = await res.json();
      if (created.status === 'ok' && members.length > 0) {
        await fetch(`/api/persona_groups/${created.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, members }),
        });
      }
    }
    showToast(_editingGroupId ? '✅ グループを更新しました' : '✅ グループを追加しました');
    closeGroupModal();
    await loadGroups();
  } catch (e) {
    showToast('❌ 保存に失敗しました');
  }
}

async function deleteGroup(groupId) {
  const g = _groups.find(x => x.id === groupId);
  if (!g) return;
  if (!confirm(`グループ「${g.name}」を削除しますか？\nメンバーは「グループなし」に移動します。`)) return;
  try {
    await fetch(`/api/persona_groups/${groupId}`, { method: 'DELETE' });
    showToast('✅ グループを削除しました');
    await loadGroups();
  } catch (e) {
    showToast('❌ 削除に失敗しました');
  }
}

// モーダル外クリックで閉じる
document.addEventListener('click', (e) => {
  const modal = document.getElementById('groupModal');
  if (modal && e.target === modal) closeGroupModal();
});

// ページ読み込み時にグループも取得
document.addEventListener('DOMContentLoaded', () => {
  loadGroups();
});
