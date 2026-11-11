/**
 * Horizontal Stage Stepper Component.
 * Stages: Seed, Server, Explore, Reproduce, Root-cause, Report, Benchmark.
 */
import { icon } from './icons.js';
import { escapeHtml } from '../util.js';

export const STAGES = [
  { id: 'seed', name: 'Seed' },
  { id: 'server', name: 'Server' },
  { id: 'explore', name: 'Explore' },
  { id: 'reproduce', name: 'Reproduce' },
  { id: 'rca', name: 'Root-cause' },
  { id: 'report', name: 'Report' },
  { id: 'benchmark', name: 'Benchmark' },
];

/**
 * Render horizontal stepper HTML.
 * @param {string} currentStage - Current active stage id
 * @param {Record<string, string>} stageStates - Map of stage id -> 'done'|'active'|'pending'
 */
export function renderStepper(currentStage, stageStates = {}) {
  let html = '<div class="stepper-container" role="region" aria-label="Pipeline Stages">';

  STAGES.forEach((stage, idx) => {
    const state = stageStates[stage.id] || 'pending';
    const isDone = state === 'done';
    const isActive = state === 'active' || (stage.id === currentStage && !isDone);

    let stateClass = 'pending';
    let dotContent = `${idx + 1}`;

    if (isDone) {
      stateClass = 'done';
      dotContent = icon('check');
    } else if (isActive) {
      stateClass = 'active';
      dotContent = icon('refresh');
    }

    html += `
      <div class="stepper-step ${stateClass}" aria-current="${isActive ? 'step' : 'false'}">
        <div class="stepper-dot" aria-hidden="true">${dotContent}</div>
        <span class="stepper-name">${escapeHtml(stage.name)}</span>
      </div>
    `;

    if (idx < STAGES.length - 1) {
      html += `<div class="stepper-line" aria-hidden="true"></div>`;
    }
  });

  html += '</div>';
  return html;
}
