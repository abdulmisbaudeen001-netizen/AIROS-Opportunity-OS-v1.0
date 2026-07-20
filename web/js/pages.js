/**
 * AIROS Opportunity OS — Page Renderers
 * Each export renders one section of the web UI into its container element.
 */

import api from './api.js';
import { toast } from './app.js';

function esc(str) {
  return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function fmt(date) {
  if (!date) return '—';
  return new Date(date).toLocaleDateString('en-GB', { day:'2-digit', month:'short', year:'numeric' });
}

function scoreColor(n) {
  if (n >= 80) return 'var(--green)';
  if (n >= 60) return 'var(--primary)';
  if (n >= 40) return 'var(--amber)';
  return 'var(--red)';
}

function categoryBadge(cat) {
  const map = {
    job:'badge-blue', scholarship:'badge-purple', fellowship:'badge-purple',
    grant:'badge-green', competition:'badge-amber', bootcamp:'badge-primary',
    conference:'badge-gray', research:'badge-blue', accelerator:'badge-green',
  };
  return `<span class="badge ${map[cat]||'badge-gray'}">${esc(cat)}</span>`;
}

function statusBadge(status) {
  const map = {
    submitted:'badge-green', awaiting_approval:'badge-amber',
    human_required:'badge-red', failed:'badge-red',
    skipped:'badge-gray', unknown:'badge-gray',
  };
  return `<span class="badge ${map[status]||'badge-gray'}">${esc(status?.replace('_',' '))}</span>`;
}

// ══════════════════════════════════════════════════════════════════
// DASHBOARD
// ══════════════════════════════════════════════════════════════════

export async function renderDashboard(container) {
  const data = await api.dashboard.get();

  const total_opps = data.total_opportunities || 0;
  const total_apps = data.total_applications || 0;
  const awaiting   = data.awaiting_approval  || 0;
  const interviews = data.interviews         || 0;
  const completeness = data.profile_completeness || 0;

  const last = data.last_mission || {};
  const summary = last.summary || {};

  container.innerHTML = `
    <div class="page-header">
      <div class="page-title">
        <h2>Dashboard</h2>
        <p>System overview and activity summary.</p>
      </div>
      <button class="btn btn-primary" onclick="navigateTo('mission')">⚡ Run Mission</button>
    </div>

    <div class="stats-grid">
      <div class="stat-tile primary">
        <div class="stat-value">${total_opps}</div>
        <div class="stat-label">Opportunities Found</div>
      </div>
      <div class="stat-tile green">
        <div class="stat-value">${summary.applications_submitted || total_apps}</div>
        <div class="stat-label">Applications Submitted</div>
      </div>
      <div class="stat-tile amber">
        <div class="stat-value">${awaiting}</div>
        <div class="stat-label">Awaiting Approval</div>
      </div>
      <div class="stat-tile ${interviews > 0 ? 'green' : ''}">
        <div class="stat-value">${interviews}</div>
        <div class="stat-label">Interview Invitations</div>
      </div>
      <div class="stat-tile">
        <div class="stat-value">${completeness}%</div>
        <div class="stat-label">Profile Completeness</div>
      </div>
    </div>

    <div class="grid-2 mb-lg">
      <!-- Last Mission -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">Last Mission</span>
          ${last.status ? `<span class="badge ${last.status === 'completed' ? 'badge-green' : 'badge-red'}">${esc(last.status)}</span>` : ''}
        </div>
        ${last.id ? `
          <div class="mono" style="color:var(--text-3);font-size:0.7rem;margin-bottom:0.75rem">${esc(last.id)}</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.75rem">
            ${dashStat('Jobs Found', summary.jobs_found || 0)}
            ${dashStat('Scholarships', summary.scholarships_found || 0)}
            ${dashStat('Submitted', summary.applications_submitted || 0)}
            ${dashStat('Errors', summary.errors || 0)}
            ${dashStat('Started', fmt(last.started_at))}
            ${dashStat('Emails', summary.emails_processed || 0)}
          </div>
        ` : '<p style="font-size:0.82rem">No missions yet. <a href="#" onclick="navigateTo(\'mission\')" style="color:var(--primary)">Run your first mission →</a></p>'}
      </div>

      <!-- Opportunity Breakdown -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">Opportunity Breakdown</span>
        </div>
        ${buildCategoryBreakdown(data.opportunity_categories || {})}
      </div>
    </div>

    <div class="grid-2">
      <!-- Application Status -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">Application Status</span>
          <a href="#" onclick="navigateTo('applications')" style="font-size:0.75rem;color:var(--primary)">View all →</a>
        </div>
        ${buildStatusBreakdown(data.application_statuses || {})}
      </div>

      <!-- Quick Actions -->
      <div class="card">
        <div class="card-header"><span class="card-title">Quick Actions</span></div>
        <div style="display:flex;flex-direction:column;gap:0.5rem">
          <button class="btn btn-secondary btn-full" onclick="navigateTo('mission')">⚡ Run /mission</button>
          <button class="btn btn-secondary btn-full" onclick="navigateTo('opportunities')">◎ Browse Opportunities</button>
          <button class="btn btn-secondary btn-full" onclick="navigateTo('applications')">◆ Review Applications</button>
          <button class="btn btn-secondary btn-full" onclick="navigateTo('email')">✉ Check Email</button>
          ${completeness < 80 ? `<button class="btn btn-ghost btn-full" onclick="navigateTo('profile')">◉ Complete Profile (${completeness}%)</button>` : ''}
        </div>
      </div>
    </div>
  `;
}

function dashStat(label, value) {
  return `<div>
    <div class="label">${esc(label)}</div>
    <div class="mono" style="color:var(--text)">${esc(String(value))}</div>
  </div>`;
}

function buildCategoryBreakdown(cats) {
  const entries = Object.entries(cats).sort((a,b) => b[1]-a[1]);
  if (!entries.length) return '<p style="font-size:0.82rem">No data yet.</p>';
  const total = entries.reduce((s,[,v]) => s+v, 0);
  return entries.map(([cat, count]) => {
    const pct = total ? Math.round((count/total)*100) : 0;
    return `<div style="margin-bottom:0.6rem">
      <div class="flex justify-between" style="margin-bottom:4px">
        <span style="font-size:0.78rem">${esc(cat)}</span>
        <span class="mono" style="font-size:0.75rem;color:var(--text-2)">${count}</span>
      </div>
      <div class="score-bar-track">
        <div class="score-bar-fill" style="width:${pct}%;background:var(--primary)"></div>
      </div>
    </div>`;
  }).join('');
}

function buildStatusBreakdown(statuses) {
  const entries = Object.entries(statuses);
  if (!entries.length) return '<p style="font-size:0.82rem">No applications yet.</p>';
  return `<div style="display:flex;flex-direction:column;gap:0.5rem">
    ${entries.map(([s, count]) => `
      <div class="flex items-center justify-between">
        ${statusBadge(s)}
        <span class="mono" style="font-size:0.82rem">${count}</span>
      </div>
    `).join('')}
  </div>`;
}

// ══════════════════════════════════════════════════════════════════
// PROFILE
// ══════════════════════════════════════════════════════════════════

export async function renderProfile(container) {
  const { profile, completeness } = await api.profile.get();
  const personal = profile.personal || {};
  const experience = profile.experience || [];
  const education = profile.education || [];
  const skills = profile.skills || [];
  const score = completeness.score || 0;
  const fields = completeness.fields || {};

  const r = 44;
  const circ = 2 * Math.PI * r;
  const offset = circ - (score / 100) * circ;

  container.innerHTML = `
    <div class="page-header">
      <div class="page-title">
        <h2>Profile</h2>
        <p>Your professional identity and career data.</p>
      </div>
      <button class="btn btn-secondary" onclick="document.getElementById('cv-upload-input').click()">
        ↑ Upload CV
      </button>
      <input type="file" id="cv-upload-input" accept=".pdf,.docx,.doc" style="display:none" />
    </div>

    <div class="profile-layout">
      <!-- Sidebar -->
      <div class="profile-sidebar-card">
        <div class="card">
          <div class="card-header"><span class="card-title">Completeness</span></div>
          <div class="progress-ring-wrap">
            <svg width="100" height="100" class="progress-ring">
              <circle class="progress-ring-bg" cx="50" cy="50" r="${r}" stroke-width="8"/>
              <circle class="progress-ring-fill" cx="50" cy="50" r="${r}" stroke-width="8"
                stroke-dasharray="${circ}" stroke-dashoffset="${offset}"/>
            </svg>
            <div>
              <div class="completeness-score">${score}%</div>
              <div class="completeness-label">Profile complete</div>
            </div>
          </div>
          <div class="divider"></div>
          <div class="field-checklist">
            ${Object.entries(fields).map(([f, done]) => `
              <div class="field-check">
                <span class="check-icon ${done ? 'check-done' : 'check-miss'}">${done ? '✓' : '✗'}</span>
                <span>${esc(f.replace(/_/g,' '))}</span>
              </div>
            `).join('')}
          </div>
        </div>

        <!-- CV Upload Zone -->
        <div class="card">
          <div class="card-header"><span class="card-title">Import CV</span></div>
          <div class="upload-zone" id="cv-drop-zone">
            <div class="upload-icon">📄</div>
            <div class="upload-text">Drop CV here or click to browse</div>
            <div class="upload-hint">PDF, DOCX — profile extracted automatically</div>
          </div>
          <div id="cv-upload-status" style="margin-top:0.5rem;font-size:0.78rem;display:none"></div>
        </div>
      </div>

      <!-- Main fields -->
      <div>
        <div class="card mb-lg">
          <div class="card-header">
            <span class="card-title">Personal Information</span>
          </div>
          <div class="profile-fields">
            ${profileField('Name',      'name',      personal.name)}
            ${profileField('Email',     'email',     personal.email)}
            ${profileField('Phone',     'phone',     personal.phone)}
            ${profileField('Location',  'location',  personal.location)}
            ${profileField('LinkedIn',  'linkedin',  personal.linkedin)}
            ${profileField('GitHub',    'github',    personal.github)}
            ${profileField('Portfolio', 'portfolio', personal.portfolio)}
            ${profileField('Salary Expectation', 'salary_expectation', personal.salary_expectation)}
          </div>
        </div>

        <!-- Skills -->
        <div class="card mb-lg">
          <div class="card-header">
            <span class="card-title">Skills</span>
            <button class="btn btn-ghost btn-sm" id="add-skill-btn">+ Add</button>
          </div>
          <div class="skills-grid" id="skills-grid">
            ${skills.map(s => `
              <div class="skill-chip">
                ${esc(s.name)}
                <span class="skill-level">${esc(s.level || '')}</span>
              </div>
            `).join('') || '<span style="color:var(--text-3);font-size:0.82rem">No skills added yet.</span>'}
          </div>
          <div id="add-skill-form" style="display:none;margin-top:1rem;gap:0.5rem;display:none">
            <div class="flex gap-sm" style="align-items:flex-end">
              <div class="form-group" style="flex:1;margin-bottom:0">
                <label>Skill name</label>
                <input type="text" id="skill-name-input" placeholder="e.g. Python" />
              </div>
              <div class="form-group" style="width:140px;margin-bottom:0">
                <label>Level</label>
                <select id="skill-level-input">
                  <option value="beginner">Beginner</option>
                  <option value="intermediate" selected>Intermediate</option>
                  <option value="advanced">Advanced</option>
                  <option value="expert">Expert</option>
                </select>
              </div>
              <button class="btn btn-primary" id="save-skill-btn">Add</button>
            </div>
          </div>
        </div>

        <!-- Experience -->
        <div class="card mb-lg">
          <div class="card-header"><span class="card-title">Experience</span></div>
          ${experience.length ? experience.map(exp => `
            <div style="padding:0.75rem 0;border-bottom:1px solid var(--border)">
              <div class="flex justify-between">
                <div>
                  <div style="font-weight:600;font-size:0.88rem">${esc(exp.title)}</div>
                  <div style="color:var(--text-2);font-size:0.8rem">${esc(exp.company)} ${exp.location ? '· ' + esc(exp.location) : ''}</div>
                </div>
                <div class="mono" style="font-size:0.72rem;color:var(--text-3);white-space:nowrap">
                  ${esc(exp.start_date||'')} – ${exp.current ? 'Present' : esc(exp.end_date||'')}
                </div>
              </div>
              ${exp.description ? `<div style="margin-top:0.4rem;font-size:0.8rem;color:var(--text-2)">${esc(exp.description)}</div>` : ''}
            </div>
          `).join('') : '<p style="font-size:0.82rem">No experience records. Import your CV to populate this.</p>'}
        </div>

        <!-- Education -->
        <div class="card">
          <div class="card-header"><span class="card-title">Education</span></div>
          ${education.length ? education.map(edu => `
            <div style="padding:0.75rem 0;border-bottom:1px solid var(--border)">
              <div class="flex justify-between">
                <div>
                  <div style="font-weight:600;font-size:0.88rem">${esc(edu.degree)} ${edu.field ? '· ' + esc(edu.field) : ''}</div>
                  <div style="color:var(--text-2);font-size:0.8rem">${esc(edu.institution)}</div>
                </div>
                <div class="mono" style="font-size:0.72rem;color:var(--text-3)">${esc(edu.end_date||edu.start_date||'')}</div>
              </div>
            </div>
          `).join('') : '<p style="font-size:0.82rem">No education records. Import your CV to populate this.</p>'}
        </div>
      </div>
    </div>
  `;

  // Profile field inline edit
  container.querySelectorAll('.edit-field-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const field = btn.dataset.field;
      const display = btn.closest('.profile-field-row').querySelector('.field-val');
      const current = display.dataset.raw || '';
      const val = prompt(`Update ${field}:`, current);
      if (val === null) return;
      try {
        await api.profile.update(field, val);
        display.textContent = val || '—';
        display.dataset.raw = val;
        toast(`${field} updated`, 'success');
      } catch (err) {
        toast(err.message, 'error');
      }
    });
  });

  // Add skill
  const addSkillBtn = container.querySelector('#add-skill-btn');
  const skillForm = container.querySelector('#add-skill-form');
  addSkillBtn?.addEventListener('click', () => {
    skillForm.style.display = skillForm.style.display === 'none' ? 'flex' : 'none';
  });

  container.querySelector('#save-skill-btn')?.addEventListener('click', async () => {
    const name = container.querySelector('#skill-name-input').value.trim();
    const level = container.querySelector('#skill-level-input').value;
    if (!name) return;
    try {
      await api.profile.addSkill(name, level);
      toast(`Skill added: ${name}`, 'success');
      renderProfile(container);
    } catch (err) {
      toast(err.message, 'error');
    }
  });

  // CV Upload handlers
  setupCVUpload(container);
}

