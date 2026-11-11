/**
 * Commit Timeline Component.
 * Visualizes commits touching the failing line with chips for blame, LLM, and ground truth.
 */
import { icon } from './icons.js';
import { escapeHtml } from '../util.js';

export function renderTimeline(timeline = []) {
  if (!timeline || timeline.length === 0) {
    return `<p class="text-muted">No commit history available for this line.</p>`;
  }

  // Determine if there is a blame trap (blame pointed at non-culprit while true culprit is earlier)
  const blamedCommit = timeline.find(c => c.blamed);
  const truthCommit = timeline.find(c => c.truth);
  const isBlameTrap = blamedCommit && truthCommit && blamedCommit.sha !== truthCommit.sha;

  let html = '';

  if (isBlameTrap) {
    html += `
      <div class="callout-blame-trap" role="alert">
        <div class="callout-blame-trap-icon" aria-hidden="true">${icon('alert-circle')}</div>
        <div>
          <strong>Blame trap:</strong> git blame points at a formatting commit. The behaviour changed earlier.
        </div>
      </div>
    `;
  }

  html += `<div class="timeline-container" role="feed" aria-label="Commit timeline">`;

  timeline.forEach((commit) => {
    let nodeClasses = ['timeline-node'];
    if (commit.blamed) nodeClasses.push('blamed');
    if (commit.truth) nodeClasses.push('truth');
    if (commit.llm_suspect) nodeClasses.push('llm-suspect');

    const chips = [];

    if (commit.blamed) {
      if (commit.truth) {
        chips.push(`<span class="chip chip-blame-correct">${icon('check')} git blame says</span>`);
      } else {
        chips.push(`<span class="chip chip-blame-wrong">${icon('alert-circle')} git blame says</span>`);
      }
    }

    if (commit.llm_suspect) {
      chips.push(`<span class="chip chip-llm">${icon('git-commit')} LLM says</span>`);
    }

    if (commit.truth) {
      chips.push(`<span class="chip chip-truth">${icon('check')} True culprit</span>`);
    }

    html += `
      <div class="${nodeClasses.join(' ')}">
        <div class="timeline-dot" aria-hidden="true"></div>
        <div class="timeline-card">
          <div class="timeline-header">
            <span class="timeline-sha">${escapeHtml(commit.short || commit.sha.slice(0, 7))}</span>
            <div class="timeline-chips">
              ${chips.join('')}
            </div>
          </div>
          <p class="timeline-subject"><strong>${escapeHtml(commit.subject)}</strong></p>
          <p class="timeline-meta text-muted" style="font-size: 0.8125rem; margin-top: 0.375rem;">
            ${escapeHtml(commit.author)} on ${escapeHtml(commit.date)}
          </p>
        </div>
      </div>
    `;
  });

  html += `</div>`;
  return html;
}
