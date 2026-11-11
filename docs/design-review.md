# Visual & Accessibility Design Review: RootCause-QA

**Reviewer**: Antigravity Senior Design & Accessibility Reviewer  
**Date**: October 29, 2026  
**Scope**: `web/` static dashboard, CSS tokens, component architecture, and responsive viewports (1440px, 1024px, 768px, 390px).  
**Design Persona**: "Editorial lab notebook" &mdash; tactile paper backgrounds, hairline borders, asymmetric typography, rigorous ground-truth data, and zero AI gimmicks.

---

## 1. Color Audit & WCAG Contrast Evaluation

### 1.1 Token Purity & Color Extraction
All colors used across [`web/css/tokens.css`](file:///c:/Users/vaishnavi/Desktop/rootcause-qa-ag/web/css/tokens.css), [`web/css/base.css`](file:///c:/Users/vaishnavi/Desktop/rootcause-qa-ag/web/css/base.css), [`web/css/components.css`](file:///c:/Users/vaishnavi/Desktop/rootcause-qa-ag/web/css/components.css), and [`web/css/pages.css`](file:///c:/Users/vaishnavi/Desktop/rootcause-qa-ag/web/css/pages.css) have been audited:
- **Zero Dark Backgrounds**: Background colors are strictly `--paper` (`#F7F3EC`), `--surface` (`#FFFDF9`), or `--surface-2` (`#EFE9DF`).
- **Zero Gradients**: No `linear-gradient`, `radial-gradient`, or gradient text anywhere in stylesheets.
- **Zero `#000` / Pure Black**: Typography uses `--ink` (`#22262B`).
- **Zero `#fff` as a Background**: All surfaces use the warm light theme `--surface` (`#FFFDF9`).
- **Zero Ad-hoc Hex Codes**: Every color rule references a defined CSS token or documented semantic variable.

### 1.2 WCAG Contrast Calculation Table
Evaluated under **WCAG 2.1 Level AA** standards ($L_1 + 0.05) / (L_2 + 0.05) \ge 4.5:1$ for standard text:

| Text / Element | Foreground | Background | Relative Contrast | WCAG AA Status | Notes / Adjustments |
| :--- | :--- | :--- | :---: | :---: | :--- |
| **Ink on Paper** | `#22262B` | `#F7F3EC` | **13.76:1** | **PASS** | Primary body text on site background |
| **Ink on Surface** | `#22262B` | `#FFFDF9` | **14.98:1** | **PASS** | Primary card headings and body |
| **Ink on Surface-2** | `#22262B` | `#EFE9DF` | **12.60:1** | **PASS** | Code panels, tables, event log |
| **Ink-Muted on Paper** | `#5E6670` | `#F7F3EC` | **5.26:1** | **PASS** | Section labels, footer subtext |
| **Ink-Muted on Surface** | `#5E6670` | `#FFFDF9` | **5.73:1** | **PASS** | Card subtitles, metadata items |
| **Ink-Muted on Surface-2** | `#5E6670` | `#EFE9DF` | **4.82:1** | **PASS** | Table headers, line numbers |
| **Accent on Surface** | `#9E4527` | `#FFFDF9` | **6.20:1** | **PASS** | Links, interactive highlights |
| **Accent on Paper** | `#9E4527` | `#F7F3EC` | **5.69:1** | **PASS** | Active navigation link underline |
| **White on Accent** | `#FFFDF9` | `#9E4527` | **6.20:1** | **PASS** | Primary button text |
| **Accent on Accent Tint** | `#9E4527` | `#F5EAE4` | **5.33:1** | **PASS** | Running status pill (adjusted from 3.87:1) |
| **Good on Surface** | `#276A42` | `#FFFDF9` | **6.41:1** | **PASS** | Done status, verified commit checks |
| **Good on Paper** | `#276A42` | `#F7F3EC` | **5.88:1** | **PASS** | Stepper completed lines |
| **Good on Good Tint** | `#276A42` | `#E9EEE6` | **5.53:1** | **PASS** | Done status pill (adjusted from 4.22:1) |
| **Warn on Surface** | `#8A5A0B` | `#FFFDF9` | **5.83:1** | **PASS** | Warning icons, caution headers |
| **Warn on Paper** | `#8A5A0B` | `#F7F3EC` | **5.35:1** | **PASS** | Notice banners |
| **Warn on Warn Tint** | `#8A5A0B` | `#F3ECE1` | **5.04:1** | **PASS** | Invalid pill, key notice background |
| **Bad on Surface** | `#B3372F` | `#FFFDF9` | **5.90:1** | **PASS** | Error headers, failure indicators |
| **Bad on Paper** | `#B3372F` | `#F7F3EC` | **5.42:1** | **PASS** | Error alerts on page |
| **Bad on Bad Tint** | `#B3372F` | `#F7E9E4` | **5.06:1** | **PASS** | Failed status pill, blame wrong chip |
| **Ink on Mark Highlight** | `#22262B` | `#F2D27A` | **10.34:1** | **PASS** | True culprit chip, blame-trap callout |

*Every foreground/background pairing in use meets or exceeds the required 4.5:1 ratio.*

---

## 2. Concrete Findings & Action Items

### Finding 1: Running Status Pill Contrast Below 4.5:1
- **Severity**: High (Accessibility & WCAG Failure)
- **Before**: `--accent` (`#B5502E`) against `--accent-soft` (`#F3DDD1`) achieved only a 3.87:1 contrast ratio, failing WCAG AA standard text requirements.
- **Fix**: Adjusted `--accent` shade to `#9E4527` and derived `--accent-soft` as a precise 10% tint on surface (`#F5EAE4`), boosting relative contrast to **5.33:1**.
- **Status**: **FIXED**

### Finding 2: Good Green Text on Pill Tint Below 4.5:1
- **Severity**: High (Accessibility & WCAG Failure)
- **Before**: `--good` (`#2F7D4F`) against its 12% tint achieved a 4.22:1 contrast ratio, falling short of the 4.5:1 threshold.
- **Fix**: Deepened `--good` to `#276A42` and tuned `--good-tint` to a 10% alpha blend (`#E9EEE6`), reaching **5.53:1** contrast on tint and **6.41:1** on surface.
- **Status**: **FIXED**

### Finding 3: Layout Max Width Exceeded 1120px Specification
- **Severity**: Medium (Design System Inconsistency)
- **Before**: Layout containers (`.top-bar-inner`, `main#app`, `.site-footer-inner`) used `max-width: 1240px`, causing wide screens to have over-extended lines and loose whitespace.
- **Fix**: Standardized `--max-width: 1120px;` across all layout containers, locking tables, scorecard boxes, and forms into a cohesive editorial grid.
- **Status**: **FIXED**

### Finding 4: Ad-Hoc Hex Colors in CSS Components
- **Severity**: Medium (Maintainability & Design Token Violation)
- **Before**: `components.css` contained hardcoded hexes (`#D3C7B2`, `#E8C5B3`, `#9E4527`, `#D8B750`, `#553A00`) and arbitrary rgba values outside token definitions.
- **Fix**: Established first-class tokens in `tokens.css` (`--line-hover`, `--accent-hover`, `--good-tint`, `--good-border`, `--bad-tint`, `--bad-border`, `--warn-tint`, `--warn-border`, `--mark-border`, `--mark-text`, `--mark-tint`) and refactored all CSS rules to use tokens exclusively.
- **Status**: **FIXED**

### Finding 5: Inconsistent Typography Scale
- **Severity**: Medium (Typographic Hierarchy)
- **Before**: Arbitrary sizes (44px, 17px, 13px) were scattered across headers and badges.
- **Fix**: Enforced a strict 6-step scale: 12px (`--text-xs`), 14px (`--text-sm`), 16px (`--text-base`), 20px (`--text-lg`), 28px (`--text-xl`), and 40px (`--text-2xl`). Set stat counters to 40px Fraunces 600 with tabular numbers.
- **Status**: **FIXED**

### Finding 6: Floating Drop Shadow on Card Hover ("Generic AI Look")
- **Severity**: Medium (Design Aesthetic Integrity)
- **Before**: `.finding-card:hover` applied `box-shadow: 0 4px 12px rgba(34, 38, 43, 0.08)`, introducing a floating SaaS card aesthetic.
- **Fix**: Removed the floating box shadow. Used flat tactile hairline border transitions (`border-color: var(--accent);`) consistent with the physical lab notebook aesthetic.
- **Status**: **FIXED**

### Finding 7: Asymmetric Hero Section Layout
- **Severity**: Medium (Layout Composition)
- **Before**: The hero section on `#/` had uniform centered-like layout without editorial hierarchy.
- **Fix**: Refactored the hero into an asymmetric editorial layout: structured left column with high-contrast headline, muted explanation, and primary launch button aligned to the baseline.
- **Status**: **FIXED**

### Finding 8: Disabled LLM State Guidance on New Run Page
- **Severity**: High (User Experience & Feedback)
- **Before**: When no LLM provider had an environment key, cards displayed a muted badge but lacked guidance on how to proceed.
- **Fix**: Introduced a dedicated informative notice banner (`.callout-blame-trap` style in warning tint) explaining that LLM analysis requires entering a temporary API key below, while Baseline mode runs deterministically without any key.
- **Status**: **FIXED**

### Finding 9: Missing Scorecard Attribution for Invalid LLM Runs
- **Severity**: High (Data Integrity & Score Accuracy)
- **Before**: If an LLM run experienced a model failure, `server/runs.py` had a missing import for `Finding` that silently caused benchmark scoring to fail, while the frontend risked displaying `0/5`.
- **Fix**: Added `from qa_agent.models import Finding` to `server/runs.py`, ensured `score()` sets `"status": "invalid"` with the exact error message, and updated `run.js` to explicitly display `"Invalid"` with the model error subtext.
- **Status**: **FIXED**

### Finding 10: Mobile Touch Targets & Edge Gutters on 390px
- **Severity**: Medium (Mobile Responsiveness)
- **Before**: At 390px, table wrappers and stepper containers risked touching screen boundaries.
- **Fix**: Enforced 16px (`var(--space-2)`) minimum gutters on `main#app`, minimum 44px touch targets on buttons, and smooth touch-scrolling (`-webkit-overflow-scrolling: touch`) on wide tables and stepper bars.
- **Status**: **FIXED**

### Finding 11: Comprehensive Motion Preference Support
- **Severity**: Medium (Accessibility & Motion Sensitivity)
- **Before**: Only the running status pill paused under `prefers-reduced-motion: reduce`, while loading skeletons and transitions continued animating.
- **Fix**: Added a universal `@media (prefers-reduced-motion: reduce)` rule in `base.css` that disables all animations, infinite pulses, and transitions across the entire DOM.
- **Status**: **FIXED**

### Finding 12: ARIA Tablist & Breadcrumb Navigation Landmarks
- **Severity**: Low (Accessibility Semantics)
- **Before**: Tabs lacked explicit `role="tablist"` / `role="tab"` bindings, and breadcrumb trails lacked semantic nav wrappers.
- **Fix**: Updated tab navigation with `role="tablist"`, `role="tab"`, `aria-selected`, and `aria-controls`, and wrapped breadcrumbs in `<nav aria-label="Breadcrumb">`.
- **Status**: **FIXED**

---

## 3. Screenshot Catalog (Before vs After)

Screenshots captured across **1440px**, **1024px**, **768px**, and **390px** widths for all 13 application states (52 before, 52 after = 104 total images):

### 3.1 State Inventory
1. **Runs (Populated)**: [`docs/screenshots/after/runs_populated_1440px.png`](file:///c:/Users/vaishnavi/Desktop/rootcause-qa-ag/docs/screenshots/after/runs_populated_1440px.png), [`runs_populated_390px.png`](file:///c:/Users/vaishnavi/Desktop/rootcause-qa-ag/docs/screenshots/after/runs_populated_390px.png)
2. **Runs (Empty)**: [`docs/screenshots/after/runs_empty_1440px.png`](file:///c:/Users/vaishnavi/Desktop/rootcause-qa-ag/docs/screenshots/after/runs_empty_1440px.png), [`runs_empty_390px.png`](file:///c:/Users/vaishnavi/Desktop/rootcause-qa-ag/docs/screenshots/after/runs_empty_390px.png)
3. **New Run (LLM Available)**: [`docs/screenshots/after/new_run_llm_available_1440px.png`](file:///c:/Users/vaishnavi/Desktop/rootcause-qa-ag/docs/screenshots/after/new_run_llm_available_1440px.png)
4. **New Run (LLM Unavailable)**: [`docs/screenshots/after/new_run_llm_unavailable_1440px.png`](file:///c:/Users/vaishnavi/Desktop/rootcause-qa-ag/docs/screenshots/after/new_run_llm_unavailable_1440px.png)
5. **Run Completed (Done)**: [`docs/screenshots/after/run_done_1440px.png`](file:///c:/Users/vaishnavi/Desktop/rootcause-qa-ag/docs/screenshots/after/run_done_1440px.png)
6. **Run In Progress (Running)**: [`docs/screenshots/after/run_running_1440px.png`](file:///c:/Users/vaishnavi/Desktop/rootcause-qa-ag/docs/screenshots/after/run_running_1440px.png)
7. **Run Invalid LLM**: [`docs/screenshots/after/run_invalid_llm_1440px.png`](file:///c:/Users/vaishnavi/Desktop/rootcause-qa-ag/docs/screenshots/after/run_invalid_llm_1440px.png)
8. **Finding B4 (Blame Trap)**: [`docs/screenshots/after/finding_b4_1440px.png`](file:///c:/Users/vaishnavi/Desktop/rootcause-qa-ag/docs/screenshots/after/finding_b4_1440px.png)
9. **Finding Normal Bug**: [`docs/screenshots/after/finding_normal_1440px.png`](file:///c:/Users/vaishnavi/Desktop/rootcause-qa-ag/docs/screenshots/after/finding_normal_1440px.png)
10. **Benchmark Tab**: [`docs/screenshots/after/benchmark_tab_1440px.png`](file:///c:/Users/vaishnavi/Desktop/rootcause-qa-ag/docs/screenshots/after/benchmark_tab_1440px.png)
11. **Report Tab**: [`docs/screenshots/after/report_tab_1440px.png`](file:///c:/Users/vaishnavi/Desktop/rootcause-qa-ag/docs/screenshots/after/report_tab_1440px.png)
12. **About / How It Works**: [`docs/screenshots/after/about_1440px.png`](file:///c:/Users/vaishnavi/Desktop/rootcause-qa-ag/docs/screenshots/after/about_1440px.png)
13. **API Error State**: [`docs/screenshots/after/error_state_1440px.png`](file:///c:/Users/vaishnavi/Desktop/rootcause-qa-ag/docs/screenshots/after/error_state_1440px.png)

---

## 4. Verification Check Results

```text
1. Banned Pattern Scan:
   - prefers-color-scheme : 0 occurrences
   - gradient             : 0 occurrences
   - #000                 : 0 occurrences
   - #fff as background   : 0 occurrences
   - "dark"               : 0 occurrences

2. Contrast Ratios:
   - Lowest ratio measured : 4.82:1 (ink-muted on surface-2)
   - Highest ratio measured: 14.98:1 (ink on surface)
   - Overall Compliance   : 100% WCAG 2.1 AA PASS (all >= 4.5:1)

3. Visual Layout Quality:
   - Scale: Strict 8px spacing grid (8, 16, 24, 32, 40, 48px)
   - Max-Width: Strict 1120px
   - Viewport Edge Defense: 16px minimum gutters at 390px
   - Typeface Discipline: Fraunces on titles/stats, Public Sans for UI, IBM Plex Mono for code
```
