/**
 * Main application router and shell.
 */
import { renderRunsView } from './views/runs.js';
import { renderNewRunView } from './views/new_run.js';
import { renderRunView } from './views/run.js';
import { renderFindingView } from './views/finding.js';
import { renderAboutView } from './views/about.js';

function updateNavActive(path) {
  const navLinks = document.querySelectorAll('.nav-link');
  navLinks.forEach(link => {
    const href = link.getAttribute('href');
    let isActive = false;
    if (href === '#/' && (path === '' || path === '/' || path.startsWith('/run/'))) {
      isActive = true;
    } else if (href === '#/new' && path === '/new') {
      isActive = true;
    } else if (href === '#/about' && path === '/about') {
      isActive = true;
    }
    link.classList.toggle('active', isActive);
    link.setAttribute('aria-current', isActive ? 'page' : 'false');
  });
}

async function handleRoute() {
  const hash = window.location.hash.slice(1) || '/';
  const appContainer = document.getElementById('app');
  if (!appContainer) return;

  // Normalize path without trailing slashes (except root)
  let path = hash.split('?')[0];
  if (path.length > 1 && path.endsWith('/')) {
    path = path.slice(0, -1);
  }

  if (window._activeRunStream) {
    try { window._activeRunStream.close(); } catch (_) {}
    window._activeRunStream = null;
  }

  try {
    // Route 1: #/ (Runs)
    if (path === '' || path === '/') {
      await renderRunsView(appContainer);
      return;
    }

    // Route 2: #/new (New Run)
    if (path === '/new') {
      await renderNewRunView(appContainer);
      return;
    }

    // Route 5: #/about (How it works)
    if (path === '/about') {
      renderAboutView(appContainer);
      return;
    }

    // Route 4: #/run/:id/finding/:fid
    const findingMatch = path.match(/^\/run\/([^\/]+)\/finding\/([^\/]+)$/);
    if (findingMatch) {
      const runId = decodeURIComponent(findingMatch[1]);
      const fid = decodeURIComponent(findingMatch[2]);
      await renderFindingView(appContainer, runId, fid);
      return;
    }

    // Route 3: #/run/:id
    const runMatch = path.match(/^\/run\/([^\/]+)$/);
    if (runMatch) {
      const runId = decodeURIComponent(runMatch[1]);
      await renderRunView(appContainer, runId);
      return;
    }

    // 404 Route
    appContainer.innerHTML = `
      <div class="empty-state">
        <h1 class="page-title">Page Not Found</h1>
        <p class="empty-state-text">The requested route <code>#${path}</code> does not exist.</p>
        <a href="#/" class="btn btn-primary">Return to Runs</a>
      </div>
    `;
  } catch (err) {
    console.error('Routing error:', err);
    appContainer.innerHTML = `
      <div class="error-panel" role="alert">
        <div class="error-panel-content">
          <div>
            <strong>Application error</strong>
            <p style="margin-top: 0.25rem;">${err.message || 'An unexpected error occurred while rendering the page.'}</p>
          </div>
        </div>
        <a href="#/" class="btn btn-secondary btn-sm">Return Home</a>
      </div>
    `;
  }
}

window.addEventListener('hashchange', handleRoute);
window.addEventListener('DOMContentLoaded', handleRoute);
