/**
 * New Run View (#/new): Configure and launch a QA pipeline run.
 */
import { fetchConfig, createRun } from '../api.js';
import { icon } from '../components/icons.js';
import { escapeHtml } from '../util.js';

export async function renderNewRunView(container) {
  container.innerHTML = `
    <div class="skeleton" style="height: 100px; max-width: 760px; margin: 0 auto 2rem;"></div>
    <div class="skeleton" style="height: 350px; max-width: 760px; margin: 0 auto;"></div>
  `;

  try {
    const config = await fetchConfig();
    const providers = config.providers || [];
    const llmConfigured = config.llm_available || false;

    container.innerHTML = `
      <div class="form-container">
        <div style="margin-bottom: 2rem;">
          <h1 class="page-title">Start a New Run</h1>
          <p class="text-muted">Configure the exploration pipeline and root-cause analysis mode.</p>
        </div>

        <form id="new-run-form" novalidate>
          <div class="form-group">
            <label class="form-label">Root-Cause Analysis Mode</label>
            <div class="mode-cards-grid" role="radiogroup" aria-label="Root-Cause Analysis Mode">
              
              <div class="mode-card selected" data-mode="baseline" tabindex="0" role="radio" aria-checked="true">
                <div class="mode-card-header">
                  <span class="mode-card-title">Baseline</span>
                  <span class="badge">No key required</span>
                </div>
                <p class="mode-card-desc">Git blame on the failing line. Fast, deterministic, traps on style commits.</p>
              </div>

              <div class="mode-card ${!llmConfigured ? 'requires-key' : ''}" data-mode="llm" tabindex="0" role="radio" aria-checked="false">
                <div class="mode-card-header">
                  <span class="mode-card-title">LLM Agent</span>
                  <span class="badge ${llmConfigured ? 'status-done' : ''}">${llmConfigured ? 'Ready' : 'Key Needed'}</span>
                </div>
                <p class="mode-card-desc">AI-powered code and history reasoning. Inspects multi-commit diffs and proposes patches.</p>
              </div>

              <div class="mode-card ${!llmConfigured ? 'requires-key' : ''}" data-mode="both" tabindex="0" role="radio" aria-checked="false">
                <div class="mode-card-header">
                  <span class="mode-card-title">Both, Compared</span>
                  <span class="badge">Benchmark</span>
                </div>
                <p class="mode-card-desc">Runs both methods side-by-side to evaluate accuracy and demonstrate blame traps.</p>
              </div>

            </div>
            ${!llmConfigured ? `
              <div class="callout-blame-trap" style="margin-top: 1rem; border-left-color: var(--warn); background-color: var(--warn-tint);" role="status">
                <div class="callout-blame-trap-icon" style="color: var(--warn);" aria-hidden="true">${icon('info')}</div>
                <div style="font-size: var(--text-xs); color: var(--ink);">
                  <strong>LLM Key Notice:</strong> No environment API key was detected for any provider. LLM modes require entering an API key in the field below, or you may run in Baseline mode without an API key.
                </div>
              </div>
            ` : ''}
          </div>

          <div class="form-group" id="provider-group">
            <label for="provider-select" class="form-label">LLM Provider</label>
            <select id="provider-select" class="form-control">
              ${providers.map(p => `
                <option value="${escapeHtml(p.name)}" ${p.configured ? 'selected' : ''}>
                  ${escapeHtml(p.name)} (${p.configured ? 'Key configured in environment' : 'Needs API key'})
                </option>
              `).join('')}
            </select>
            <div class="form-helper" id="provider-hint"></div>
          </div>

          <div class="form-group" id="key-group">
            <label for="api-key-input" class="form-label">API Key (optional)</label>
            <input type="password" id="api-key-input" class="form-control" placeholder="Paste temporary API key" autocomplete="off">
            <p class="form-helper">Used for this run only. Never saved to disk or logs.</p>
          </div>

          <div class="checkbox-group">
            <label class="checkbox-label">
              <input type="checkbox" id="check-llm-payloads" ${llmConfigured ? 'checked' : ''}>
              <span>Let the model suggest test inputs (fuzzing)</span>
            </label>
            <label class="checkbox-label">
              <input type="checkbox" id="check-reseed" checked>
              <span>Rebuild the seeded test repo (resets git commits and SQLite database)</span>
            </label>
          </div>

          <div id="submit-error" style="display: none;" class="error-panel" role="alert">
            <div class="error-panel-content">
              <div class="error-panel-icon">${icon('alert-circle')}</div>
              <div id="submit-error-msg"></div>
            </div>
          </div>

          <div style="display: flex; gap: 1rem; align-items: center; margin-top: 2rem;">
            <button type="submit" id="btn-submit-run" class="btn btn-primary">
              ${icon('play')} Launch Pipeline Run
            </button>
            <a href="#/" class="btn btn-secondary">Cancel</a>
          </div>
        </form>
      </div>
    `;

    let selectedMode = config.default_rca_mode || 'baseline';
    const form = document.getElementById('new-run-form');
    const modeCards = container.querySelectorAll('.mode-card');
    const providerSelect = document.getElementById('provider-select');
    const apiKeyInput = document.getElementById('api-key-input');
    const providerHint = document.getElementById('provider-hint');
    const submitError = document.getElementById('submit-error');
    const submitErrorMsg = document.getElementById('submit-error-msg');
    const submitBtn = document.getElementById('btn-submit-run');

    function updateModeSelection(mode) {
      selectedMode = mode;
      modeCards.forEach(c => {
        const isMatch = c.getAttribute('data-mode') === mode;
        c.classList.toggle('selected', isMatch);
        c.setAttribute('aria-checked', isMatch ? 'true' : 'false');
      });
      updateProviderVisibility();
    }

    function updateProviderVisibility() {
      const selectedProviderName = providerSelect.value;
      const prov = providers.find(p => p.name === selectedProviderName);
      if (prov) {
        if (prov.configured) {
          providerHint.innerHTML = `<span style="color: var(--good);">${icon('check')} Key found in environment variable \`${escapeHtml(prov.key_env)}\`.</span>`;
        } else {
          providerHint.innerHTML = `<span style="color: var(--warn);">${icon('alert-circle')} No \`${escapeHtml(prov.key_env)}\` detected. Please provide an API key below to use this provider.</span>`;
        }
      }
    }

    modeCards.forEach(card => {
      card.addEventListener('click', () => {
        updateModeSelection(card.getAttribute('data-mode'));
      });
      card.addEventListener('keydown', (e) => {
        if (e.key === ' ' || e.key === 'Enter') {
          e.preventDefault();
          updateModeSelection(card.getAttribute('data-mode'));
        }
      });
    });

    providerSelect.addEventListener('change', updateProviderVisibility);
    updateModeSelection(selectedMode);

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      submitError.style.display = 'none';

      const provider = providerSelect.value;
      const apiKey = apiKeyInput.value.trim() || undefined;
      const llmPayloads = document.getElementById('check-llm-payloads').checked;
      const reseed = document.getElementById('check-reseed').checked;

      // Validate LLM requirement
      if ((selectedMode === 'llm' || selectedMode === 'both') && !apiKey) {
        const prov = providers.find(p => p.name === provider);
        if (!prov || !prov.configured) {
          submitError.style.display = 'flex';
          submitErrorMsg.textContent = `Provider "${provider}" is not configured. Please enter an API key or switch to Baseline mode.`;
          return;
        }
      }

      submitBtn.disabled = true;
      submitBtn.innerHTML = `${icon('refresh')} Starting run...`;

      try {
        const payload = {
          rca: selectedMode,
          provider: (selectedMode === 'baseline') ? undefined : provider,
          llm_payloads: llmPayloads,
          reseed: reseed,
          api_key: apiKey,
        };

        const result = await createRun(payload);
        if (result && result.run_id) {
          window.location.hash = `#/run/${result.run_id}`;
        } else {
          throw new Error('Server did not return a run ID');
        }
      } catch (err) {
        submitError.style.display = 'flex';
        submitErrorMsg.textContent = err.message || 'Failed to start run';
        submitBtn.disabled = false;
        submitBtn.innerHTML = `${icon('play')} Launch Pipeline Run`;
      }
    });

  } catch (err) {
    container.innerHTML = `
      <div class="error-panel" role="alert">
        <div class="error-panel-content">
          <div class="error-panel-icon">${icon('alert-circle')}</div>
          <div>
            <strong>Error loading configuration</strong>
            <p style="margin-top: 0.25rem;">${escapeHtml(err.message)}</p>
          </div>
        </div>
        <button id="btn-retry-config" class="btn btn-secondary btn-sm">Retry</button>
      </div>
    `;
    document.getElementById('btn-retry-config')?.addEventListener('click', () => {
      renderNewRunView(container);
    });
  }
}
