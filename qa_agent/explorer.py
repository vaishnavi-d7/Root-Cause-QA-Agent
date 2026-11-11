"""Playwright-based autonomous QA exploration and reproduction agent."""
import json
import os
import shutil
import stat
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from playwright.sync_api import Page, Response, sync_playwright

from qa_agent.models import Finding, normalise_route
from qa_agent.payloads import llm_payloads, static_payloads

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def safe_rmtree(target_dir: Path) -> None:
    """Safely remove directory tree clearing read-only flags on Windows."""
    if not target_dir.exists():
        return

    def _clear_readonly(func, path, exc):
        try:
            os.chmod(path, stat.S_IWRITE)
        except OSError:
            pass
        func(path)

    if sys.version_info >= (3, 12):
        shutil.rmtree(target_dir, onexc=_clear_readonly)
    else:
        shutil.rmtree(target_dir, onerror=lambda f, p, e: _clear_readonly(f, p, None))


class Signals:
    """Capture console errors, uncaught exceptions, and failed network requests."""

    def __init__(self, page: Page) -> None:
        """Register listeners on the given Playwright page."""
        self.console_messages: List[str] = []
        self.page_errors: List[str] = []
        self.failed_requests: List[str] = []
        self.http_500_responses: List[Response] = []

        page.on("console", self._on_console)
        page.on("pageerror", lambda err: self.page_errors.append(str(err)))
        page.on(
            "requestfailed",
            lambda req: self.failed_requests.append(f"{req.method} {req.url}: {req.failure}"),
        )
        page.on("response", self._on_response)

    def _on_console(self, msg: Any) -> None:
        """Filter and collect console error messages."""
        text = str(msg.text)
        if msg.type == "error" and "Failed to load resource" not in text:
            self.console_messages.append(text)

    def _on_response(self, resp: Response) -> None:
        """Capture HTTP responses with 5xx status codes."""
        if resp.status >= 500:
            self.http_500_responses.append(resp)

    def clear(self) -> None:
        """Clear recorded signals before starting a new probe."""
        self.console_messages.clear()
        self.page_errors.clear()
        self.failed_requests.clear()
        self.http_500_responses.clear()


