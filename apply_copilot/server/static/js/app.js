// Apply Copilot — dashboard SPA
const $ = (sel, el=document) => el.querySelector(sel);
const $$ = (sel, el=document) => Array.from(el.querySelectorAll(sel));

// ─── Tab navigation ────────────────────────────────────────────────────────

function showTab(name) {
  $$('nav button').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  $$('main section.tab').forEach(s =>
    s.classList.toggle('active', s.id === 'tab-' + name));
  if (name === 'resumes') loadResumes();
  if (name === 'apps') loadApplications();
  if (name === 'autopilot') refreshAutopilotStatus();
  if (name === 'kb') loadProjectKB();
  if (name === 'editor') loadEditorList();
}
$$('nav button').forEach(b => b.onclick = () => showTab(b.dataset.tab));

// ─── Diagnostics (does the server have an OpenAI key?) ────────────────────

async function loadDiag() {
  try {
    const r = await fetch('/api/settings').then(r => r.json());
    $('#diag').textContent = r.openai_key_set
      ? `✓ key set · data: ${r.data_root}`
      : '⚠ OPENAI_API_KEY not set';
  } catch (e) {
    $('#diag').textContent = '⚠ server down?';
  }
}

// ─── Profile form ──────────────────────────────────────────────────────────

async function loadProfile() {
  const d = await fetch('/api/profile').then(r => r.json());
  const f = $('#profile-form');
  for (const [k, v] of Object.entries(d)) {
    const input = f.querySelector(`[name="${k}"]`);
    if (input) input.value = v ?? '';
  }
}

$('#profile-form').onsubmit = async (e) => {
  e.preventDefault();
  const data = {};
  new FormData(e.target).forEach((v, k) => { data[k] = v; });
  const r = await fetch('/api/profile', {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data),
  });
  $('#profile-status').textContent = r.ok ? '✓ saved ' + new Date().toLocaleTimeString() : '✗ error';
  setTimeout(() => $('#profile-status').textContent = '', 3000);
};

// ─── Resume upload ─────────────────────────────────────────────────────────

async function loadResumes() {
  const items = await fetch('/api/resumes').then(r => r.json());
  const tbody = $('#resume-list tbody');
  tbody.innerHTML = items.map(r => `
    <tr>
      <td>${esc(r.direction)}</td>
      <td>${esc(r.label)}</td>
      <td><a href="/api/resumes/${r.id}/download">${esc(r.filename)}</a></td>
      <td>${r.is_default ? '⭐' : ''}</td>
      <td>${esc(r.uploaded_at.split('T')[0])}</td>
      <td><button onclick="deleteResume(${r.id})">🗑</button></td>
    </tr>
  `).join('') || '<tr><td colspan="6" class="hint">No resumes uploaded yet.</td></tr>';
}

$('#resume-upload-form').onsubmit = async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  if (!fd.get('is_default')) fd.set('is_default', 'false');
  const r = await fetch('/api/resumes', {method: 'POST', body: fd});
  if (r.ok) {
    e.target.reset();
    loadResumes();
  } else {
    const err = await r.json().catch(() => ({detail: 'upload failed'}));
    alert('Upload failed: ' + (err.detail || 'unknown error'));
  }
};

async function deleteResume(id) {
  if (!confirm('Delete this resume?')) return;
  await fetch('/api/resumes/' + id, {method: 'DELETE'});
  loadResumes();
}
window.deleteResume = deleteResume;

// ─── Autopilot ─────────────────────────────────────────────────────────────

$('#autopilot-form').onsubmit = async (e) => {
  e.preventDefault();
  const data = {};
  new FormData(e.target).forEach((v, k) =>
    data[k] = (k === 'max_jobs') ? parseInt(v, 10) : v);
  const r = await fetch('/api/autopilot/start', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    alert('Start failed: ' + (j.detail || 'unknown'));
    return;
  }
  $('#autopilot-status').textContent = `✓ running pid=${j.pid}`;
  refreshAutopilotStatus();
};

$('#autopilot-stop').onclick = async () => {
  await fetch('/api/autopilot/stop', {method: 'POST'});
  refreshAutopilotStatus();
};

let _logTimer = null;
async function refreshAutopilotStatus() {
  const s = await fetch('/api/autopilot/status').then(r => r.json());
  $('#autopilot-status').textContent = s.running ? `▶ running pid=${s.pid}` : '⏸ stopped';
  const log = await fetch('/api/autopilot/log').then(r => r.json());
  const pre = $('#autopilot-log');
  if (pre) {
    pre.textContent = (log.lines || []).join('\n');
    pre.scrollTop = pre.scrollHeight;
  }
  if (s.running) {
    clearTimeout(_logTimer);
    _logTimer = setTimeout(refreshAutopilotStatus, 3000);
  }
}