function profileField(label, field, value) {
  return `<div class="profile-field-row">
    <div class="field-key">${esc(label)}</div>
    <div class="field-val ${value ? '' : 'field-empty'}" data-raw="${esc(value||'')}">${esc(value) || 'Not set'}</div>
    <button class="btn btn-ghost btn-sm edit-field-btn" data-field="${esc(field)}">Edit</button>
  </div>`;
}

function setupCVUpload(container) {
  const input = document.getElementById('cv-upload-input');
  const dropZone = container.querySelector('#cv-drop-zone');
  const statusEl = container.querySelector('#cv-upload-status');

  async function handleFile(file) {
    statusEl.style.display = 'block';
    statusEl.style.color = 'var(--text-2)';
    statusEl.textContent = `Importing ${file.name}...`;
    try {
      await api.profile.uploadCV(file);
      statusEl.style.color = 'var(--green)';
      statusEl.textContent = '✓ CV imported. Refreshing profile...';
      toast('CV imported successfully', 'success');
      setTimeout(() => renderProfile(container), 1500);
    } catch (err) {
      statusEl.style.color = 'var(--red)';
      statusEl.textContent = `✗ ${err.message}`;
      toast(err.message, 'error');
    }
  }

  input?.addEventListener('change', (e) => { if (e.target.files[0]) handleFile(e.target.files[0]); });
  dropZone?.addEventListener('click', () => input?.click());
  dropZone?.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('drag-over'); });
  dropZone?.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
  dropZone?.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
  });
}

