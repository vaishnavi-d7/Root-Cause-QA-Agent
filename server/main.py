"""FastAPI application exposing RootCause-QA endpoints and static dashboard assets."""
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent

import llm_client
from server.runs import (
    RUNS_DIR,
    create_run,
    delete_run,
    get_active_run_id,
    get_run_details,
    get_timeline,
    list_runs,
    register_listener,
    unregister_listener,
)

app = FastAPI(title="RootCause-QA API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunCreateRequest(BaseModel):
    """Payload schema for creating a new pipeline run."""

    rca: str = "auto"
    provider: Optional[str] = None
    llm_payloads: bool = False
    reseed: bool = False
    api_key: Optional[str] = None


@app.get("/api/health")
def health() -> Dict[str, bool]:
    """Health check endpoint."""
    return {"ok": True}


@app.get("/api/config")
def config() -> Dict[str, Any]:
    """Return configured LLM providers, model presets, and default RCA mode."""
    providers_info = []
    for p_name, p_data in llm_client.PRESETS.items():
        key_env = p_data.get("key_env")
        configured = True if key_env is None else bool(os.environ.get(key_env))
        needs_key = key_env is not None
        providers_info.append(
            {
                "name": p_name,
                "key_env": key_env,
                "default_model": p_data.get("model"),
                "configured": configured,
                "needs_key": needs_key,
            }
        )

    llm_avail = llm_client.available()
    return {
        "providers": providers_info,
        "llm_available": llm_avail,
        "default_rca_mode": "both" if llm_avail else "baseline",
    }


@app.post("/api/runs", status_code=status.HTTP_202_ACCEPTED)
def start_run(req: RunCreateRequest) -> Dict[str, str]:
    """Trigger background pipeline run or reject with 400 (missing LLM) or 409 (busy)."""
    # 1. Validate if LLM is required
    rca_mode = req.rca.lower()
    if rca_mode in ("llm", "both"):
        llm_ready = False
        if req.api_key:
            llm_ready = True
        elif req.provider == "ollama":
            llm_ready = True
        elif req.provider:
            key_var = llm_client.PRESETS.get(req.provider, {}).get("key_env")
            llm_ready = bool(key_var and os.environ.get(key_var))
        else:
            llm_ready = llm_client.available()

        if not llm_ready:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=llm_client.missing_hint(),
            )

    # 2. Check concurrency: allow ONE active run at a time
    active_id = get_active_run_id()
    if active_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run {active_id} is already in progress. Only one run may execute at a time.",
        )

    run_id = create_run(
        rca=req.rca,
        provider=req.provider,
        llm_payloads=req.llm_payloads,
        reseed=req.reseed,
        api_key=req.api_key,
    )

    if not run_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A run is already in progress.",
        )

    return {"run_id": run_id}


@app.get("/api/runs")
def get_runs() -> List[Dict[str, Any]]:
    """Return summary list of all runs, newest first."""
    return list_runs()


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> Dict[str, Any]:
    """Return full details, findings, RCA results, and markdown summaries for run_id."""
    details = get_run_details(run_id)
    if not details:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return details


@app.get("/api/runs/{run_id}/events")
async def stream_events(run_id: str, request: Request) -> StreamingResponse:
    """Stream SSE events: historical replay, live updates, and final end event."""
    run_dir = RUNS_DIR / run_id
    meta_file = run_dir / "meta.json"
    if not meta_file.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()
    register_listener(run_id, loop, q)

    async def event_generator():
        try:
            # 1. Replay historical events from events.jsonl
            events_file = run_dir / "events.jsonl"
            last_event_type = None
            if events_file.exists():
                lines = events_file.read_text(encoding="utf-8").splitlines()
                for line in lines:
                    if line.strip():
                        try:
                            parsed_line = json.loads(line)
                            last_event_type = parsed_line.get("type")
                        except Exception:
                            pass
                        yield f"data: {line.strip()}\n\n"

            # 2. Stream live events if still active
            while True:
                meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}
                status_str = meta.get("status", "unknown")

                if status_str in ("done", "failed"):
                    if q.empty():
                        if last_event_type != "end":
                            end_evt = {"type": "end", "status": status_str}
                            yield f"data: {json.dumps(end_evt)}\n\n"
                        break

                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                    last_event_type = event.get("type")
                    yield f"data: {json.dumps(event)}\n\n"
                    if last_event_type == "end":
                        break
                except asyncio.TimeoutError:
                    # 15s keep-alive comment
                    yield ": keep-alive\n\n"
        finally:
            unregister_listener(run_id, q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/runs/{run_id}/media/{media_path:path}")
def serve_media(run_id: str, media_path: str) -> FileResponse:
    """Serve media files strictly from videos/ and screenshots/ with path traversal guards."""
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    target_path = (run_dir / media_path).resolve()
    videos_dir = (run_dir / "videos").resolve()
    screenshots_dir = (run_dir / "screenshots").resolve()

    # Reject any path that escapes the allowed media directories
    is_video = str(target_path).startswith(str(videos_dir))
    is_screenshot = str(target_path).startswith(str(screenshots_dir))

    if not (is_video or is_screenshot):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    if target_path.suffix == ".webm":
        return FileResponse(target_path, media_type="video/webm")
    elif target_path.suffix == ".png":
        return FileResponse(target_path, media_type="image/png")
    return FileResponse(target_path, media_type="application/octet-stream")


@app.get("/api/runs/{run_id}/findings/{fid}/timeline")
def timeline(run_id: str, fid: str) -> List[Dict[str, Any]]:
    """Return chronological commit history touching the failing line with culprit flags."""
    return get_timeline(run_id, fid)


@app.delete("/api/runs/{run_id}")
def delete_run_endpoint(run_id: str) -> Dict[str, bool]:
    """Delete run folder on disk using Windows-safe rmtree."""
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    active_id = get_active_run_id()
    if run_id == active_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete an active run.",
        )

    deleted = delete_run(run_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to delete run")
    return {"ok": True}


# Serve static web dashboard files at / AFTER API routes
web_dir = ROOT_DIR / "web"
web_dir.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="static")
