/**
 * AIROS Opportunity OS — App Shell
 * Handles auth guard, sidebar navigation, page switching, toasts.
 */

import api from './api.js';
import { renderDashboard }    from './pages.js';
import { renderMission }      from './mission.js';
import { renderProfile }      from './pages.js';
import { renderOpportunities} from './pages.js';
import { renderApplications } from './pages.js';
import { renderDocuments }    from './pages.js';
import { renderEmail }        from './pages.js';
import { renderSettings }     from './pages.js';

// ── Auth guard ────────────────────────────────────────────────────────────

if (!localStorage.getItem('airos_token')) {
  window.location.href = '/';
}

// ── Page registry ─────────────────────────────────────────────────────────

const PAGES = {
  dashboard:     { label: 'Dashboard',       icon: '◈',  render: renderDashboard },
  mission:       { label: 'Mission Control', icon: '⚡', render: renderMission },
  profile:       { label: 'Profile',         icon: '◉',  render: renderProfile },
  opportunities: { label: 'Opportunities',   icon: '◎',  render: renderOpportunities },
  applications:  { label: 'Applications',    icon: '◆',  render: renderApplications },
  documents:     { label: 'Documents',       icon: '▤',  render: renderDocuments },
  email:         { label: 'Email',           icon: '✉',  render: renderEmail },
  settings:      { label: 'Settings',        icon: '⚙',  render: renderSettings },
};

let _currentPage = null;

// ── Build sidebar nav ─────────────────────────────────────────────────────

function buildNav() {
  const nav = document.getElementById('sidebar-nav');
  nav.innerHTML = '';

  const section = document.createElement('div');
  section.className = 'nav-section';

  const sectionLabel = document.createElement('div');
  sectionLabel.className = 'nav-section-label';
  sectionLabel.textContent = 'Navigation';
  section.appendChild(sectionLabel);

  for (const [key, page] of Object.entries(PAGES)) {
    const item = document.createElement('div');
    item.className = 'nav-item';
    item.dataset.page = key;
    item.innerHTML = `
      <span class="nav-icon">${page.icon}</span>
      <span>${page.label}</span>
    `;
    item.addEventListener('click', () => navigate(key));
    section.appendChild(item);
  }

  nav.appendChild(section);
}

// ── Navigation ────────────────────────────────────────────────────────────

export function navigate(pageKey) {
  if (pageKey === _currentPage) return;
  _currentPage = pageKey;

  // Update nav active state
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.page === pageKey);
  });

  // Show correct page container
  document.querySelectorAll('.page').forEach(el => {
    el.classList.toggle('active', el.id === `page-${pageKey}`);
  });

  // Update URL hash without reload
  history.replaceState(null, '', `#${pageKey}`);

  // Render the page content
  const page = PAGES[pageKey];
  if (page?.render) {
    const container = document.getElementById(`page-${pageKey}`);
    if (container) {
      container.innerHTML = '<div class="empty-state"><div class="spinner"></div></div>';
      page.render(container).catch(err => {
        container.innerHTML = `<div class="empty-state">
          <div class="empty-icon">⚠</div>
          <div class="empty-title">Failed to load</div>
          <div class="empty-desc">${err.message}</div>
        </div>`;
      });
    }
  }
}

// ── Toast system ──────────────────────────────────────────────────────────

export function toast(message, type = 'info', duration = 4000) {
  const container = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => el.remove(), duration);
}

// ── Logout ────────────────────────────────────────────────────────────────

async function logout() {
  try { await api.auth.logout(); } catch (_) {}
  localStorage.removeItem('airos_token');
  window.location.href = '/';
}

// ── System status check ───────────────────────────────────────────────────

async function checkHealth() {
  try {
    await api.health.get();
    document.getElementById('status-dot').style.background = 'var(--green)';
    document.getElementById('status-text').textContent = 'Online';
  } catch {
    document.getElementById('status-dot').style.background = 'var(--red)';
    document.getElementById('status-text').textContent = 'Offline';
  }
}

// ── Badge updater ─────────────────────────────────────────────────────────

async function updateBadges() {
  try {
    const data = await api.dashboard.get();
    const awaiting = data.awaiting_approval || 0;
    const interviews = data.interviews || 0;

    // Applications badge
    const appBadge = document.querySelector('[data-page="applications"] .nav-badge');
    if (appBadge) {
      appBadge.textContent = awaiting;
      appBadge.style.display = awaiting > 0 ? 'inline-flex' : 'none';
    }

    // Email badge
    const emailBadge = document.querySelector('[data-page="email"] .nav-badge');
    if (emailBadge) {
      emailBadge.textContent = interviews;
      emailBadge.style.display = interviews > 0 ? 'inline-flex' : 'none';
    }
  } catch (_) {}
}

// ── Init ──────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  buildNav();

  // Add badges to nav items that need them
  const appItem = document.querySelector('[data-page="applications"]');
  if (appItem) {
    const badge = document.createElement('span');
    badge.className = 'nav-badge amber';
    badge.style.display = 'none';
    appItem.appendChild(badge);
  }

  const emailItem = document.querySelector('[data-page="email"]');
  if (emailItem) {
    const badge = document.createElement('span');
    badge.className = 'nav-badge red';
    badge.style.display = 'none';
    emailItem.appendChild(badge);
  }

  // Logout button
  document.getElementById('logout-btn')?.addEventListener('click', logout);

  // Determine initial page from hash or default
  const hash = window.location.hash.replace('#', '') || 'dashboard';
  const startPage = PAGES[hash] ? hash : 'dashboard';
  navigate(startPage);

  // Health check + badge updates
  checkHealth();
  updateBadges();
  setInterval(checkHealth, 30000);
  setInterval(updateBadges, 60000);
});

// Expose navigate globally for inline onclick usage
window.navigateTo = navigate;
window.showToast = toast;