class Explorer:
    """Explores web application routes and forms to discover, de-duplicate, and reproduce bugs."""

    def __init__(
        self,
        base_url: str,
        out_dir: Path,
        use_llm: bool = False,
        max_pages: int = 25,
        on_event: Optional[Any] = None,
    ) -> None:
        """Initialize explorer with target base URL and output directory."""
        self.base_url = base_url.rstrip("/")
        self.out_dir = Path(out_dir)
        self.use_llm = use_llm
        self.max_pages = max_pages
        self.on_event = on_event
        self.screenshots_dir = self.out_dir / "screenshots"
        self.videos_dir = self.out_dir / "videos"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.videos_dir.mkdir(parents=True, exist_ok=True)

        self.findings: Dict[Tuple[str, str, str], Finding] = {}
        self.finding_counter: int = 1
        self.probe_count: int = 0

    def _advance_probe(self) -> None:
        """Increment probe count and notify callback every 5 probes."""
        self.probe_count += 1
        if self.probe_count % 5 == 0 and self.on_event:
            self.on_event({"type": "probe", "count": self.probe_count})

    def _reset_app(self) -> None:
        """POST to /__reset before every probe to ensure isolated state."""
        try:
            req = urllib.request.Request(f"{self.base_url}/__reset", method="POST", data=b"")
            with urllib.request.urlopen(req, timeout=3):
                pass
        except Exception:
            pass

    def _handle_detection(
        self,
        page: Page,
        steps: List[Dict[str, Any]],
        method: str,
        url: str,
        status: Optional[int],
        summary: str,
        kind: str,
        console: List[str],
    ) -> None:
        """Record or de-duplicate a discovered finding."""
        route = normalise_route(url)
        key = (route, kind, method)

        if key in self.findings:
            self.findings[key].occurrences += 1
            print(f"  [Duplicate] {kind} on {route} ({method}) - occurrences: {self.findings[key].occurrences}")
            return

        fid = f"F{self.finding_counter:02d}"
        self.finding_counter += 1

        screenshot_rel = f"screenshots/{fid}.png"
        screenshot_path = self.out_dir / screenshot_rel
        try:
            page.screenshot(path=str(screenshot_path))
        except Exception:
            screenshot_rel = None

        finding = Finding(
            id=fid,
            kind=kind,
            method=method,
            url=url,
            route=route,
            status=status,
            summary=summary,
            steps=list(steps),
            console=list(console),
            screenshot=screenshot_rel,
            video=None,
            reproduced=None,
            occurrences=1,
        )
        self.findings[key] = finding
        if self.on_event:
            self.on_event({"type": "finding", "finding": finding.to_dict()})
        print(f"  [Finding {fid}] {kind.upper()} on {route} ({method}) - status {status}")

    def _extract_forms(self, page: Page) -> List[Dict[str, Any]]:
        """Collect form details including actions, methods, and input fields."""
        forms_data = []
        forms = page.query_selector_all("form")
        for idx, form in enumerate(forms):
            action = form.get_attribute("action") or ""
            method = (form.get_attribute("method") or "GET").upper()
            submit_btn = form.query_selector("button[type='submit'], input[type='submit'], button")
            if submit_btn:
                btn_tag = submit_btn.evaluate("el => el.tagName.toLowerCase()")
                submit_sel = (
                    f"form >> nth={idx} >> button"
                    if btn_tag == "button"
                    else f"form >> nth={idx} >> input[type='submit']"
                )
            else:
                submit_sel = f"form >> nth={idx} >> button"

            fields = []
            for el in form.query_selector_all("input, select, textarea"):
                tag = el.evaluate("e => e.tagName.toLowerCase()")
                name = el.get_attribute("name") or ""
                if not name:
                    continue
                input_type = (el.get_attribute("type") or "text").lower() if tag == "input" else tag
                val = el.get_attribute("value") or ""
                options = []
                if tag == "select":
                    options = [
                        o.get_attribute("value") or o.inner_text().strip()
                        for o in el.query_selector_all("option")
                    ]
                fields.append(
                    {
                        "name": name,
                        "tag": tag,
                        "type": input_type,
                        "value": val,
                        "options": options,
                    }
                )
            forms_data.append(
                {
                    "index": idx,
                    "action": action,
                    "method": method,
                    "submit_selector": submit_sel,
                    "fields": fields,
                }
            )
        return forms_data

    def _field_default(self, field: Dict[str, Any]) -> str:
        """Return sensible default value for a form field."""
        tag = field.get("tag", "input")
        if tag == "select":
            opts = field.get("options", [])
            return str(opts[0]) if opts else "1"
        if field.get("type") == "number":
            return "1"
        return "test"

    def _check_signals_detection(
        self,
        page: Page,
        signals: Signals,
        steps: List[Dict[str, Any]],
        default_method: str,
        default_url: str,
    ) -> None:
        """Inspect signals and record findings if failures are detected."""
        if signals.http_500_responses:
            resp = signals.http_500_responses[-1]
            self._handle_detection(
                page=page,
                steps=steps,
                method=resp.request.method,
                url=resp.url,
                status=resp.status,
                summary=f"HTTP {resp.status} on {normalise_route(resp.url)}",
                kind="http_500",
                console=signals.console_messages,
            )
        elif signals.page_errors:
            self._handle_detection(
                page=page,
                steps=steps,
                method=default_method,
                url=page.url if page.url != "about:blank" else default_url,
                status=None,
                summary=signals.page_errors[0],
                kind="js_error",
                console=signals.console_messages,
            )
        elif signals.console_messages:
            self._handle_detection(
                page=page,
                steps=steps,
                method=default_method,
                url=page.url if page.url != "about:blank" else default_url,
                status=None,
                summary=signals.console_messages[0],
                kind="console_error",
                console=signals.console_messages,
            )
        elif signals.failed_requests:
            self._handle_detection(
                page=page,
                steps=steps,
                method=default_method,
                url=page.url if page.url != "about:blank" else default_url,
                status=None,
                summary=signals.failed_requests[0],
                kind="request_failed",
                console=signals.console_messages,
            )

    def run(self) -> List[Finding]:
        """Execute QA exploration, detection, and reproduction pipeline."""
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            signals = Signals(page)

            # 1. CRAWL (BFS)
            queue: List[str] = [f"{self.base_url}/"]
            visited_urls: Set[str] = set()
            visited_paths: List[str] = []
            collected_forms: List[Tuple[str, Dict[str, Any]]] = []

            print("\n=== Phase 1: Crawling routes ===")
            while queue and len(visited_urls) < self.max_pages:
                curr_url = queue.pop(0)
                if curr_url in visited_urls:
                    continue
                visited_urls.add(curr_url)
                visited_paths.append(urllib.parse.urlparse(curr_url).path)

                self._advance_probe()
                self._reset_app()
                signals.clear()
                steps = [{"action": "goto", "url": curr_url}]
                print(f"Probe {self.probe_count:2d}: GET {curr_url}")

                try:
                    resp = page.goto(curr_url, wait_until="load", timeout=5000)
                    if resp and resp.status >= 500:
                        self._handle_detection(
                            page=page,
                            steps=steps,
                            method=resp.request.method,
                            url=resp.url,
                            status=resp.status,
                            summary=f"HTTP {resp.status} on {normalise_route(resp.url)}",
                            kind="http_500",
                            console=signals.console_messages,
                        )
                    else:
                        self._check_signals_detection(page, signals, steps, "GET", curr_url)

                        # Discover links on HTML page
                        content_type = resp.headers.get("content-type", "") if resp else ""
                        if "html" in content_type:
                            forms = self._extract_forms(page)
                            for f in forms:
                                collected_forms.append((curr_url, f))

                            for link in page.query_selector_all("a[href]"):
                                href = link.get_attribute("href") or ""
                                if href.startswith("#") or href.startswith("mailto:") or href.startswith("javascript:"):
                                    continue
                                resolved = urllib.parse.urljoin(curr_url, href)
                                if urllib.parse.urlparse(resolved).netloc == urllib.parse.urlparse(self.base_url).netloc:
                                    if resolved not in visited_urls and resolved not in queue:
                                        queue.append(resolved)
                except Exception:
                    self._check_signals_detection(page, signals, steps, "GET", curr_url)

            # 2. MUTATE URLS
            print("\n=== Phase 2: Mutating URL segments ===")
            mutation_candidates = ["0", "-1", "999999", "abc"]
            for path in visited_paths:
                segments = path.split("/")
                for idx, seg in enumerate(segments):
                    if seg.isdigit() or (seg.startswith("-") and seg[1:].isdigit()):
                        for cand in mutation_candidates:
                            mutated_segs = list(segments)
                            mutated_segs[idx] = cand
                            mutated_path = "/".join(mutated_segs)
                            target_url = urllib.parse.urljoin(self.base_url, mutated_path)

                            self._advance_probe()
                            self._reset_app()
                            signals.clear()
                            steps = [{"action": "goto", "url": target_url}]
                            print(f"Probe {self.probe_count:2d}: GET {target_url}")

                            try:
                                resp = page.goto(target_url, wait_until="load", timeout=5000)
                                if resp and resp.status >= 500:
                                    self._handle_detection(
                                        page=page,
                                        steps=steps,
                                        method=resp.request.method,
                                        url=resp.url,
                                        status=resp.status,
                                        summary=f"HTTP {resp.status} on {normalise_route(resp.url)}",
                                        kind="http_500",
                                        console=signals.console_messages,
                                    )
                                else:
                                    self._check_signals_detection(page, signals, steps, "GET", target_url)
                            except Exception:
                                self._check_signals_detection(page, signals, steps, "GET", target_url)

            # 3. FUZZ FORMS
            print("\n=== Phase 3: Fuzzing forms ===")
            for page_url, form in collected_forms:
                form_idx = form["index"]
                submit_sel = form["submit_selector"]
                fields = form["fields"]

                # Happy path submission
                self._advance_probe()
                self._reset_app()
                signals.clear()
                happy_steps: List[Dict[str, Any]] = [{"action": "goto", "url": page_url}]
                for f in fields:
                    sel = f'form >> nth={form_idx} >> [name="{f["name"]}"]'
                    def_val = self._field_default(f)
                    if f["tag"] == "select":
                        happy_steps.append({"action": "select", "selector": sel, "value": def_val})
                    else:
                        happy_steps.append({"action": "fill", "selector": sel, "value": def_val})
                happy_steps.append({"action": "submit", "selector": submit_sel})

                print(f"Probe {self.probe_count:2d}: {form['method']} form [{form_idx}] happy path")
                try:
                    page.goto(page_url, wait_until="load", timeout=5000)
                    for s in happy_steps[1:-1]:
                        if s["action"] == "fill":
                            page.fill(s["selector"], s["value"])
                        elif s["action"] == "select":
                            page.select_option(s["selector"], s["value"])
                    page.click(submit_sel)
                    page.wait_for_timeout(300)
                    self._check_signals_detection(page, signals, happy_steps, form["method"], page_url)
                except Exception:
                    self._check_signals_detection(page, signals, happy_steps, form["method"], page_url)

                # Field-by-field payload fuzzing
                llm_dict = llm_payloads(form) if self.use_llm else {}
                for field in fields:
                    if field.get("tag") == "select":
                        continue
                    if field.get("type") in ("hidden", "submit", "button", "checkbox", "radio", "file"):
                        continue

                    payloads = static_payloads(field)
                    if self.use_llm and field["name"] in llm_dict:
                        payloads = payloads + llm_dict[field["name"]]

                    for payload in payloads:
                        self._advance_probe()
                        self._reset_app()
                        signals.clear()

                        probe_steps: List[Dict[str, Any]] = [{"action": "goto", "url": page_url}]
                        for f in fields:
                            sel = f'form >> nth={form_idx} >> [name="{f["name"]}"]'
                            val = payload if f["name"] == field["name"] else self._field_default(f)
                            if f["tag"] == "select":
                                probe_steps.append({"action": "select", "selector": sel, "value": val})
                            else:
                                probe_steps.append({"action": "fill", "selector": sel, "value": val})
                        probe_steps.append({"action": "submit", "selector": submit_sel})

                        display_val = payload if len(payload) <= 25 else f"{payload[:22]}..."
                        print(f"Probe {self.probe_count:2d}: {form['method']} form [{form_idx}] field '{field['name']}' = {repr(display_val)}")

                        try:
                            page.goto(page_url, wait_until="load", timeout=5000)
                            for s in probe_steps[1:-1]:
                                if s["action"] == "fill":
                                    page.fill(s["selector"], s["value"])
                                elif s["action"] == "select":
                                    page.select_option(s["selector"], s["value"])
                            page.click(submit_sel)
                            page.wait_for_timeout(300)
                            self._check_signals_detection(page, signals, probe_steps, form["method"], page_url)
                        except Exception:
                            # Skip probes that make Playwright throw silently
                            pass

            context.close()

            # 8. REPRODUCE
            print("\n=== Phase 4: Reproducing findings on video ===")
            if self.on_event:
                self.on_event({"type": "stage", "stage": "reproduce", "status": "started"})
            for finding in self.findings.values():
                self._reset_app()
                temp_rec_dir = Path(tempfile.mkdtemp(prefix=f"rec_{finding.id}_", dir=str(self.out_dir)))
                rep_ctx = browser.new_context(
                    record_video_dir=str(temp_rec_dir),
                    record_video_size={"width": 900, "height": 600},
                )
                rep_page = rep_ctx.new_page()
                rep_signals = Signals(rep_page)

                try:
                    for step in finding.steps:
                        action = step.get("action")
                        if action == "goto":
                            rep_page.goto(step["url"], wait_until="load", timeout=5000)
                        elif action == "fill":
                            rep_page.fill(step["selector"], step["value"])
                        elif action == "select":
                            rep_page.select_option(step["selector"], step["value"])
                        elif action == "submit":
                            rep_page.click(step["selector"])
                            rep_page.wait_for_timeout(300)
                except Exception:
                    pass

                rep_page.wait_for_timeout(1200)

                reproduced = False
                if finding.kind == "http_500" and rep_signals.http_500_responses:
                    reproduced = True
                elif finding.kind == "js_error" and rep_signals.page_errors:
                    reproduced = True
                elif finding.kind == "console_error" and rep_signals.console_messages:
                    reproduced = True
                elif finding.kind == "request_failed" and rep_signals.failed_requests:
                    reproduced = True

                video_path = rep_page.video.path() if rep_page.video else None
                rep_ctx.close()

                target_video_rel = f"videos/{finding.id}.webm"
                target_video_path = self.out_dir / target_video_rel
                if video_path and os.path.exists(video_path):
                    if target_video_path.exists():
                        target_video_path.unlink()
                    shutil.move(video_path, target_video_path)
                    finding.video = target_video_rel

                finding.reproduced = reproduced
                safe_rmtree(temp_rec_dir)

                print(
                    f"Reproduced {finding.id} ({finding.route} - {finding.kind}): "
                    f"{reproduced} [video: {finding.video}]"
                )

            if self.on_event:
                self.on_event({"type": "stage", "stage": "reproduce", "status": "done"})

            browser.close()

        # 9. Write findings.json
        findings_json_path = self.out_dir / "findings.json"
        findings_data = [f.to_dict() for f in self.findings.values()]
        findings_json_path.write_text(json.dumps(findings_data, indent=2), encoding="utf-8")

        print("\n=== Exploration Summary ===")
        print(f"Total Probes Executed: {self.probe_count}")
        print(f"Total Unique Findings: {len(self.findings)}")
        for f in self.findings.values():
            print(
                f"- [{f.id}] {f.kind} on {f.route} [{f.method}] | "
                f"Reproduced: {f.reproduced} | Occurrences: {f.occurrences} | Video: {f.video}"
            )

        return list(self.findings.values())
