/**
 * Status and metadata pill components (icon + word, never color alone).
 */
import { icon } from './icons.js';
import { escapeHtml } from '../util.js';

/**
 * Render run status pill.
 */
export function renderStatusPill(status) {
  const s = String(status || 'queued').toLowerCase();
  let iconName = 'clock';
  let className = 'status-queued';
  let label = 'Queued';

  if (s === 'running') {
    iconName = 'refresh';
    className = 'status-running';
    label = 'Running';
  } else if (s === 'done' || s === 'completed' || s === 'success') {
    iconName = 'check';
    className = 'status-done';
    label = 'Done';
  } else if (s === 'failed' || s === 'error') {
    iconName = 'alert-circle';
    className = 'status-failed';
    label = 'Failed';
  } else if (s === 'invalid') {
    iconName = 'alert-circle';
    className = 'status-invalid';
    label = 'Invalid';
  }

  return `<span class="status-pill ${className}">${icon(iconName)} ${escapeHtml(label)}</span>`;
}

/**
 * Render reproduced pill.
 */
export function renderReproducedPill(reproduced) {
  if (reproduced === true) {
    return `<span class="status-pill status-done">${icon('check')} Reproduced</span>`;
  } else if (reproduced === false) {
    return `<span class="status-pill status-failed">${icon('x')} Not Reproduced</span>`;
  }
  return `<span class="status-pill status-queued">${icon('clock')} Unverified</span>`;
}

/**
 * Render finding failure kind pill.
 */
export function renderKindPill(kind) {
  const k = String(kind || 'unknown');
  let label = k;
  if (k === 'http_500') label = 'HTTP 500';
  else if (k === 'js_error') label = 'JS Error';
  else if (k === 'console_error') label = 'Console Error';
  else if (k === 'request_failed') label = 'Request Failed';

  return `<span class="badge badge-code">${icon('bug')} ${escapeHtml(label)}</span>`;
}