// ══════════════════════════════════════════════════════════════════
// OPPORTUNITIES
// ══════════════════════════════════════════════════════════════════

export async function renderOpportunities(container) {
  const { opportunities } = await api.opportunities.list(50);

  const categories = ['all', ...new Set(opportunities.map(o => o.category).filter(Boolean))];

  container.innerHTML = `
    <div class="page-header">
      <div class="page-title">
        <h2>Opportunities</h2>
        <p>${opportunities.length} opportunities found across all categories.</p>
      </div>
      <button class="btn btn-primary" onclick="navigateTo('mission')">⚡ Search More</button>
    </div>

    <div class="opp-filters" id="opp-filters">
      ${categories.map(c => `
        <div class="filter-chip ${c === 'all' ? 'active' : ''}" data-cat="${esc(c)}">${esc(c)}</div>
      `).join('')}
    </div>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Opportunity</th>
            <th>Organization</th>
            <th>Category</th>
            <th>Match</th>
            <th>Eligibility</th>
            <th>Deadline</th>
            <th>Remote</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody id="opp-tbody">
          ${renderOppRows(opportunities)}
        </tbody>
      </table>
    </div>
  `;

  // Category filter
  container.querySelectorAll('.filter-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      container.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      const cat = chip.dataset.cat;
      const filtered = cat === 'all' ? opportunities : opportunities.filter(o => o.category === cat);
      container.querySelector('#opp-tbody').innerHTML = renderOppRows(filtered);
    });
  });
}

