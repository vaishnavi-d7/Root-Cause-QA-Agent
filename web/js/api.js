/**
 * API client for RootCause-QA backend.
 */

const API_BASE = '/api';

/**
 * Perform a JSON request with robust error handling.
 */
async function request(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const headers = {
    'Accept': 'application/json',
    ...(options.headers || {}),
  };

  if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }

  const response = await fetch(url, { ...options, headers });
  
  if (!response.ok) {
    let errorDetail = response.statusText;
    try {
      const data = await response.json();
      errorDetail = data.detail || data.error || JSON.stringify(data);
    } catch (_) {
      try {
        errorDetail = await response.text();
      } catch (_) {}
    }
    const err = new Error(errorDetail || `HTTP ${response.status}`);
    err.status = response.status;
    throw err;
  }

  if (response.status === 204) {
    return null;
  }

  return await response.json();
}

export async function fetchHealth() {
  return await request('/health');
}

export async function fetchConfig() {
  return await request('/config');
}

export async function fetchRuns() {
  return await request('/runs');
}

export async function fetchRun(id) {
  return await request(`/runs/${encodeURIComponent(id)}`);
}

export async function createRun(payload) {
  return await request('/runs', {
    method: 'POST',
    body: payload,
  });
}

export async function deleteRun(id) {
  return await request(`/runs/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
}

export async function fetchTimeline(runId, fid) {
  return await request(`/runs/${encodeURIComponent(runId)}/findings/${encodeURIComponent(fid)}/timeline`);
}

/**
 * Connect to Server-Sent Events stream for a run.
 * Returns a controller with a close() method.
 */
export function streamRunEvents(runId, onEvent, onError, onEnd) {
  const url = `${API_BASE}/runs/${encodeURIComponent(runId)}/events`;
  const es = new EventSource(url);

  es.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'end') {
        if (onEnd) onEnd(data);
        es.close();
      } else {
        if (onEvent) onEvent(data);
      }
    } catch (err) {
      console.warn('Failed to parse SSE event:', err);
    }
  };

  es.onerror = (err) => {
    if (onError) onError(err);
  };

  return {
    close() {
      es.close();
    }
  };
}
