"""RootCause-QA end-to-end autonomous execution pipeline and CLI."""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent

import llm_client
from benchmark.score import score
from qa_agent.explorer import Explorer, safe_rmtree
from qa_agent.models import Finding
from rca_agent.analyzer import RCAResult, analyze
from rca_agent.log_parser import parse_server_log
from rca_agent.report import render_report


@dataclass
class PipelineConfig:
    """Configuration options for a pipeline run."""

    port: int = 5055
    out: str = "artifacts"
    reseed: bool = False
    llm_payloads: bool = False
    provider: Optional[str] = None
    rca: str = "auto"


@dataclass
class RunResult:
    """Output artifacts and summary metrics from a completed pipeline run."""

    findings: List[Finding]
    results: Dict[str, List[RCAResult]]
    benchmark: Dict[str, Any]
    out_dir: Path


def wait_for_server(url: str, timeout_seconds: float = 15.0) -> bool:
    """Poll URL until server responds or timeout is exceeded."""
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        try:
            with urllib.request.urlopen(url, timeout=1.0):
                return True
        except Exception:
            time.sleep(0.25)
    return False


def run(
    config: PipelineConfig,
    on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> RunResult:
    """Execute end-to-end RootCause-QA pipeline: seed, server, explore, rca, report, benchmark."""
    def emit_stage(stage_name: str, stage_status: str) -> None:
        if on_event:
            on_event({"type": "stage", "stage": stage_name, "status": stage_status})

    # 1. Resolve LLM provider and analysis modes
    if config.provider:
        os.environ["LLM_PROVIDER"] = config.provider

    rca_choice = config.rca.lower()
    if rca_choice == "auto":
        modes = ["baseline", "llm"] if llm_client.available() else ["baseline"]
    elif rca_choice == "both":
        if not llm_client.available():
            sys.stderr.write(llm_client.missing_hint() + "\n")
            sys.exit(1)
        modes = ["baseline", "llm"]
    elif rca_choice == "llm":
        if not llm_client.available():
            sys.stderr.write(llm_client.missing_hint() + "\n")
            sys.exit(1)
        modes = ["llm"]
    elif rca_choice == "baseline":
        modes = ["baseline"]
    else:
        raise ValueError(f"Invalid --rca option: {config.rca}")

    # 2. Recreate output directory
    out_dir = Path(config.out).resolve()
    if out_dir.exists():
        safe_rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "videos").mkdir(parents=True, exist_ok=True)
    (out_dir / "screenshots").mkdir(parents=True, exist_ok=True)

    repo_dir = ROOT_DIR / "testapp" / "repo"
    gt_file = ROOT_DIR / "testapp" / "ground_truth.json"

    # 3. Seed repository if requested or missing
    if config.reseed or not repo_dir.exists() or not gt_file.exists():
        emit_stage("seed", "started")
        try:
            from testapp.seed_history import seed_history

            seed_history()
            emit_stage("seed", "done")
        except Exception:
            emit_stage("seed", "failed")
            raise

    # 4. Start test application server
    emit_stage("server", "started")
    server_log_path = out_dir / "server.log"
    log_handle = open(server_log_path, "w", encoding="utf-8", errors="replace")
    server_env = os.environ.copy()
    server_env["PORT"] = str(config.port)
    server_env["PYTHONUTF8"] = "1"
    server_env["PYTHONIOENCODING"] = "utf-8"

    server_proc = subprocess.Popen(
        [sys.executable, "-u", "app.py"],
        cwd=str(repo_dir),
        env=server_env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )

    app_base_url = f"http://127.0.0.1:{config.port}"
    try:
        if not wait_for_server(f"{app_base_url}/", timeout_seconds=15.0):
            emit_stage("server", "failed")
            raise RuntimeError(f"Test application failed to respond on {app_base_url} within 15 seconds")
        emit_stage("server", "done")

        # 5. Run Explorer
        emit_stage("explore", "started")
        explorer = Explorer(
            app_base_url,
            out_dir=out_dir,
            use_llm=config.llm_payloads,
            on_event=on_event,
        )
        findings = explorer.run()
        emit_stage("explore", "done")

        # Allow final log writes to settle
        time.sleep(0.5)

    finally:
        # Always terminate the server process
        server_proc.terminate()
        server_proc.wait()
        log_handle.close()

    # 6. Parse server logs for tracebacks
    log_content = server_log_path.read_text(encoding="utf-8", errors="replace")
    traces = parse_server_log(log_content)

    # 7. Run root cause analysis per finding and mode
    emit_stage("rca", "started")
    results_by_mode: Dict[str, List[RCAResult]] = {m: [] for m in modes}

    for mode in modes:
        for finding in findings:
            if on_event:
                on_event({"type": "rca", "finding_id": finding.id, "mode": mode})
            rca_res = analyze(finding, repo_dir, traces, mode=mode)
            results_by_mode[mode].append(rca_res)

        rca_json_file = out_dir / f"rca_{mode}.json"
        rca_data = [r.to_dict() for r in results_by_mode[mode]]
        rca_json_file.write_text(json.dumps(rca_data, indent=2), encoding="utf-8")

    emit_stage("rca", "done")

    # 8. Render markdown report
    emit_stage("report", "started")
    report_md = render_report(findings, results_by_mode)
    (out_dir / "report.md").write_text(report_md, encoding="utf-8")
    emit_stage("report", "done")

    # 9. Benchmark against ground truth
    emit_stage("benchmark", "started")
    ground_truth = json.loads(gt_file.read_text(encoding="utf-8"))
    summary, benchmark_md = score(findings, results_by_mode, ground_truth)
    (out_dir / "benchmark.md").write_text(benchmark_md, encoding="utf-8")
    emit_stage("benchmark", "done")

    print("\n" + benchmark_md)

    return RunResult(
        findings=findings,
        results=results_by_mode,
        benchmark=summary,
        out_dir=out_dir,
    )


def main() -> None:
    """CLI entry point for running the RootCause-QA pipeline."""
    parser = argparse.ArgumentParser(description="RootCause-QA Pipeline Runner")
    parser.add_argument("--port", type=int, default=5055, help="Port to run test application on")
    parser.add_argument("--out", type=str, default="artifacts", help="Output directory for artifacts")
    parser.add_argument("--reseed", action="store_true", help="Re-generate seeded git history before running")
    parser.add_argument("--llm-payloads", action="store_true", help="Use LLM to generate adversarial form payloads")
    parser.add_argument(
        "--provider",
        choices=["anthropic", "gemini", "groq", "openrouter", "ollama"],
        help="LLM provider preset",
    )
    parser.add_argument(
        "--rca",
        choices=["auto", "baseline", "llm", "both"],
        default="auto",
        help="Root-cause analysis mode (default: auto)",
    )

    args = parser.parse_args()
    config = PipelineConfig(
        port=args.port,
        out=args.out,
        reseed=args.reseed,
        llm_payloads=args.llm_payloads,
        provider=args.provider,
        rca=args.rca,
    )
    run(config)


if __name__ == "__main__":
    main()
