/**
 * Finding Detail View (#/run/:id/finding/:fid):
 * Two-column layout: steps, video, screenshot, root-cause, confidence, code, traceback, diff, and commit timeline.
 */
import { fetchRun, fetchTimeline } from '../api.js';
import { renderStatusPill, renderKindPill, renderReproducedPill } from '../components/pill.js';
import { renderTimeline } from '../components/timeline.js';
import { icon } from '../components/icons.js';
import { escapeHtml, describeStep, shortSha } from '../util.js';

export async function renderFindingView(container, runId, fid) {
  container.innerHTML = `
    <div class="skeleton" style="height: 60px; margin-bottom: 1.5rem;"></div>
    <div class="skeleton" style="height: 400px;"></div>
  `;

  try {
    const [run, timeline] = await Promise.all([
      fetchRun(runId),
      fetchTimeline(runId, fid),
    ]);

    const findings = run.findings || [];
    const finding = findings.find(f => f.id === fid);

    if (!finding) {
      container.innerHTML = `
        <div class="error-panel" role="alert">
          <div class="error-panel-content">
            <div class="error-panel-icon">${icon('alert-circle')}</div>
            <div>
              <strong>Finding not found</strong>
              <p>No finding with ID "${escapeHtml(fid)}" exists in run ${escapeHtml(runId)}.</p>
            </div>
          </div>
          <a href="#/run/${encodeURIComponent(runId)}" class="btn btn-secondary btn-sm">Back to Run</a>
        </div>
      `;
      return;
    }

    // Determine RCA result (prefer LLM result if available, else baseline)
    const rcaLlm = (run.rca?.llm || []).find(r => r.finding_id === fid);
    const rcaBase = (run.rca?.baseline || []).find(r => r.finding_id === fid);
    const rca = rcaLlm || rcaBase || {};

    const confidenceVal = rca.confidence !== undefined ? Math.round(rca.confidence * 100) : 100;
    const mediaVideoUrl = finding.video ? `/api/runs/${encodeURIComponent(runId)}/media/${finding.video}` : null;
    const mediaScreenshotUrl = finding.screenshot ? `/api/runs/${encodeURIComponent(runId)}/media/${finding.screenshot}` : null;

    container.innerHTML = `
      <!-- Breadcrumb & Header -->
      <nav aria-label="Breadcrumb" style="margin-bottom: 1rem;">
        <div style="display: flex; align-items: center; gap: 0.5rem; font-size: 0.875rem;">
          <a href="#/">Runs</a>
          <span class="text-muted">/</span>
          <a href="#/run/${encodeURIComponent(runId)}" style="font-family: var(--font-code);">${escapeHtml(runId)}</a>
          <span class="text-muted">/</span>
          <span style="font-family: var(--font-code); font-weight: 600;">${escapeHtml(finding.id)}</span>
        </div>
      </nav>

      <div class="run-header">
        <div>
          <div class="run-id-title">
            <h1 class="page-title" style="margin-bottom: 0;">${escapeHtml(finding.id)}: ${escapeHtml(finding.summary || finding.route)}</h1>
            ${renderReproducedPill(finding.reproduced)}
            ${renderKindPill(finding.kind)}
          </div>
          <div class="run-meta-row">
            <span><strong>Route:</strong> <code>${escapeHtml(finding.route)}</code></span>
            <span><strong>Method:</strong> <span class="badge">${escapeHtml(finding.method || 'GET')}</span></span>
            <span><strong>Status Code:</strong> <span class="badge">${finding.status || 500}</span></span>
            <span><strong>Hits:</strong> ${finding.occurrences || 1}</span>
          </div>
        </div>
        <div>
          <a href="#/run/${encodeURIComponent(runId)}" class="btn btn-secondary btn-sm">
            ${icon('arrow-right')} Back to Run
          </a>
        </div>
      </div>

      <!-- HERO: Commit Timeline -->
      <section class="card" style="margin-bottom: 2rem;" aria-labelledby="timeline-heading">
        <div class="runs-section-header" style="margin-bottom: 0.5rem;">
          <h2 id="timeline-heading" class="section-label" style="font-size: 0.8125rem;">Commit Timeline & Suspect Attribution</h2>
          <span class="text-muted" style="font-size: 0.8125rem;">Git history touching the failing line</span>
        </div>
        ${renderTimeline(timeline)}
      </section>

      <!-- Two-Column Layout -->
      <div class="finding-layout">
        
        <!-- Left Column: Reproduction & Evidence Media -->
        <div class="finding-col">
          <section class="card" aria-labelledby="repro-heading">
            <h2 id="repro-heading" class="card-title">Steps to Reproduce</h2>
            <ol class="steps-list">
              ${(finding.steps || []).map(step => `
                <li>${describeStep(step)}</li>
              `).join('')}
            </ol>
          </section>

          <section class="card" aria-labelledby="media-heading">
            <h2 id="media-heading" class="card-title">Reproduction Video & Screenshot</h2>
            <div class="media-viewer">
              ${mediaVideoUrl ? `
                <video controls preload="metadata" ${mediaScreenshotUrl ? `poster="${mediaScreenshotUrl}"` : ''}>
                  <source src="${mediaVideoUrl}" type="video/webm">
                  Your browser does not support the video tag.
                </video>
              ` : '<p class="text-muted" style="padding: 1rem;">No video recorded.</p>'}

              ${mediaScreenshotUrl ? `
                <div style="padding: 0.75rem 1rem; font-size: 0.75rem; color: var(--ink-muted); font-weight: 600; text-transform: uppercase; background-color: var(--surface-2);">
                  Failure Snapshot
                </div>
                <img src="${mediaScreenshotUrl}" alt="Failure snapshot for ${escapeHtml(finding.id)}">
              ` : ''}
            </div>
          </section>
        </div>

        <!-- Right Column: Root Cause, Source Code, Traceback, Patch -->
        <div class="finding-col">
          
          <section class="card" aria-labelledby="rca-heading">
            <h2 id="rca-heading" class="card-title">Root Cause Analysis</h2>
            <p style="margin-bottom: 1.25rem; font-size: 0.9375rem; line-height: 1.6;">
              ${escapeHtml(rca.root_cause || rca.summary || 'Root-cause analysis completed.')}
            </p>

            <div style="margin-bottom: 1.25rem;">
              <span class="section-label" style="display: block; margin-bottom: 0.375rem;">Analysis Confidence</span>
              <div class="confidence-container">
                <div class="confidence-bar-bg" role="progressbar" aria-valuenow="${confidenceVal}" aria-valuemin="0" aria-valuemax="100">
                  <div class="confidence-bar-fill" style="width: ${confidenceVal}%;"></div>
                </div>
                <span class="confidence-value">${confidenceVal}%</span>
              </div>
            </div>

            ${(rca.evidence && rca.evidence.length > 0) ? `
              <div>
                <span class="section-label" style="display: block; margin-bottom: 0.5rem;">Evidence</span>
                <ul class="evidence-list">
                  ${rca.evidence.map(e => `<li>${escapeHtml(e)}</li>`).join('')}
                </ul>
              </div>
            ` : ''}
          </section>

          <!-- Source Code Panel -->
          ${rca.code_context ? `
            <section class="card" style="padding: 0; overflow: hidden;" aria-labelledby="code-heading">
              <div class="code-panel">
                <div class="code-panel-header">
                  <span id="code-heading">${escapeHtml(rca.location || 'Failing Source Context')}</span>
                  <span>Failing Line Highlighted</span>
                </div>
                <pre><code>${formatCodeContext(rca.code_context)}</code></pre>
              </div>
            </section>
          ` : ''}

          <!-- Server Traceback (Collapsible) -->
          ${(rca.server_trace?.raw || rca.server_trace) ? `
            <details class="traceback-details">
              <summary>${icon('terminal')} Server Traceback</summary>
              <pre><code>${escapeHtml(typeof rca.server_trace === 'string' ? rca.server_trace : (rca.server_trace.raw || JSON.stringify(rca.server_trace, null, 2)))}</code></pre>
            </details>
          ` : ''}

          <!-- Proposed Patch Panel -->
          ${rca.patch ? `
            <section class="card" aria-labelledby="patch-heading">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                <h2 id="patch-heading" class="card-title" style="margin-bottom: 0;">Proposed Patch</h2>
                ${rca.patch_applies !== undefined ? `
                  <span class="status-pill ${rca.patch_applies ? 'status-done' : 'status-failed'}">
                    ${icon(rca.patch_applies ? 'check' : 'x')} Applies Cleanly: ${rca.patch_applies ? 'Yes' : 'No'}
                  </span>
                ` : ''}
              </div>
              <div class="code-panel">
                <pre><code>${formatDiff(rca.patch)}</code></pre>
              </div>
            </section>
          ` : ''}

        </div>
      </div>
    `;

  } catch (err) {
    container.innerHTML = `
      <div class="error-panel" role="alert">
        <div class="error-panel-content">
          <div class="error-panel-icon">${icon('alert-circle')}</div>
          <div>
            <strong>Error loading finding details</strong>
            <p style="margin-top: 0.25rem;">${escapeHtml(err.message)}</p>
          </div>
        </div>
        <button id="btn-retry-finding" class="btn btn-secondary btn-sm">Retry</button>
      </div>
    `;
    document.getElementById('btn-retry-finding')?.addEventListener('click', () => {
      renderFindingView(container, runId, fid);
    });
  }
}

function formatCodeContext(contextText) {
  const lines = String(contextText).split(/\r?\n/);
  return lines.map((line) => {
    const isHighlight = line.trim().startsWith('>');
    const cleanLine = isHighlight ? line.replace(/^\s*>\s?/, '  ') : line;
    return `<div class="code-line ${isHighlight ? 'highlight' : ''}"><span class="code-line-text">${escapeHtml(cleanLine)}</span></div>`;
  }).join('');
}

function formatDiff(diffText) {
  const lines = String(diffText).split(/\r?\n/);
  return lines.map((line) => {
    let diffClass = '';
    if (line.startsWith('+') && !line.startsWith('+++')) {
      diffClass = 'diff-line-add';
    } else if (line.startsWith('-') && !line.startsWith('---')) {
      diffClass = 'diff-line-del';
    }
    return `<div class="code-line ${diffClass}"><span class="code-line-text">${escapeHtml(line)}</span></div>`;
  }).join('');
}