function renderOppRows(opps) {
  if (!opps.length) return `<tr><td colspan="8">
    <div class="empty-state">
      <div class="empty-icon">◎</div>
      <div class="empty-title">No opportunities</div>
      <div class="empty-desc">Run a mission to discover opportunities.</div>
    </div>
  </td></tr>`;

  return opps.map(o => {
    const score = o.score || 0;
    const eligIcon = o.eligible === 'eligible' ? '✓' : o.eligible === 'not_eligible' ? '✗' : '~';
    const eligColor = o.eligible === 'eligible' ? 'var(--green)' : o.eligible === 'not_eligible' ? 'var(--red)' : 'var(--amber)';
    const days = o.days_until_deadline;
    let deadlineCell = esc(o.deadline || '—');
    if (days !== null && days !== undefined) {
      if (days < 0) deadlineCell += ' <span style="color:var(--red);font-size:0.7rem">(expired)</span>';
      else if (days <= 3) deadlineCell += ` <span style="color:var(--red);font-size:0.7rem">${days}d</span>`;
      else if (days <= 7) deadlineCell += ` <span style="color:var(--amber);font-size:0.7rem">${days}d</span>`;
    }
    return `<tr>
      <td>
        <div style="font-weight:600;font-size:0.85rem">${esc(o.title || '—')}</div>
        ${o.application_url ? `<a href="${esc(o.application_url)}" target="_blank" style="font-size:0.72rem;color:var(--primary)">↗ Apply</a>` : ''}
      </td>
      <td class="td-dim">${esc(o.organization || '—')}</td>
      <td>${categoryBadge(o.category)}</td>
      <td>
        <div class="score-bar">
          <span style="color:${scoreColor(score)};font-weight:700">${score}</span>
          <div class="score-bar-track" style="width:60px">
            <div class="score-bar-fill" style="width:${score}%;background:${scoreColor(score)}"></div>
          </div>
        </div>
      </td>
      <td style="color:${eligColor};font-size:1rem;text-align:center">${eligIcon}</td>
      <td class="td-dim" style="font-size:0.78rem">${deadlineCell}</td>
      <td style="text-align:center">${o.remote ? '<span style="color:var(--green)">✓</span>' : '<span style="color:var(--text-3)">—</span>'}</td>
      <td>
        ${o.application_url ? `<a href="${esc(o.application_url)}" target="_blank" class="btn btn-ghost btn-sm">Apply →</a>` : '<span style="color:var(--text-3);font-size:0.75rem">No URL</span>'}
      </td>
    </tr>`;
  }).join('');
}

