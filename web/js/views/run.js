/**
 * Run Detail View (#/run/:id): Stage stepper, event stream, scorecard, findings, benchmark, and report.
 */
import { fetchRun, streamRunEvents } from '../api.js';
import { renderStatusPill, renderKindPill, renderReproducedPill } from '../components/pill.js';
import { renderStepper, STAGES } from '../components/stepper.js';
import { icon } from '../components/icons.js';
import { escapeHtml, formatTime, shortSha, renderMarkdown, downloadFile } from '../util.js';

export async function renderRunView(container, runId) {
  container.innerHTML = `
    <div class="skeleton" style="height: 80px; margin-bottom: 1.5rem;"></div>
    <div class="skeleton" style="height: 120px; margin-bottom: 1.5rem;"></div>
    <div class="skeleton" style="height: 300px;"></div>
  `;

  let eventStream = null;
  const stageStates = {};
  STAGES.forEach(s => { stageStates[s.id] = 'pending'; });

  let probeCount = 0;
  let findingCount = 0;
  let activeTab = 'findings';

  async function loadAndRender() {
    try {
      const run = await fetchRun(runId);
      const meta = run.meta || {};
      const status = meta.status || 'running';
      const findings = run.findings || [];
      const rca = run.rca || {};
      const bench = run.benchmark || {};
      findingCount = findings.length;

      // Update stage states if run is done
      if (status === 'done') {
        STAGES.forEach(s => { stageStates[s.id] = 'done'; });
      }

      // Compute scorecard values
      const baselineMode = bench.modes?.baseline;
      const llmMode = bench.modes?.llm;
      let llmDisplay = '—';
      let llmSub = 'not configured';

      const rcaConfig = meta.config?.rca;
      if (rcaConfig === 'llm' || rcaConfig === 'both') {
        if (!llmMode || llmMode.status === 'invalid') {
          llmDisplay = 'Invalid';
          llmSub = llmMode?.errors?.[0] || meta.error || 'Model returned invalid response';
        } else if (llmMode.correct !== undefined) {
          llmDisplay = `${llmMode.correct}/5`;
          llmSub = `${Math.round((llmMode.accuracy || 0) * 100)}% accuracy`;
        }
      }

      const baselineDisplay = (baselineMode && baselineMode.correct !== undefined)
        ? `${baselineMode.correct}/5`
        : '—';

      container.innerHTML = `
        <div class="run-header">
          <div>
            <div class="run-id-title">
              <h1 class="page-title" style="margin-bottom: 0; font-size: 2rem;">Run ${escapeHtml(runId)}</h1>
              <span id="run-status-pill">${renderStatusPill(status)}</span>
            </div>
            <div class="run-meta-row">
              <span><strong>Created:</strong> ${escapeHtml(formatTime(meta.created_at))}</span>
              ${meta.finished_at ? `<span><strong>Finished:</strong> ${escapeHtml(formatTime(meta.finished_at))}</span>` : ''}
              <span><strong>Mode:</strong> <span class="badge">${escapeHtml(meta.config?.rca || 'baseline')}</span></span>
              <span><strong>LLM:</strong> ${escapeHtml(meta.llm_description || 'None')}</span>
            </div>
          </div>
          <div>
            <a href="#/" class="btn btn-secondary btn-sm">${icon('arrow-right')} All Runs</a>
          </div>
        </div>

        <div id="stepper-section">
          ${renderStepper(null, stageStates)}
        </div>

        <div class="live-counters">
          <div class="badge" style="padding: 0.5rem 0.875rem; font-size: 0.875rem;">
            ${icon('refresh')} <span id="counter-probes"><strong>${probeCount}</strong> Probes</span>
          </div>
          <div class="badge" style="padding: 0.5rem 0.875rem; font-size: 0.875rem;">
            ${icon('bug')} <span id="counter-findings"><strong>${findingCount}</strong> Failures Detected</span>
          </div>
        </div>

        <!-- Event Log Section -->
        <details style="margin-bottom: 2rem;" class="traceback-details" ${status === 'running' ? 'open' : ''}>
          <summary>${icon('terminal')} Pipeline Event Log (live)</summary>
          <div id="event-log" class="event-log-container" aria-live="polite">
            <div class="event-log-entry" style="color: var(--ink-muted);">Connecting to live event stream...</div>
          </div>
        </details>

        <!-- Scorecard Section -->
        <div class="runs-section-header">
          <span class="section-label">Pipeline Scorecard</span>
        </div>
        <div class="scorecard-grid">
          <div class="stat-box">
            <span class="stat-number">${bench.detected ?? findings.length}/5</span>
            <span class="stat-label">Bugs Detected</span>
            <span class="stat-subtext">5 seeded vulnerabilities</span>
          </div>
          <div class="stat-box">
            <span class="stat-number">${bench.reproduced ?? findings.filter(f => f.reproduced).length}/5</span>
            <span class="stat-label">Reproduced on Video</span>
            <span class="stat-subtext">automated replay</span>
          </div>
          <div class="stat-box">
            <span class="stat-number">${baselineDisplay}</span>
            <span class="stat-label">Git Blame Accuracy</span>
            <span class="stat-subtext">trapped on style commit</span>
          </div>
          <div class="stat-box">
            <span class="stat-number">${llmDisplay}</span>
            <span class="stat-label">LLM Root-Cause</span>
            <span class="stat-subtext">${escapeHtml(llmSub)}</span>
          </div>
        </div>

        <!-- Tabs Navigation -->
        <div class="tabs-nav" role="tablist">
          <button class="tab-btn ${activeTab === 'findings' ? 'active' : ''}" data-tab="findings" role="tab" aria-selected="${activeTab === 'findings'}">
            ${icon('bug')} Findings (${findings.length})
          </button>
          <button class="tab-btn ${activeTab === 'benchmark' ? 'active' : ''}" data-tab="benchmark" role="tab" aria-selected="${activeTab === 'benchmark'}">
            ${icon('check')} Benchmark Results
          </button>
          <button class="tab-btn ${activeTab === 'report' ? 'active' : ''}" data-tab="report" role="tab" aria-selected="${activeTab === 'report'}">
            ${icon('file-text')} Markdown Report
          </button>
        </div>

        <!-- Tab 1: Findings List -->
        <div id="tab-findings" style="display: ${activeTab === 'findings' ? 'block' : 'none'};">
          ${renderFindingsGrid(runId, findings, rca)}
        </div>

        <!-- Tab 2: Benchmark Table -->
        <div id="tab-benchmark" style="display: ${activeTab === 'benchmark' ? 'block' : 'none'};">
          ${renderBenchmarkTable(bench)}
        </div>

        <!-- Tab 3: Markdown Report -->
        <div id="tab-report" style="display: ${activeTab === 'report' ? 'block' : 'none'};">
          <div style="display: flex; justify-content: flex-end; margin-bottom: 1rem;">
            <button id="btn-download-report" class="btn btn-secondary btn-sm">
              ${icon('download')} Download report.md
            </button>
          </div>
          <div class="card">
            ${renderMarkdown(run.report_md || '_No report generated yet._')}
          </div>
        </div>
      `;

      // Wire up tab buttons
      container.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          activeTab = btn.getAttribute('data-tab');
          container.querySelectorAll('.tab-btn').forEach(b => {
            const isActive = b.getAttribute('data-tab') === activeTab;
            b.classList.toggle('active', isActive);
            b.setAttribute('aria-selected', isActive ? 'true' : 'false');
          });
          document.getElementById('tab-findings').style.display = activeTab === 'findings' ? 'block' : 'none';
          document.getElementById('tab-benchmark').style.display = activeTab === 'benchmark' ? 'block' : 'none';
          document.getElementById('tab-report').style.display = activeTab === 'report' ? 'block' : 'none';
        });
      });

      // Wire up download report button
      document.getElementById('btn-download-report')?.addEventListener('click', () => {
        downloadFile(`report-${runId}.md`, run.report_md || '', 'text/markdown');
      });

      // Setup EventSource for live streaming
      connectEventSource();

    } catch (err) {
      container.innerHTML = `
        <div class="error-panel" role="alert">
          <div class="error-panel-content">
            <div class="error-panel-icon">${icon('alert-circle')}</div>
            <div>
              <strong>Error loading run details</strong>
              <p style="margin-top: 0.25rem;">${escapeHtml(err.message)}</p>
            </div>
          </div>
          <button id="btn-retry-run" class="btn btn-secondary btn-sm">Retry</button>
        </div>
      `;
      document.getElementById('btn-retry-run')?.addEventListener('click', () => {
        renderRunView(container, runId);
      });
    }
  }

  function connectEventSource() {
    const logBox = document.getElementById('event-log');
    if (!logBox) return;

    if (eventStream) {
      eventStream.close();
    }

    logBox.innerHTML = '';

    eventStream = streamRunEvents(
      runId,
      (eventData) => {
        const timeStr = eventData.time ? formatTime(eventData.time) : '';
        const entry = document.createElement('div');
        entry.className = 'event-log-entry';

        if (eventData.type === 'stage') {
          const stg = eventData.stage;
          const st = eventData.status;
          if (st === 'started') {
            stageStates[stg] = 'active';
          } else if (st === 'done') {
            stageStates[stg] = 'done';
          }
          const stepperSec = document.getElementById('stepper-section');
          if (stepperSec) {
            stepperSec.innerHTML = renderStepper(stg, stageStates);
          }
          entry.innerHTML = `
            <span class="event-log-time">${escapeHtml(timeStr)}</span>
            <span class="event-log-stage">[${escapeHtml(stg)}]</span>
            <span class="event-log-msg">Stage <strong>${escapeHtml(stg)}</strong> ${escapeHtml(st)}</span>
          `;
        } else if (eventData.type === 'probe') {
          probeCount = eventData.count || probeCount;
          const probeEl = document.getElementById('counter-probes');
          if (probeEl) probeEl.innerHTML = `<strong>${probeCount}</strong> Probes`;
          entry.innerHTML = `
            <span class="event-log-time">${escapeHtml(timeStr)}</span>
            <span class="event-log-stage">[probe]</span>
            <span class="event-log-msg">Probed application state (${probeCount} total probes)</span>
          `;
        } else if (eventData.type === 'finding') {
          findingCount += 1;
          const findingEl = document.getElementById('counter-findings');
          if (findingEl) findingEl.innerHTML = `<strong>${findingCount}</strong> Failures Detected`;
          const f = eventData.finding || {};
          entry.innerHTML = `
            <span class="event-log-time">${escapeHtml(timeStr)}</span>
            <span class="event-log-stage" style="color: var(--bad);">[finding]</span>
            <span class="event-log-msg">New failure: <strong>${escapeHtml(f.id)}</strong> on <code>${escapeHtml(f.route)}</code> (${escapeHtml(f.kind)})</span>
          `;
        } else {
          entry.innerHTML = `
            <span class="event-log-time">${escapeHtml(timeStr)}</span>
            <span class="event-log-stage">[info]</span>
            <span class="event-log-msg">${escapeHtml(JSON.stringify(eventData))}</span>
          `;
        }

        logBox.appendChild(entry);
        logBox.scrollTop = logBox.scrollHeight;
      },
      (err) => {
        // SSE error or stream ended
      },
      (endData) => {
        const entry = document.createElement('div');
        entry.className = 'event-log-entry';
        entry.innerHTML = `
          <span class="event-log-stage" style="color: var(--good);">[end]</span>
          <span class="event-log-msg"><strong>Pipeline finished with status: ${escapeHtml(endData.status || 'done')}</strong></span>
        `;
        logBox.appendChild(entry);
        // Refresh full view with finished data only if the run was actively running
        if (status === 'running') {
          setTimeout(() => {
            if (window.location.hash === `#/run/${runId}`) {
              loadAndRender();
            }
          }, 1000);
        }
      }
    );
    window._activeRunStream = eventStream;
  }

  await loadAndRender();
}

