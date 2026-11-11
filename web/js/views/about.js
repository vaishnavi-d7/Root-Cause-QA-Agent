/**
 * About / How It Works View (#/about):
 * Architecture overview, inline-SVG pipeline diagram, blame-trap explainer, and limitations.
 */
import { icon } from '../components/icons.js';

export function renderAboutView(container) {
  container.innerHTML = `
    <div class="about-hero">
      <h1 class="page-title">How RootCause-QA Works</h1>
      <p class="hero-subtitle">
        An autonomous QA agent bridging the gap between browser automation and source code version control.
      </p>
    </div>

    <!-- Inline-SVG Architecture Diagram -->
    <div class="diagram-container" role="img" aria-label="RootCause-QA Pipeline Architecture Diagram">
      <svg viewBox="0 0 960 220" fill="none" xmlns="http://www.w3.org/2000/svg">
        <!-- Stage 1: Seed -->
        <g id="stage-seed">
          <rect x="10" y="30" width="130" height="130" rx="10" fill="#F7F3EC" stroke="#E2DACB" stroke-width="2"/>
          <circle cx="75" cy="65" r="18" fill="#EFE9DF" stroke="#9E4527" stroke-width="2"/>
          <text x="75" y="70" text-anchor="middle" font-family="'IBM Plex Mono', monospace" font-size="12" font-weight="600" fill="#9E4527">01</text>
          <text x="75" y="105" text-anchor="middle" font-family="'Fraunces', serif" font-size="14" font-weight="600" fill="#22262B">Seed</text>
          <text x="75" y="125" text-anchor="middle" font-family="'Public Sans', sans-serif" font-size="10" fill="#5E6670">Git history & db</text>
          <text x="75" y="140" text-anchor="middle" font-family="'Public Sans', sans-serif" font-size="10" fill="#5E6670">Mini Shop app</text>
        </g>

        <!-- Arrow 1 -> 2 -->
        <path d="M142 95 L168 95" stroke="#9E4527" stroke-width="2" stroke-linecap="round"/>
        <polygon points="172,95 165,91 165,99" fill="#9E4527"/>

        <!-- Stage 2: Server -->
        <g id="stage-server">
          <rect x="175" y="30" width="130" height="130" rx="10" fill="#F7F3EC" stroke="#E2DACB" stroke-width="2"/>
          <circle cx="240" cy="65" r="18" fill="#EFE9DF" stroke="#9E4527" stroke-width="2"/>
          <text x="240" y="70" text-anchor="middle" font-family="'IBM Plex Mono', monospace" font-size="12" font-weight="600" fill="#9E4527">02</text>
          <text x="240" y="105" text-anchor="middle" font-family="'Fraunces', serif" font-size="14" font-weight="600" fill="#22262B">Server</text>
          <text x="240" y="125" text-anchor="middle" font-family="'Public Sans', sans-serif" font-size="10" fill="#5E6670">Subprocess log</text>
          <text x="240" y="140" text-anchor="middle" font-family="'Public Sans', sans-serif" font-size="10" fill="#5E6670">Error traces</text>
        </g>

        <!-- Arrow 2 -> 3 -->
        <path d="M307 95 L333 95" stroke="#9E4527" stroke-width="2" stroke-linecap="round"/>
        <polygon points="337,95 330,91 330,99" fill="#9E4527"/>

        <!-- Stage 3: Explore -->
        <g id="stage-explore">
          <rect x="340" y="30" width="130" height="130" rx="10" fill="#F7F3EC" stroke="#E2DACB" stroke-width="2"/>
          <circle cx="405" cy="65" r="18" fill="#EFE9DF" stroke="#9E4527" stroke-width="2"/>
          <text x="405" y="70" text-anchor="middle" font-family="'IBM Plex Mono', monospace" font-size="12" font-weight="600" fill="#9E4527">03</text>
          <text x="405" y="105" text-anchor="middle" font-family="'Fraunces', serif" font-size="14" font-weight="600" fill="#22262B">Explore</text>
          <text x="405" y="125" text-anchor="middle" font-family="'Public Sans', sans-serif" font-size="10" fill="#5E6670">Playwright crawl</text>
          <text x="405" y="140" text-anchor="middle" font-family="'Public Sans', sans-serif" font-size="10" fill="#5E6670">Fuzz payloads</text>
        </g>

        <!-- Arrow 3 -> 4 -->
        <path d="M472 95 L498 95" stroke="#9E4527" stroke-width="2" stroke-linecap="round"/>
        <polygon points="502,95 495,91 495,99" fill="#9E4527"/>

        <!-- Stage 4: Reproduce -->
        <g id="stage-reproduce">
          <rect x="505" y="30" width="130" height="130" rx="10" fill="#F7F3EC" stroke="#E2DACB" stroke-width="2"/>
          <circle cx="570" cy="65" r="18" fill="#EFE9DF" stroke="#9E4527" stroke-width="2"/>
          <text x="570" y="70" text-anchor="middle" font-family="'IBM Plex Mono', monospace" font-size="12" font-weight="600" fill="#9E4527">04</text>
          <text x="570" y="105" text-anchor="middle" font-family="'Fraunces', serif" font-size="14" font-weight="600" fill="#22262B">Reproduce</text>
          <text x="570" y="125" text-anchor="middle" font-family="'Public Sans', sans-serif" font-size="10" fill="#5E6670">Clean browser</text>
          <text x="570" y="140" text-anchor="middle" font-family="'Public Sans', sans-serif" font-size="10" fill="#5E6670">WebM video</text>
        </g>

        <!-- Arrow 4 -> 5 -->
        <path d="M637 95 L663 95" stroke="#9E4527" stroke-width="2" stroke-linecap="round"/>
        <polygon points="667,95 660,91 660,99" fill="#9E4527"/>

        <!-- Stage 5: Root-cause -->
        <g id="stage-rca">
          <rect x="670" y="30" width="130" height="130" rx="10" fill="#F7F3EC" stroke="#E2DACB" stroke-width="2"/>
          <circle cx="735" cy="65" r="18" fill="#EFE9DF" stroke="#9E4527" stroke-width="2"/>
          <text x="735" y="70" text-anchor="middle" font-family="'IBM Plex Mono', monospace" font-size="12" font-weight="600" fill="#9E4527">05</text>
          <text x="735" y="105" text-anchor="middle" font-family="'Fraunces', serif" font-size="14" font-weight="600" fill="#22262B">Root-cause</text>
          <text x="735" y="125" text-anchor="middle" font-family="'Public Sans', sans-serif" font-size="10" fill="#5E6670">git log -L history</text>
          <text x="735" y="140" text-anchor="middle" font-family="'Public Sans', sans-serif" font-size="10" fill="#5E6670">LLM code analyzer</text>
        </g>

        <!-- Arrow 5 -> 6 -->
        <path d="M802 95 L828 95" stroke="#9E4527" stroke-width="2" stroke-linecap="round"/>
        <polygon points="832,95 825,91 825,99" fill="#9E4527"/>

        <!-- Stage 6: Report & Benchmark -->
        <g id="stage-report">
          <rect x="835" y="30" width="115" height="130" rx="10" fill="#F7F3EC" stroke="#276A42" stroke-width="2"/>
          <circle cx="892" cy="65" r="18" fill="#EFE9DF" stroke="#276A42" stroke-width="2"/>
          <text x="892" y="70" text-anchor="middle" font-family="'IBM Plex Mono', monospace" font-size="12" font-weight="600" fill="#276A42">06</text>
          <text x="892" y="105" text-anchor="middle" font-family="'Fraunces', serif" font-size="14" font-weight="600" fill="#22262B">Benchmark</text>
          <text x="892" y="125" text-anchor="middle" font-family="'Public Sans', sans-serif" font-size="10" fill="#5E6670">Accuracy score</text>
          <text x="892" y="140" text-anchor="middle" font-family="'Public Sans', sans-serif" font-size="10" fill="#5E6670">report.md</text>
        </g>
      </svg>
    </div>

    <div class="about-cards-grid">
      
      <!-- Card: The Blame Trap Explainer -->
      <section class="card" aria-labelledby="blametrap-heading">
        <h2 id="blametrap-heading" class="card-title">The Blame Trap</h2>
        <p style="margin-bottom: 1rem; color: var(--ink);">
          Most automated root-cause tools use <code>git blame</code> to identify who modified the failing line of code. However, <code>git blame</code> is easily trapped:
        </p>
        <ul class="steps-list" style="margin-bottom: 1.25rem;">
          <li>A developer writes a functional bug in commit <em>A</em>.</li>
          <li>Later, another developer runs a code linter or wraps a long line in commit <em>B</em>.</li>
          <li><code>git blame</code> blames commit <em>B</em> because it touched the characters last, even though commit <em>B</em> was purely aesthetic.</li>
        </ul>
        <p style="color: var(--ink-muted); font-size: 0.875rem;">
          RootCause-QA uses <code>git log -L</code> to inspect the full chronological history of the failing line, feeding diffs and tracebacks to an LLM to distinguish semantic regressions from stylistic modifications.
        </p>
      </section>

      <!-- Card: What This Does Not Do Yet -->
      <section class="card" aria-labelledby="limitations-heading">
        <h2 id="limitations-heading" class="card-title">What This Does Not Do Yet</h2>
        <ul class="steps-list" style="margin-bottom: 1rem;">
          <li>
            <strong>Rule-based explorer:</strong> The crawling engine uses deterministic form discovery and payload fuzzing, not a full autonomous web browsing agent.
          </li>
          <li>
            <strong>One small seeded app:</strong> The benchmark is evaluated against the Mini Shop Flask application with five seeded edge-case vulnerabilities.
          </li>
          <li>
            <strong>Syntactic patch check:</strong> The proposed patch validation verifies clean application and AST parse tree validity, not exhaustive regression test suites.
          </li>
        </ul>
        <div style="background-color: var(--surface-2); padding: 0.875rem 1rem; border-radius: var(--radius-sm); border: 1px solid var(--line); font-size: 0.8125rem;">
          ${icon('info')} <em>Built for transparent, reproducible evaluation with honest ground-truth scoring.</em>
        </div>
      </section>

    </div>
  `;
}
