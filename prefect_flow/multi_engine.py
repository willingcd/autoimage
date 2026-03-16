"""Higher-level Prefect flow for multi-engine orchestration.

Usage scenario (company side):
- This module stays inside `prefect_flow/`.
- Existing single-engine pipeline is `build_pipeline_flow` in `prefect_flow.flow`.
- Company Prefect pipelines import and call `multi_engine_build_flow`.

Behaviour:
- First, run **vllm** and **vllm-ascend** in parallel作为两个子流（子任务）。
- 如果 vllm 在任意 Step 失败（单次调用异常），则再触发 **sglang** 和 **mindie**
  两个新的工作子流，并行构建。

注意：
- 这里没有强绑 ENGINE_NAME / GITHUB_REPO_* 等具体值，只在输出目录上区分引擎。
- 环境变量（目标仓库、镜像仓库等）建议由公司那一侧按引擎来配置
  （例如用不同运行环境、不同部署规则），这里只负责控制「什么时候、对哪个引擎」
  调用 `build_pipeline_flow`。
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Dict, List

from prefect import flow, task

from .flow import build_pipeline_flow
from src.engine_config import get_engine_config


@dataclass(frozen=True)
class EngineConfig:
    """Lightweight engine description used only for naming / output layout."""

    engine_id: str
    output_subdir: str


# Four engines we care about
ENGINE_VLLM = EngineConfig("vllm", "vllm")
ENGINE_VLLM_ASCEND = EngineConfig("vllm-ascend", "vllm_ascend")
ENGINE_SGLANG = EngineConfig("sglang", "sglang")
ENGINE_MINDIE = EngineConfig("mindie", "mindie")


@task(name="run_single_engine_pipeline")
def run_single_engine_pipeline(
    engine: EngineConfig,
    model_id: str,
    output_root: str,
) -> Dict[str, Any]:
    """Run the existing build pipeline for a single engine.

    This task will:
    - Calculate the engine-specific output_dir
    - Load EngineConfig from src.engine_config
    - Temporarily set engine-related env vars (ENGINE_NAME, GITHUB_REPO_*, DOCKERHUB_REPOSITORY,
      MODEL_REGISTRY_IMPORT_PATH, OUTPUT_FILE_PREFIX, GIT_REPO_URL)
    - Delegate to build_pipeline_flow(model_id, output_dir)
    """
    base = Path(output_root)
    base.mkdir(parents=True, exist_ok=True)
    output_dir = base / engine.output_subdir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load engine-specific configuration
    engine_cfg = get_engine_config(engine.engine_id)

    # Prepare env overrides for this engine
    env_overrides = {
        "ENGINE_NAME": engine_cfg.engine_name,
        "GITHUB_REPO_OWNER": engine_cfg.github_repo_owner,
        "GITHUB_REPO_NAME": engine_cfg.github_repo_name,
        "DOCKERHUB_REPOSITORY": engine_cfg.dockerhub_repository,
        "MODEL_REGISTRY_IMPORT_PATH": engine_cfg.model_registry_import_path,
        "OUTPUT_FILE_PREFIX": engine_cfg.output_file_prefix,
        "GIT_REPO_URL": engine_cfg.git_repo_url,
    }

    # Temporarily update os.environ while running the single-engine pipeline
    old_env: Dict[str, str] = {}
    try:
        for key, value in env_overrides.items():
            old_env[key] = os.environ.get(key, "")
            os.environ[key] = value

        result = build_pipeline_flow(model_id=model_id, output_dir=str(output_dir))
    finally:
        # Restore previous env (empty string → unset)
        for key, old_value in old_env.items():
            if old_value == "":
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value
    # Augment result with engine id for easier上层聚合
    result_with_engine = dict(result)
    result_with_engine["engine_id"] = engine.engine_id
    result_with_engine["engine_output_dir"] = str(output_dir)
    return result_with_engine


@flow(
    name="multi_engine_build_flow",
    description=(
        "Orchestrate builds for vllm / vllm-ascend / sglang / mindie.\n"
        "- vllm & vllm-ascend: first pair, built in parallel.\n"
        "- If vllm fails, then trigger sglang & mindie as a second pair, in parallel."
    ),
)
def multi_engine_build_flow(model_id: str, output_root: str) -> Dict[str, Any]:
    """Company-facing orchestration flow.

    Args:
        model_id: Full model ID (e.g. 'Qwen/Qwen3.5-35B-A3B-FP8')
        output_root: Base directory for all engines, e.g. '/output'.
                     Actual per-engine dirs will be:
                       - <output_root>/vllm/
                       - <output_root>/vllm_ascend/
                       - <output_root>/sglang/
                       - <output_root>/mindie/

    Returns:
        A dict summarising which engines ran, their success/failure and results.
    """
    summary: Dict[str, Any] = {
        "model_id": model_id,
        "output_root": output_root,
        "engines": {},
    }

    # --- Stage 1: run vllm and vllm-ascend in parallel ---
    vllm_future = run_single_engine_pipeline.submit(
        ENGINE_VLLM, model_id, output_root
    )
    vllm_ascend_future = run_single_engine_pipeline.submit(
        ENGINE_VLLM_ASCEND, model_id, output_root
    )

    vllm_ok = True
    vllm_result: Dict[str, Any] | None = None
    vllm_error: str | None = None

    # Collect vllm-ascend result (if it fails, we let the exception propagate;
    # company side可以通过 Prefect UI/日志看到失败细节)
    try:
        vllm_ascend_result = vllm_ascend_future.result()
        summary["engines"][ENGINE_VLLM_ASCEND.engine_id] = {
            "status": "success",
            "result": vllm_ascend_result,
        }
    except Exception as e:  # noqa: BLE001
        summary["engines"][ENGINE_VLLM_ASCEND.engine_id] = {
            "status": "failed",
            "error": str(e),
        }

    # Collect vllm result, but we need its失败/成功来决定是否触发 sglang/mindie
    try:
        vllm_result = vllm_future.result()
        summary["engines"][ENGINE_VLLM.engine_id] = {
            "status": "success",
            "result": vllm_result,
        }
    except Exception as e:  # noqa: BLE001
        vllm_ok = False
        vllm_error = str(e)
        summary["engines"][ENGINE_VLLM.engine_id] = {
            "status": "failed",
            "error": vllm_error,
        }

    # --- Stage 2: if vllm failed, trigger sglang & mindie in parallel ---
    if not vllm_ok:
        sglang_future = run_single_engine_pipeline.submit(
            ENGINE_SGLANG, model_id, output_root
        )
        mindie_future = run_single_engine_pipeline.submit(
            ENGINE_MINDIE, model_id, output_root
        )

        try:
            sglang_result = sglang_future.result()
            summary["engines"][ENGINE_SGLANG.engine_id] = {
                "status": "success",
                "result": sglang_result,
            }
        except Exception as e:  # noqa: BLE001
            summary["engines"][ENGINE_SGLANG.engine_id] = {
                "status": "failed",
                "error": str(e),
            }

        try:
            mindie_result = mindie_future.result()
            summary["engines"][ENGINE_MINDIE.engine_id] = {
                "status": "success",
                "result": mindie_result,
            }
        except Exception as e:  # noqa: BLE001
            summary["engines"][ENGINE_MINDIE.engine_id] = {
                "status": "failed",
                "error": str(e),
            }

    return summary