// ─── Applications list ─────────────────────────────────────────────────────

async function loadApplications() {
  const search = $('#apps-search').value.toLowerCase();
  const emp = $('#apps-employment').value;
  const status = $('#apps-status').value;
  const qs = new URLSearchParams();
  if (emp) qs.set('employment_type', emp);
  if (status) qs.set('status', status);
  const data = await fetch('/api/applications?' + qs).then(r => r.json());
  let items = data.items || [];
  if (search) {
    items = items.filter(i =>
      (i.company + ' ' + i.title + ' ' + i.url).toLowerCase().includes(search));
  }
  const tbody = $('#apps-list tbody');
  tbody.innerHTML = items.map(r => `
    <tr data-bundle="${esc(r.bundle)}">
      <td><input type="checkbox" ${r.manual_checked ? 'checked' : ''}
                 onchange="setChecked('${esc(r.bundle)}', this.checked)" /></td>
      <td><span class="status-badge status-${r.status}">${esc(r.status)}</span></td>
      <td>
        <strong>${esc(r.company)}</strong><br>
        <a href="${esc(r.url)}" target="_blank">${esc(r.title)}</a>
      </td>
      <td>${esc(r.employment_type)}</td>
      <td>${esc(r.direction)}</td>
      <td>${r.coverage_pct}%</td>
      <td>${esc((r.submitted_at || '').split('T')[0])}</td>
      <td></td>
    </tr>
  `).join('') || '<tr><td colspan="8" class="hint">No applications yet.</td></tr>';
}

async function setChecked(bundle, checked) {
  await fetch(`/api/applications/${encodeURIComponent(bundle)}/state`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({checked}),
  });
}
window.setChecked = setChecked;

$('#apps-search').oninput = loadApplications;
$('#apps-employment').onchange = loadApplications;
$('#apps-status').onchange = loadApplications;

// ─── Project KB ────────────────────────────────────────────────────────────

async function loadProjectKB() {
  const data = await fetch('/api/project-kb').then(r => r.json());
  const tbody = $('#kb-list tbody');
  tbody.innerHTML = (data.items || []).map(p => `
    <tr>
      <td><code>${esc(p.id)}</code></td>
      <td>${esc(p.preview)}</td>
      <td>${p.chars} chars</td>
      <td>
        <button onclick="editProjectKB('${esc(p.id)}')">✏ Edit</button>
        <button onclick="deleteProjectKB('${esc(p.id)}')">🗑</button>
      </td>
    </tr>
  `).join('') || '<tr><td colspan="4" class="hint">No projects yet. Add one above.</td></tr>';
}

async function editProjectKB(id) {
  const d = await fetch('/api/project-kb/' + encodeURIComponent(id)).then(r => r.json());
  const f = $('#kb-form');
  f.elements.project_id.value = d.id;
  f.elements.content.value = d.content;
  f.elements.project_id.focus();
}
window.editProjectKB = editProjectKB;

async function deleteProjectKB(id) {
  if (!confirm(`Delete project "${id}"?`)) return;
  await fetch('/api/project-kb/' + encodeURIComponent(id), {method: 'DELETE'});
  loadProjectKB();
}
window.deleteProjectKB = deleteProjectKB;

$('#kb-form').onsubmit = async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const id = (fd.get('project_id') || '').trim();
  const content = (fd.get('content') || '').trim();
  if (!id || !content) return;
  const r = await fetch('/api/project-kb/' + encodeURIComponent(id), {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({content}),
  });
  const j = await r.json().catch(() => ({}));
  $('#kb-status').textContent = r.ok ? `✓ saved (${j.chars} chars)` : '✗ ' + (j.detail || 'error');
  setTimeout(() => $('#kb-status').textContent = '', 3000);
  if (r.ok) {
    e.target.reset();
    loadProjectKB();
  }
};

// ─── Resume Editor ─────────────────────────────────────────────────────────

let _editorActiveId = null;

async function loadEditorList() {
  const items = await fetch('/api/resumes').then(r => r.json());
  const ul = $('#editor-resume-list');
  if (!items.length) {
    ul.innerHTML = '<li class="hint" style="padding:8px;">No resumes uploaded yet — use the Resumes tab.</li>';
    return;
  }
  ul.innerHTML = items.map(r => `
    <li style="padding:8px; border-bottom:1px solid var(--border); cursor:pointer; ${_editorActiveId === r.id ? 'background:#dbeafe;' : ''}"
        onclick="selectEditorResume(${r.id})">
      <strong>${esc(r.label)}</strong>
      <div class="hint" style="font-size:11px;">${esc(r.direction)} · ${esc(r.filename.slice(0, 30))}${r.filename.length > 30 ? '…' : ''}</div>
    </li>
  `).join('');
}

