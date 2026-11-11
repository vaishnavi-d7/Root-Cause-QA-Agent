/**
 * Runs View (#/): List of all QA runs with hero and latest scorecard.
 */
import { fetchRuns, fetchRun, deleteRun } from '../api.js';
import { renderStatusPill } from '../components/pill.js';
import { icon } from '../components/icons.js';
import { escapeHtml, formatTime } from '../util.js';

export async function renderRunsView(container) {
  container.innerHTML = `
    <div class="skeleton" style="height: 140px; margin-bottom: 2rem;"></div>
    <div class="skeleton" style="height: 200px;"></div>
  `;

  try {
    const runs = await fetchRuns();

    let scorecardHtml = '';
    if (runs && runs.length > 0) {
      try {
        const latestDetails = await fetchRun(runs[0].id);
        const bench = latestDetails.benchmark || {};
        const baselineCorrect = bench.modes?.baseline?.correct ?? '—';
        const llmMode = bench.modes?.llm;
        let llmDisplay = '—';
        if (llmMode) {
          if (llmMode.status === 'invalid') {
            llmDisplay = 'Invalid';
          } else if (llmMode.correct !== undefined) {
            llmDisplay = `${llmMode.correct}/5`;
          }
        }

        scorecardHtml = `
          <div class="runs-section-header">
            <span class="section-label">Latest Run Scorecard (${escapeHtml(runs[0].id)})</span>
            <a href="#/run/${encodeURIComponent(runs[0].id)}" class="btn btn-secondary btn-sm">
              View Run Details ${icon('arrow-right')}
            </a>
          </div>
          <div class="scorecard-grid">
            <div class="stat-box">
              <span class="stat-number">${bench.detected ?? runs[0].counts?.findings ?? 0}</span>
              <span class="stat-label">Bugs Detected</span>
              <span class="stat-subtext">out of 5 seeded</span>
            </div>
            <div class="stat-box">
              <span class="stat-number">${bench.reproduced ?? runs[0].counts?.reproduced ?? 0}</span>
              <span class="stat-label">Reproduced on Video</span>
              <span class="stat-subtext">confirmed browser failure</span>
            </div>
            <div class="stat-box">
              <span class="stat-number">${baselineCorrect !== '—' ? `${baselineCorrect}/5` : '—'}</span>
              <span class="stat-label">Git Blame Accuracy</span>
              <span class="stat-subtext">trapped on style commit</span>
            </div>
            <div class="stat-box">
              <span class="stat-number">${llmDisplay}</span>
              <span class="stat-label">LLM Root-Cause</span>
              <span class="stat-subtext">semantic culprit search</span>
            </div>
          </div>
        `;
      } catch (err) {
        console.warn('Failed to load latest run details for scorecard:', err);
      }
    }

    let runsTableHtml = '';
    if (!runs || runs.length === 0) {
      runsTableHtml = `
        <div class="empty-state">
          <div class="empty-state-icon" aria-hidden="true">${icon('bug')}</div>
          <h2 class="empty-state-title">No runs yet</h2>
          <p class="empty-state-text">Start a run to explore the Mini Shop test app, record reproducible failures on video, and identify culprit commits.</p>
          <a href="#/new" class="btn btn-primary">${icon('play')} Start a run</a>
        </div>
      `;
    } else {
      runsTableHtml = `
        <div class="runs-section-header">
          <h2 class="section-label">Run History</h2>
          <span class="text-muted" style="font-size: 0.8125rem;">${runs.length} total run${runs.length === 1 ? '' : 's'}</span>
        </div>
        <div class="table-container">
          <table class="data-table" aria-label="Run History">
            <thead>
              <tr>
                <th scope="col">Run ID</th>
                <th scope="col">Status</th>
                <th scope="col">Created</th>
                <th scope="col">Mode</th>
                <th scope="col">LLM Provider</th>
                <th scope="col">Findings</th>
                <th scope="col">Reproduced</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              ${runs.map((r) => {
                return `
                  <tr>
                    <td>
                      <a href="#/run/${encodeURIComponent(r.id)}" style="font-family: var(--font-code); font-weight: 600;">
                        ${escapeHtml(r.id)}
                      </a>
                    </td>
                    <td>${renderStatusPill(r.status)}</td>
                    <td>${escapeHtml(formatTime(r.created_at))}</td>
                    <td><span class="badge">${escapeHtml(r.rca || 'baseline')}</span></td>
                    <td class="text-muted" style="font-size: 0.8125rem;">${escapeHtml(r.llm_description || 'None')}</td>
                    <td><strong>${r.counts?.findings ?? 0}</strong></td>
                    <td>${r.counts?.reproduced ?? 0}</td>
                    <td>
                      <div style="display: flex; gap: 0.5rem; align-items: center;">
                        <a href="#/run/${encodeURIComponent(r.id)}" class="btn btn-secondary btn-sm" title="View run details">
                          View
                        </a>
                        <button class="btn btn-secondary btn-sm btn-delete-run" data-run-id="${escapeHtml(r.id)}" title="Delete run">
                          ${icon('trash')}
                        </button>
                      </div>
                    </td>
                  </tr>
                `;
              }).join('')}
            </tbody>
          </table>
        </div>
      `;
    }

    container.innerHTML = `
      <section class="hero-section" aria-labelledby="hero-title">
        <div class="hero-content">
          <h1 id="hero-title" class="hero-title">Find the bug. Prove it. Name the commit.</h1>
          <p class="hero-subtitle">
            An autonomous QA agent that explores a web application in a real browser, reproduces bugs on video, and traces each failure to the git commit that introduced it.
          </p>
        </div>
        <a href="#/new" class="btn btn-primary">${icon('play')} Start a run</a>
      </section>

      ${scorecardHtml}
      ${runsTableHtml}
    `;

    // Wire up delete buttons
    container.querySelectorAll('.btn-delete-run').forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        const runId = btn.getAttribute('data-run-id');
        if (!confirm(`Are you sure you want to delete run ${runId}? This cannot be undone.`)) {
          return;
        }
        try {
          btn.disabled = true;
          await deleteRun(runId);
          renderRunsView(container);
        } catch (err) {
          alert(`Failed to delete run: ${err.message}`);
          btn.disabled = false;
        }
      });
    });

  } catch (err) {
    container.innerHTML = `
      <div class="error-panel" role="alert">
        <div class="error-panel-content">
          <div class="error-panel-icon">${icon('alert-circle')}</div>
          <div>
            <strong>Error loading runs</strong>
            <p style="margin-top: 0.25rem;">${escapeHtml(err.message)}</p>
          </div>
        </div>
        <button id="btn-retry-runs" class="btn btn-secondary btn-sm">Retry</button>
      </div>
    `;
    document.getElementById('btn-retry-runs')?.addEventListener('click', () => {
      renderRunsView(container);
    });
  }
}
