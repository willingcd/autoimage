"""
Prefect flow: trigger parallel builds for vllm, vllm_ascend, sglang, mindie.

Does not modify any existing code; runs main.main() via subprocess with
per-engine env and output dir (e.g. /output/vllm, /output/vllm_ascend, ...).
"""

import os
import subprocess
import sys
from pathlib import Path

from prefect import flow, task

from .engine_configs import (
    ENGINE_ENV_OVERRIDES,
    ENGINE_IDS,
    ENGINE_OUTPUT_SUBDIRS,
)


def _project_root() -> Path:
    """Project root (parent of prefect_flow)."""
    return Path(__file__).resolve().parent.parent


@task(name="build_engine")
def build_engine_task(engine_id: str, model_id: str, output_root: Path) -> dict:
    """
    Run the existing main.py for one engine in a subprocess.

    Uses ENGINE_* env overrides and output_dir = output_root / engine_subdir.
    """
    if engine_id not in ENGINE_IDS:
        raise ValueError(f"Unknown engine_id: {engine_id}")

    subdir = ENGINE_OUTPUT_SUBDIRS[engine_id]
    output_dir = (output_root / subdir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update(ENGINE_ENV_OVERRIDES.get(engine_id, {}))

    root = _project_root()
    main_py = root / "main.py"
    if not main_py.exists():
        raise FileNotFoundError(f"main.py not found at {main_py}")

    cmd = [
        sys.executable,
        str(main_py),
        "--model-id",
        model_id,
        "--output-dir",
        str(output_dir),
    ]
    result = subprocess.run(
        cmd,
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
    )

    return {
        "engine_id": engine_id,
        "output_dir": str(output_dir),
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


@flow(name="multi_engine_build", description="Build vllm, vllm_ascend, sglang, mindie in parallel")
def multi_engine_build_flow(model_id: str, output_root: str = "/output") -> list:
    """
    Run the build pipeline for all four engines in parallel.

    Args:
        model_id: Full model ID (e.g. Qwen/Qwen3.5-35B-A3B-FP8)
        output_root: Base output directory; each engine writes to output_root/<engine_subdir>/

    Returns:
        List of result dicts from each engine task.
    """
    root = Path(output_root).resolve()
    root.mkdir(parents=True, exist_ok=True)

    results = []
    for engine_id in ENGINE_IDS:
        r = build_engine_task.submit(engine_id, model_id, root)
        results.append(r)

    # Wait for all and return results (Prefect gathers futures when returning)
    return [r.result() for r in results]
