/* ══════════════════════════════════════════════════
   COVE - settings.js
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
};

async function loadPersonas() {
  const list = document.getElementById('personaList');
  if(!list) return;
  try {
    const res = await fetch('/api/personas');
    _personas = await res.json();
    list.innerHTML = '';
    _personas.forEach(p => {
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

  if(nameOrNull) {
    const p = _personas.find(x => x.persona_name === nameOrNull);
    document.getElementById('personaModalTitle').textContent = 'ペルソナを編集';
    document.getElementById('pName').value    = p ? p.persona_name   : '';
    document.getElementById('pRole').value    = p ? (p.role || '')   : '';
    document.getElementById('pPrompt').value  = p ? (p.system_prompt || '') : '';
    document.getElementById('pEnabled').checked = p ? !!p.enabled    : true;
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
