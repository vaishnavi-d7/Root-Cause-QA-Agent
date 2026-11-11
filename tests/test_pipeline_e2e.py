"""End-to-end integration test executing the full baseline RootCause-QA pipeline."""
import sys
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from run_pipeline import PipelineConfig, run as run_pipeline


@pytest.mark.slow
def test_pipeline_baseline_e2e(tmp_path: Path) -> None:
    """Verify that running the pipeline in baseline mode detects 5, reproduces 5, and scores 4/5."""
    out_dir = tmp_path / "test_pipeline_out"

    config = PipelineConfig(
        port=5065,
        out=str(out_dir),
        reseed=True,
        llm_payloads=False,
        provider=None,
        rca="baseline",
    )

    result = run_pipeline(config)

    # 1. Assert detection and reproduction counts
    assert len(result.findings) == 5, f"Expected 5 findings, got {len(result.findings)}"
    reproduced_count = sum(1 for f in result.findings if f.reproduced)
    assert reproduced_count == 5, f"Expected 5 reproduced findings, got {reproduced_count}"

    # 2. Assert benchmark summary metrics
    assert result.benchmark["total_bugs"] == 5
    assert result.benchmark["detected"] == 5
    assert result.benchmark["reproduced"] == 5
    assert result.benchmark["modes"]["baseline"]["correct"] == 4
    assert result.benchmark["modes"]["baseline"]["total"] == 5

    # 3. Assert generated artifacts exist on disk
    assert (out_dir / "report.md").exists()
    assert (out_dir / "benchmark.md").exists()
    assert (out_dir / "rca_baseline.json").exists()
    assert (out_dir / "server.log").exists()