function renderFindingsGrid(runId, findings, rca) {
  if (!findings || findings.length === 0) {
    return `<div class="empty-state"><p>No failure findings detected in this run.</p></div>`;
  }

  const baselineList = rca.baseline || [];
  const llmList = rca.llm || [];

  return `
    <div class="findings-grid">
      ${findings.map((f) => {
        const baseResult = baselineList.find(r => r.finding_id === f.id);
        const llmResult = llmList.find(r => r.finding_id === f.id);

        const baseSha = baseResult?.suspected_commit || baseResult?.blame?.sha;
        const llmSha = llmResult?.suspected_commit;

        return `
          <a href="#/run/${encodeURIComponent(runId)}/finding/${encodeURIComponent(f.id)}" class="finding-card">
            <div class="finding-card-top">
              <span class="finding-fid">${escapeHtml(f.id)}</span>
              ${renderReproducedPill(f.reproduced)}
            </div>
            <div class="finding-route">${escapeHtml(f.method || 'GET')} ${escapeHtml(f.route)}</div>
            <div class="finding-pills">
              ${renderKindPill(f.kind)}
              <span class="badge">${f.occurrences || 1} hits</span>
            </div>
            <div class="finding-suspects">
              <div class="finding-suspect-row">
                <span>Git Blame Suspect:</span>
                <span style="font-family: var(--font-code); font-weight: 600;">${baseSha ? shortSha(baseSha) : '—'}</span>
              </div>
              <div class="finding-suspect-row">
                <span>LLM Suspect:</span>
                <span style="font-family: var(--font-code); font-weight: 600; color: var(--accent);">${llmSha ? shortSha(llmSha) : '—'}</span>
              </div>
            </div>
          </a>
        `;
      }).join('')}
    </div>
  `;
}

