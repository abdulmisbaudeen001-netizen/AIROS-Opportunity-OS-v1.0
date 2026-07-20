/**
 * AIROS Opportunity OS — API Client
 * All communication with the Render backend goes through this module.
 * Base URL is the current origin (same Render service).
 */

const BASE = '';  // Same origin — no hardcoded URL needed

function token() {
  return localStorage.getItem('airos_token') || '';
}

function headers(extra = {}) {
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token()}`,
    ...extra,
  };
}

async function request(method, path, body = null, opts = {}) {
  const config = {
    method,
    headers: headers(opts.headers || {}),
  };
  if (body) config.body = JSON.stringify(body);

  const res = await fetch(BASE + path, config);

  if (res.status === 401) {
    localStorage.removeItem('airos_token');
    window.location.href = '/';
    return null;
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

async function upload(path, formData) {
  const res = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token()}` },
    body: formData,
  });
  if (res.status === 401) {
    localStorage.removeItem('airos_token');
    window.location.href = '/';
    return null;
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Auth ──────────────────────────────────────────────────────────────────

const api = {
  auth: {
    logout: () => request('POST', '/api/logout'),
  },

  // ── Dashboard ─────────────────────────────────────────────────────────

  dashboard: {
    get: () => request('GET', '/api/dashboard'),
  },

  // ── Mission ───────────────────────────────────────────────────────────

  mission: {
    run:    (command) => request('POST', '/api/mission/run', { command }),
    recent: ()        => request('GET', '/api/mission/recent'),
    stream: ()        => new EventSource(`/api/mission/stream?token=${token()}`),
  },

  // ── Profile ───────────────────────────────────────────────────────────

  profile: {
    get:          ()           => request('GET', '/api/profile'),
    update:       (field, value) => request('PATCH', '/api/profile', { field, value }),
    uploadCV:     (file)       => {
      const fd = new FormData();
      fd.append('file', file);
      return upload('/api/profile/cv', fd);
    },
    addSkill:     (name, level) => request('POST', '/api/profile/skills', { name, level }),
    addKnowledge: (category, content) => request('POST', '/api/profile/knowledge', { category, content }),
    questions:    ()           => request('GET', '/api/profile/questions'),
  },

  // ── Opportunities ─────────────────────────────────────────────────────

  opportunities: {
    list:   (limit = 50, category = null) => {
      const q = new URLSearchParams({ limit });
      if (category) q.set('category', category);
      return request('GET', `/api/opportunities?${q}`);
    },
    get:    (id) => request('GET', `/api/opportunities/${id}`),
  },

  // ── Applications ──────────────────────────────────────────────────────

  applications: {
    list:   (status = null, limit = 50) => {
      const q = new URLSearchParams({ limit });
      if (status) q.set('status', status);
      return request('GET', `/api/applications?${q}`);
    },
    action: (application_id, action) =>
      request('POST', '/api/applications/action', { application_id, action }),
  },

  // ── Documents ─────────────────────────────────────────────────────────

  documents: {
    list:     (docType = null) => {
      const q = docType ? `?doc_type=${docType}` : '';
      return request('GET', `/api/documents${q}`);
    },
    download: (id) => `${BASE}/api/documents/${id}/download?token=${token()}`,
  },

  // ── Email ─────────────────────────────────────────────────────────────

  email: {
    list:  (category = null, limit = 50) => {
      const q = new URLSearchParams({ limit });
      if (category) q.set('category', category);
      return request('GET', `/api/email?${q}`);
    },
    check: () => request('POST', '/api/email/check'),
  },

  // ── Settings ──────────────────────────────────────────────────────────

  settings: {
    get: () => request('GET', '/api/settings'),
  },

  // ── Health ────────────────────────────────────────────────────────────

  health: {
    get: () => request('GET', '/api/health'),
  },
};

export default api;
