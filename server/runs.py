"""Run storage, lifecycle management, and background pipeline execution."""
import asyncio
import json
import os
import secrets
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT_DIR / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)

import llm_client
from qa_agent.explorer import safe_rmtree
from qa_agent.models import Finding
from run_pipeline import PipelineConfig, run as run_pipeline

_active_run_id: Optional[str] = None
_active_lock = threading.Lock()
_live_listeners: Dict[str, List[Tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = {}


def generate_run_id() -> str:
    """Generate unique run identifier like 20261022-153045-ab12."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    rand_suffix = secrets.token_hex(2)
    return f"{timestamp}-{rand_suffix}"


def get_active_run_id() -> Optional[str]:
    """Return currently active run ID if one is executing."""
    with _active_lock:
        return _active_run_id


def _append_event(run_dir: Path, run_id: str, event: Dict[str, Any]) -> None:
    """Persist event to events.jsonl with timestamp and broadcast to active SSE listeners."""
    event_with_ts = dict(event)
    if "timestamp" not in event_with_ts:
        event_with_ts["timestamp"] = datetime.now(timezone.utc).isoformat()

    events_file = run_dir / "events.jsonl"
    with open(events_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(event_with_ts) + "\n")

    # Broadcast to live SSE queues
    with _active_lock:
        listeners = list(_live_listeners.get(run_id, []))
    for loop, q in listeners:
        try:
            loop.call_soon_threadsafe(q.put_nowait, event_with_ts)
        except Exception:
            pass


def _background_worker(
    run_id: str,
    run_dir: Path,
    rca: str,
    provider: Optional[str],
    llm_payloads: bool,
    reseed: bool,
    api_key: Optional[str],
) -> None:
    """Execute pipeline in a background thread with isolated credentials."""
    global _active_run_id

    meta_file = run_dir / "meta.json"
    with open(meta_file, "r", encoding="utf-8") as f:
        meta = json.load(f)

    meta["status"] = "running"
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    # Temporary environment injection for api_key
    chosen_provider = provider or llm_client.provider()
    key_env = llm_client.PRESETS.get(chosen_provider, {}).get("key_env") if chosen_provider else None
    old_key_val = os.environ.get(key_env) if key_env else None

    if api_key and key_env:
        os.environ[key_env] = api_key

    error_text: Optional[str] = None
    status = "done"

    def pipeline_event_handler(evt: Dict[str, Any]) -> None:
        _append_event(run_dir, run_id, evt)

    try:
        config = PipelineConfig(
            port=5055,
            out=str(run_dir),
            reseed=reseed,
            llm_payloads=llm_payloads,
            provider=provider,
            rca=rca,
        )
        run_pipeline(config, on_event=pipeline_event_handler)
    except Exception as exc:
        status = "failed"
        error_text = str(exc)
        pipeline_event_handler({"type": "stage", "stage": "pipeline", "status": "failed", "error": str(exc)})
    finally:
        # Restore environment variables
        if api_key and key_env:
            if old_key_val is not None:
                os.environ[key_env] = old_key_val
            else:
                os.environ.pop(key_env, None)

        meta["status"] = status
        meta["finished_at"] = datetime.now(timezone.utc).isoformat()
        meta["error"] = error_text

        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        _append_event(run_dir, run_id, {"type": "end", "status": status})

        with _active_lock:
            _active_run_id = None


def create_run(
    rca: str = "auto",
    provider: Optional[str] = None,
    llm_payloads: bool = False,
    reseed: bool = False,
    api_key: Optional[str] = None,
) -> Optional[str]:
    """Initialize a new run and start background execution if no run is currently active."""
    global _active_run_id

    with _active_lock:
        if _active_run_id is not None:
            return None

        run_id = generate_run_id()
        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "videos").mkdir(parents=True, exist_ok=True)
        (run_dir / "screenshots").mkdir(parents=True, exist_ok=True)

        # Describe LLM without secrets
        prev_provider = os.environ.get("LLM_PROVIDER")
        if provider:
            os.environ["LLM_PROVIDER"] = provider
        llm_desc = llm_client.describe()
        if provider:
            if prev_provider:
                os.environ["LLM_PROVIDER"] = prev_provider
            else:
                os.environ.pop("LLM_PROVIDER", None)

        # Meta record without secrets
        meta = {
            "id": run_id,
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "config": {
                "rca": rca,
                "provider": provider,
                "llm_payloads": llm_payloads,
                "reseed": reseed,
            },
            "llm_description": llm_desc,
            "error": None,
        }

        with open(run_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        # Initialize empty events.jsonl
        (run_dir / "events.jsonl").write_text("", encoding="utf-8")

        _active_run_id = run_id

    worker_thread = threading.Thread(
        target=_background_worker,
        args=(run_id, run_dir, rca, provider, llm_payloads, reseed, api_key),
        daemon=True,
    )
    worker_thread.start()
    return run_id


def list_runs() -> List[Dict[str, Any]]:
    """Return summary list of all runs on disk, sorted newest first."""
    summaries = []
    if not RUNS_DIR.exists():
        return summaries

    for item in RUNS_DIR.iterdir():
        if item.is_dir() and (item / "meta.json").exists():
            try:
                meta = json.loads((item / "meta.json").read_text(encoding="utf-8"))
                findings_file = item / "findings.json"
                findings = (
                    json.loads(findings_file.read_text(encoding="utf-8"))
                    if findings_file.exists()
                    else []
                )

                correct_by_mode: Dict[str, int] = {}
                for rca_file in item.glob("rca_*.json"):
                    mode_name = rca_file.stem.replace("rca_", "")
                    try:
                        rca_list = json.loads(rca_file.read_text(encoding="utf-8"))
                        # Count correct from rca results if possible
                        correct_by_mode[mode_name] = len(rca_list)
                    except Exception:
                        pass

                summaries.append(
                    {
                        "id": meta.get("id", item.name),
                        "status": meta.get("status", "unknown"),
                        "created_at": meta.get("created_at"),
                        "rca": meta.get("config", {}).get("rca", "unknown"),
                        "llm_description": meta.get("llm_description", ""),
                        "counts": {
                            "findings": len(findings),
                            "reproduced": sum(1 for f in findings if f.get("reproduced")),
                            "correct_by_mode": correct_by_mode,
                        },
                    }
                )
            except Exception:
                continue

    summaries.sort(key=lambda s: s.get("created_at") or "", reverse=True)
    return summaries


def get_run_details(run_id: str) -> Optional[Dict[str, Any]]:
    """Return full details, findings, RCA, reports, and benchmark for a specific run."""
    run_dir = RUNS_DIR / run_id
    meta_file = run_dir / "meta.json"
    if not meta_file.exists():
        return None

    meta = json.loads(meta_file.read_text(encoding="utf-8"))

    findings_file = run_dir / "findings.json"
    findings = json.loads(findings_file.read_text(encoding="utf-8")) if findings_file.exists() else []

    rca_results: Dict[str, Any] = {}
    for rca_file in run_dir.glob("rca_*.json"):
        mode = rca_file.stem.replace("rca_", "")
        try:
            rca_results[mode] = json.loads(rca_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    report_file = run_dir / "report.md"
    report_md = report_file.read_text(encoding="utf-8") if report_file.exists() else ""

    benchmark_file = run_dir / "benchmark.md"
    benchmark_md = benchmark_file.read_text(encoding="utf-8") if benchmark_file.exists() else ""

    gt_file = ROOT_DIR / "testapp" / "ground_truth.json"
    benchmark_summary: Dict[str, Any] = {}
    if gt_file.exists() and findings:
        try:
            from benchmark.score import score

            gt = json.loads(gt_file.read_text(encoding="utf-8"))
            benchmark_summary, _ = score(
                [Finding(**f) for f in findings],
                rca_results,
                gt,
            )
        except Exception:
            pass

    return {
        "meta": meta,
        "findings": findings,
        "rca": rca_results,
        "benchmark": benchmark_summary,
        "report_md": report_md,
        "benchmark_md": benchmark_md,
    }


def delete_run(run_id: str) -> bool:
    """Delete run folder on disk using Windows-safe rmtree."""
    with _active_lock:
        if run_id == _active_run_id:
            return False

    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        return False

    safe_rmtree(run_dir)
    return True


def register_listener(run_id: str, loop: asyncio.AbstractEventLoop, q: asyncio.Queue) -> None:
    """Register an SSE listener queue for a run."""
    with _active_lock:
        if run_id not in _live_listeners:
            _live_listeners[run_id] = []
        _live_listeners[run_id].append((loop, q))


def unregister_listener(run_id: str, q: asyncio.Queue) -> None:
    """Unregister an SSE listener queue."""
    with _active_lock:
        if run_id in _live_listeners:
            _live_listeners[run_id] = [item for item in _live_listeners[run_id] if item[1] is not q]
            if not _live_listeners[run_id]:
                _live_listeners.pop(run_id, None)


def get_timeline(run_id: str, fid: str) -> List[Dict[str, Any]]:
    """Return commits that modified the failing line for finding fid, newest first."""
    run_dir = RUNS_DIR / run_id
    findings_file = run_dir / "findings.json"
    if not findings_file.exists():
        return []

    try:
        findings = json.loads(findings_file.read_text(encoding="utf-8"))
    except Exception:
        return []

    finding = next((f for f in findings if f["id"] == fid), None)
    if not finding:
        return []

    location = None
    blamed_sha = None
    rca_base_file = run_dir / "rca_baseline.json"
    if rca_base_file.exists():
        try:
            rca_base_list = json.loads(rca_base_file.read_text(encoding="utf-8"))
            r_base = next((r for r in rca_base_list if r["finding_id"] == fid), None)
            if r_base:
                location = r_base.get("location")
                if r_base.get("blame"):
                    blamed_sha = r_base["blame"].get("sha")
        except Exception:
            pass

    llm_sha = None
    rca_llm_file = run_dir / "rca_llm.json"
    if rca_llm_file.exists():
        try:
            rca_llm_list = json.loads(rca_llm_file.read_text(encoding="utf-8"))
            r_llm = next((r for r in rca_llm_list if r["finding_id"] == fid), None)
            if r_llm:
                llm_sha = r_llm.get("suspected_commit")
        except Exception:
            pass

    gt_file = ROOT_DIR / "testapp" / "ground_truth.json"
    truth_sha = None
    if gt_file.exists():
        try:
            gt_list = json.loads(gt_file.read_text(encoding="utf-8"))
            gt_item = next((item for item in gt_list if item["route"] == finding["route"]), None)
            if gt_item:
                truth_sha = gt_item.get("culprit_commit")
        except Exception:
            pass

    if not location or ":" not in location:
        return []

    file_rel, line_str = location.split(":")
    line_num = int(line_str)
    repo_dir = ROOT_DIR / "testapp" / "repo"

    cmd = [
        "git",
        "-C",
        str(repo_dir),
        "log",
        f"-L{line_num},{line_num}:{file_rel}",
        "--no-patch",
        "--date=short",
        "--format=%H%x00%an%x00%ad%x00%s",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        return []

    timeline = []
    for line in res.stdout.strip().splitlines():
        parts = line.split("\x00")
        if len(parts) >= 4:
            sha, author, date_val, subject = parts[0], parts[1], parts[2], parts[3]
            timeline.append(
                {
                    "sha": sha,
                    "short": sha[:7],
                    "date": date_val,
                    "author": author,
                    "subject": subject,
                    "blamed": sha == blamed_sha,
                    "llm_suspect": (sha == llm_sha) if llm_sha else False,
                    "truth": sha == truth_sha,
                }
            )
    return timeline