// ══════════════════════════════════════════════════════════════════
// APPLICATIONS
// ══════════════════════════════════════════════════════════════════

export async function renderApplications(container) {
  const { applications } = await api.applications.list(null, 100);
  const awaiting = applications.filter(a => a.status === 'awaiting_approval');

  container.innerHTML = `
    <div class="page-header">
      <div class="page-title">
        <h2>Applications</h2>
        <p>${applications.length} total · ${awaiting.length} awaiting approval.</p>
      </div>
    </div>

    ${awaiting.length ? `
    <div class="card mb-lg" style="border-color:var(--amber-dim)">
      <div class="card-header">
        <span class="card-title" style="color:var(--amber)">⏳ Awaiting Your Approval (${awaiting.length})</span>
      </div>
      <div style="display:flex;flex-direction:column;gap:0.75rem">
        ${awaiting.map(a => `
          <div style="display:flex;align-items:center;justify-content:space-between;padding:0.65rem 0;border-bottom:1px solid var(--border)">
            <div>
              <div style="font-weight:600;font-size:0.85rem">${esc(a.opportunity_title)}</div>
              <div style="font-size:0.75rem;color:var(--text-2)">${esc(a.organization)} · ${esc(a.category)}</div>
            </div>
            <div class="flex gap-sm">
              <button class="btn btn-green btn-sm" onclick="approveApp('${esc(a.id)}', this)">Approve</button>
              <button class="btn btn-ghost btn-sm" onclick="skipApp('${esc(a.id)}', this)">Skip</button>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
    ` : ''}

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Opportunity</th>
            <th>Organization</th>
            <th>Category</th>
            <th>Status</th>
            <th>Platform</th>
            <th>Submitted</th>
          </tr>
        </thead>
        <tbody>
          ${applications.length ? applications.map(a => `
            <tr>
              <td>
                <div style="font-weight:600;font-size:0.85rem">${esc(a.opportunity_title || '—')}</div>
                ${a.application_url ? `<a href="${esc(a.application_url)}" target="_blank" style="font-size:0.72rem;color:var(--primary)">↗ Link</a>` : ''}
              </td>
              <td class="td-dim">${esc(a.organization || '—')}</td>
              <td>${categoryBadge(a.category)}</td>
              <td>${statusBadge(a.status)}</td>
              <td class="td-mono">${esc(a.account_platform || '—')}</td>
              <td class="td-dim" style="font-size:0.78rem">${fmt(a.submitted_at || a.created_at)}</td>
            </tr>
          `).join('') : `<tr><td colspan="6">
            <div class="empty-state">
              <div class="empty-icon">◆</div>
              <div class="empty-title">No applications yet</div>
              <div class="empty-desc">Run a mission to start applying.</div>
            </div>
          </td></tr>`}
        </tbody>
      </table>
    </div>
  `;

  // Expose approve/skip globally for onclick handlers
  window.approveApp = async (id, btn) => {
    btn.disabled = true;
    btn.textContent = '...';
    try {
      await api.applications.action(id, 'approve');
      toast('Application approved and submitted', 'success');
      renderApplications(container);
    } catch (err) {
      toast(err.message, 'error');
      btn.disabled = false;
      btn.textContent = 'Approve';
    }
  };

  window.skipApp = async (id, btn) => {
    btn.disabled = true;
    try {
      await api.applications.action(id, 'skip');
      toast('Application skipped', 'info');
      renderApplications(container);
    } catch (err) {
      toast(err.message, 'error');
      btn.disabled = false;
    }
  };
}

// ══════════════════════════════════════════════════════════════════
// DOCUMENTS
// ══════════════════════════════════════════════════════════════════

export async function renderDocuments(container) {
  const { documents } = await api.documents.list();

  const typeIcon = { resume:'📄', cover_letter:'✉', sop:'📝', personal_statement:'📋', motivation_letter:'💌', biography:'👤' };
  const typeLabel = { resume:'Resume', cover_letter:'Cover Letter', sop:'Statement of Purpose', personal_statement:'Personal Statement', motivation_letter:'Motivation Letter', biography:'Biography' };

  container.innerHTML = `
    <div class="page-header">
      <div class="page-title">
        <h2>Documents</h2>
        <p>${documents.length} generated documents.</p>
      </div>
    </div>

    ${documents.length ? `
    <div class="doc-grid">
      ${documents.map(d => `
        <div class="doc-card">
          <div class="doc-icon">${typeIcon[d.type] || '📄'}</div>
          <div>
            <div class="doc-type">${esc(typeLabel[d.type] || d.type)}</div>
            <div class="doc-title">${esc(d.opportunity_title || 'General')}</div>
            <div class="doc-date">${fmt(d.created_at)}</div>
          </div>
          <a href="${api.documents.download(d.id)}" class="btn btn-secondary btn-sm btn-full" target="_blank">
            ↓ Download PDF
          </a>
        </div>
      `).join('')}
    </div>
    ` : `
    <div class="empty-state" style="padding:4rem">
      <div class="empty-icon">▤</div>
      <div class="empty-title">No documents yet</div>
      <div class="empty-desc">Documents are generated automatically during missions.</div>
      <button class="btn btn-primary mt-md" onclick="navigateTo('mission')">Run Mission</button>
    </div>
    `}
  `;
}

// ══════════════════════════════════════════════════════════════════
// EMAIL
// ══════════════════════════════════════════════════════════════════

export async function renderEmail(container) {
  const { emails } = await api.email.list(null, 100);

  const catIcon = {
    interview:'🎤', offer:'🏆', coding_test:'📝',
    verification:'📧', rejection:'❌', reminder:'🔔', general:'📩'
  };

  container.innerHTML = `
    <div class="page-header">
      <div class="page-title">
        <h2>Email</h2>
        <p>${emails.length} emails processed.</p>
      </div>
      <button class="btn btn-primary" id="check-email-btn">↻ Check Now</button>
    </div>

    ${emails.length ? `
    <div class="email-list">
      ${emails.map(e => `
        <div class="email-item ${e.priority === 'high' ? 'unread' : ''}">
          <div class="email-cat-icon">${catIcon[e.category] || '📩'}</div>
          <div>
            <div class="email-from">${esc(e.sender_organization || e.sender || '—')}</div>
            <div class="email-subject">${esc(e.subject || '—')}</div>
          </div>
          <span class="badge ${e.priority === 'high' ? 'badge-red' : e.priority === 'medium' ? 'badge-amber' : 'badge-gray'}">
            ${esc(e.category?.replace('_',' ') || '—')}
          </span>
          <div class="email-date">${fmt(e.received_at)}</div>
        </div>
      `).join('')}
    </div>
    ` : `
    <div class="empty-state">
      <div class="empty-icon">✉</div>
      <div class="empty-title">No emails yet</div>
      <div class="empty-desc">Click "Check Now" to scan your career inbox.</div>
    </div>
    `}
  `;

  container.querySelector('#check-email-btn')?.addEventListener('click', async (e) => {
    const btn = e.target;
    btn.disabled = true;
    btn.textContent = 'Checking...';
    try {
      const result = await api.email.check();
      toast(`${result.emails.length} emails processed`, 'success');
      renderEmail(container);
    } catch (err) {
      toast(err.message, 'error');
      btn.disabled = false;
      btn.textContent = '↻ Check Now';
    }
  });
}

// ══════════════════════════════════════════════════════════════════
// SETTINGS
// ══════════════════════════════════════════════════════════════════

export async function renderSettings(container) {
  const s = await api.settings.get();

  container.innerHTML = `
    <div class="page-header">
      <div class="page-title">
        <h2>Settings</h2>
        <p>System configuration. Changes require environment variable updates on Render.</p>
      </div>
    </div>

    <div class="settings-group">
      <div class="settings-group-header">Application Policy</div>
      <div class="settings-row">
        <div>
          <div class="settings-label">Application Mode</div>
          <div class="settings-desc">Current mode: <strong style="color:var(--primary)">${esc(s.application_mode)}</strong></div>
        </div>
        <div style="display:flex;gap:0.5rem">
          ${modeBtn('manual', s.application_mode)}
          ${modeBtn('smart', s.application_mode)}
          ${modeBtn('automatic', s.application_mode)}
        </div>
      </div>
      <div class="settings-row">
        <div>
          <div class="settings-label">Smart Apply</div>
          <div class="settings-desc">Auto-submit low-risk applications without approval</div>
        </div>
        <label class="toggle">
          <input type="checkbox" ${s.smart_apply ? 'checked' : ''} disabled />
          <div class="toggle-track"></div>
        </label>
      </div>
      <div class="settings-row">
        <div>
          <div class="settings-label">Auto Apply</div>
          <div class="settings-desc">Submit all eligible applications automatically</div>
        </div>
        <label class="toggle">
          <input type="checkbox" ${s.auto_apply ? 'checked' : ''} disabled />
          <div class="toggle-track"></div>
        </label>
      </div>
    </div>

    <div class="settings-group">
      <div class="settings-group-header">Configuration</div>
      <div class="settings-row">
        <div>
          <div class="settings-label">Career Email</div>
          <div class="settings-desc">Gmail account monitored for career correspondence</div>
        </div>
        <span class="mono" style="color:var(--text-2)">${esc(s.email_address || 'Not set')}</span>
      </div>
      <div class="settings-row">
        <div>
          <div class="settings-label">LLM Model</div>
          <div class="settings-desc">Primary model via OpenRouter</div>
        </div>
        <span class="mono badge badge-primary">${esc(s.llm_model)}</span>
      </div>
      <div class="settings-row">
        <div>
          <div class="settings-label">Document Provider</div>
          <div class="settings-desc">Backend used for document generation</div>
        </div>
        <span class="mono badge badge-gray">${esc(s.document_provider)}</span>
      </div>
      <div class="settings-row">
        <div>
          <div class="settings-label">Timezone</div>
          <div class="settings-desc">Used for scheduling and timestamps</div>
        </div>
        <span class="mono" style="color:var(--text-2)">${esc(s.timezone)}</span>
      </div>
    </div>

    <div class="settings-group">
      <div class="settings-group-header">To Change Settings</div>
      <div class="settings-row">
        <div>
          <div class="settings-label">Environment Variables</div>
          <div class="settings-desc">All settings are controlled via Render environment variables. Go to your Render dashboard → Environment to update them. Changes take effect on next deploy.</div>
        </div>
        <a href="https://dashboard.render.com" target="_blank" class="btn btn-secondary btn-sm">Open Render →</a>
      </div>
    </div>

    <div class="settings-group">
      <div class="settings-group-header">Session</div>
      <div class="settings-row">
        <div>
          <div class="settings-label">Sign Out</div>
          <div class="settings-desc">Revoke current session token</div>
        </div>
        <button class="btn btn-red btn-sm" onclick="document.getElementById('logout-btn').click()">Sign out</button>
      </div>
    </div>
  `;
}

function modeBtn(mode, current) {
  const active = mode === current;
  return `<button class="btn ${active ? 'btn-primary' : 'btn-ghost'} btn-sm" disabled>${esc(mode)}</button>`;
}