async function selectEditorResume(id) {
  _editorActiveId = id;
  loadEditorList();
  $('#editor-preview').innerHTML = '<span class="hint">Loading preview…</span>';
  $('#editor-preview-lang').textContent = '';
  try {
    const d = await fetch(`/api/resumes/${id}/preview`).then(r => r.json());
    if (!d.paragraphs) {
      $('#editor-preview').innerHTML = '<span class="hint">No content parsed.</span>';
      return;
    }
    $('#editor-preview-lang').textContent = `(detected: ${d.language})`;
    $('#editor-preview').innerHTML = d.paragraphs.map(p => {
      const tag = p.is_bullet ? `<div style="padding-left:16px;">• ${esc(p.text)}</div>`
                              : (/heading/i.test(p.style)
                                  ? `<h4 style="margin:8px 0 4px;">${esc(p.text)}</h4>`
                                  : `<p style="margin:4px 0;${p.bold ? 'font-weight:600;' : ''}">${esc(p.text)}</p>`);
      return tag;
    }).join('');
  } catch (e) {
    $('#editor-preview').innerHTML = `<span class="hint">Preview failed: ${esc(String(e))}</span>`;
  }
}
window.selectEditorResume = selectEditorResume;

async function _editorTranslate(lang) {
  if (!_editorActiveId) { alert('Pick a resume first.'); return; }
  setEditorStatus('Translating…');
  const r = await fetch(`/api/resumes/${_editorActiveId}/translate`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({target_lang: lang}),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { setEditorStatus('✗ ' + (j.detail || 'translate failed')); return; }
  setEditorStatus(`✓ saved as id=${j.id} (${j.summary.translated}/${j.summary.total_paragraphs} paragraphs)`);
  loadEditorList();
  _editorActiveId = j.id;
  await selectEditorResume(j.id);
}

$('#editor-translate-zh').onclick = () => _editorTranslate('zh');
$('#editor-translate-en').onclick = () => _editorTranslate('en');

$('#editor-refresh').onclick = loadEditorList;

$('#editor-download').onclick = () => {
  if (!_editorActiveId) { alert('Pick a resume first.'); return; }
  window.location = `/api/resumes/${_editorActiveId}/download`;
};

$('#editor-render').onclick = () => {
  if (!_editorActiveId) { alert('Pick a resume first.'); return; }
  window.open(`/api/resumes/${_editorActiveId}/render`, '_blank');
};

$('#editor-skills-apply').onclick = async () => {
  if (!_editorActiveId) { alert('Pick a resume first.'); return; }
  const cat = $('#editor-skills-cat').value.trim();
  const kw = $('#editor-skills-kw').value.split(',').map(s => s.trim()).filter(Boolean);
  if (!cat || !kw.length) { alert('Need both category and at least one keyword.'); return; }
  await _editorApplyEdits([{type: 'skills_add', category: cat, keywords: kw}]);
};

$('#editor-bullet-apply').onclick = async () => {
  if (!_editorActiveId) { alert('Pick a resume first.'); return; }
  const anchor = $('#editor-anchor').value.trim();
  const add = $('#editor-addition').value.trim();
  if (!anchor || !add) { alert('Need both anchor and phrase.'); return; }
  await _editorApplyEdits([{type: 'bullet_inject', anchor: anchor, addition: add}]);
};

async function _editorApplyEdits(edits) {
  setEditorStatus('Applying…');
  const r = await fetch(`/api/resumes/${_editorActiveId}/edit`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({edits, enforce_page_limit: true}),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { setEditorStatus('✗ ' + (j.detail || 'edit failed')); return; }
  const ed = j.edits || {};
  setEditorStatus(`✓ saved id=${j.id} · applied ${ed.applied?.length ?? 0}, skipped ${ed.skipped?.length ?? 0}`);
  loadEditorList();
  _editorActiveId = j.id;
  await selectEditorResume(j.id);
}

function setEditorStatus(msg) {
  $('#editor-action-status').textContent = msg;
  setTimeout(() => {
    if ($('#editor-action-status').textContent === msg) {
      $('#editor-action-status').textContent = '';
    }
  }, 6000);
}

// ─── Util ───────────────────────────────────────────────────────────────

function esc(s) {
  return String(s ?? '').replace(/[<>&"']/g, c =>
    ({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":'&#39;'}[c]));
}

// ─── Boot ──────────────────────────────────────────────────────────────────

loadDiag();
loadProfile();
