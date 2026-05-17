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

// ─── Util ───────────────────────────────────────────────────────────────

function esc(s) {
  return String(s ?? '').replace(/[<>&"']/g, c =>
    ({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":'&#39;'}[c]));
}

// ─── Boot ──────────────────────────────────────────────────────────────────

loadDiag();
loadProfile();