function renderBenchmarkTable(bench) {
  const results = bench.results || [];
  if (results.length === 0) {
    return `
      <div class="card">
        <p class="text-muted">Benchmark data is available when ground truth matches the test application routes.</p>
      </div>
    `;
  }

  return `
    <div class="table-container">
      <table class="data-table" aria-label="Benchmark Comparison Table">
        <thead>
          <tr>
            <th scope="col">Bug ID</th>
            <th scope="col">Route</th>
            <th scope="col">Exception</th>
            <th scope="col">Detected</th>
            <th scope="col">Reproduced</th>
            <th scope="col">Baseline (Git Blame)</th>
            <th scope="col">LLM Agent</th>
          </tr>
        </thead>
        <tbody>
          ${results.map((r) => {
            const baseMode = r.modes?.baseline;
            const llmMode = r.modes?.llm;

            let baseCell = '—';
            if (baseMode) {
              if (baseMode.correct) {
                baseCell = `<span class="chip chip-blame-correct">${icon('check')} Correct (${shortSha(baseMode.suspected_commit)})</span>`;
              } else {
                baseCell = `<span class="chip chip-blame-wrong">${icon('x')} Trapped (${shortSha(baseMode.suspected_commit)})</span>`;
              }
            }

            let llmCell = '—';
            if (llmMode) {
              if (llmMode.correct) {
                llmCell = `<span class="chip chip-blame-correct">${icon('check')} Correct (${shortSha(llmMode.suspected_commit)})</span>`;
              } else {
                llmCell = `<span class="chip chip-blame-wrong">${icon('x')} Wrong (${shortSha(llmMode.suspected_commit)})</span>`;
              }
            }

            return `
              <tr>
                <td><strong>${escapeHtml(r.bug_id)}</strong></td>
                <td><code style="font-family: var(--font-code);">${escapeHtml(r.route)}</code></td>
                <td><span class="badge badge-code">${escapeHtml(r.exception || '')}</span></td>
                <td>
                  ${r.detected
                    ? `<span style="color: var(--good); display: inline-flex; align-items: center; gap: 0.25rem;">${icon('check')} Detected</span>`
                    : `<span style="color: var(--bad); display: inline-flex; align-items: center; gap: 0.25rem;">${icon('x')} Missed</span>`}
                </td>
                <td>
                  ${r.reproduced
                    ? `<span style="color: var(--good); display: inline-flex; align-items: center; gap: 0.25rem;">${icon('check')} Reproduced</span>`
                    : `<span style="color: var(--bad); display: inline-flex; align-items: center; gap: 0.25rem;">${icon('x')} Failed</span>`}
                </td>
                <td>${baseCell}</td>
                <td>${llmCell}</td>
              </tr>
            `;
          }).join('')}
        </tbody>
      </table>
    </div>
  `;
}
