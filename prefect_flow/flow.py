"""Prefect flow that wraps the existing 6-step build pipeline.

Design goals:
- Do NOT modify existing project code (main.py, src/steps, config.py).
- Expose a clean Prefect @flow that company pipelines can import.
- Keep all Prefect-specific code inside the `prefect_flow` package.
"""

from pathlib import Path
from typing import Dict, Any

from prefect import flow, task

from src.error_handler import handle_error
from src.steps.step1_get_nightly import get_nightly_sha
from src.steps.step2_match_pr import match_model_pr
from src.steps.step3_pull_nightly import pull_nightly_and_verify
from src.steps.step4_check_ancestor import check_ancestor_relationship
from src.steps.step4_docker_ops import docker_build_custom
from src.steps.step5_validate import validate_model_registrations
from src.steps.step6_package import package_image


@task(name="step1_get_nightly_sha", retries=3, retry_delay_seconds=30)
def step1_get_nightly_sha_task() -> str:
    """Prefect task: Step 1 - get latest nightly SHA from Docker registry."""
    return get_nightly_sha()


@task(name="step2_match_pr", retries=3, retry_delay_seconds=30)
def step2_match_pr_task(model_id: str) -> Dict[str, Any]:
    """Prefect task: Step 2 - get latest merged PR and model registrations."""
    return match_model_pr(model_id)


@task(name="step3_pull_and_verify", retries=3, retry_delay_seconds=30)
def step3_pull_and_verify_task(sha_n: str) -> str:
    """Prefect task: Step 3 - docker pull nightly-sha-n and verify digest."""
    return pull_nightly_and_verify(sha_n)


@task(name="step4_check_ancestor")
def step4_check_ancestor_task(sha_m: str, sha_n: str) -> bool:
    """Prefect task: Step 4 - check if sha-m is ancestor of sha-n."""
    return check_ancestor_relationship(sha_m, sha_n)


@task(name="step4b_docker_build", retries=3, retry_delay_seconds=60)
def step4b_docker_build_task(
    sha_m: str,
    sha_n: str,
    pr_number: int,
    model_key: str,
    output_root: Path,
) -> str:
    """Prefect task: Step 4-B - build custom image from PR changes."""
    return docker_build_custom(
        sha_m=sha_m,
        sha_n=sha_n,
        pr_number=pr_number,
        model_key=model_key,
        output_root=output_root,
    )


@task(name="step5_validate")
def step5_validate_task(image_tag: str, model_registrations: Dict[str, Any]) -> None:
    """Prefect task: Step 5 - validate model registrations in container."""
    validate_model_registrations(image_tag, model_registrations)


@task(name="step6_package")
def step6_package_task(
    image_tag: str,
    output_root: Path,
    source: str,
    sha_n_tag: str,
    pr_number: int | None,
) -> Path:
    """Prefect task: Step 6 - package Docker image as tar file."""
    return package_image(
        image_tag=image_tag,
        output_root=output_root,
        source=source,
        sha_n_tag=sha_n_tag,
        pr_number=pr_number,
    )


@flow(
    name="build_inference_engine_image",
    description=(
        "Build and validate an inference engine Docker image using the "
        "existing 6-step pipeline (nightly SHA, PR, pull/build, validate, package)."
    ),
)
def build_pipeline_flow(model_id: str, output_dir: str) -> Dict[str, Any]:
    """Top-level Prefect flow wrapping steps 1–6.

    Args:
        model_id: Full model ID (e.g., 'Qwen/Qwen3.5-35B-A3B-FP8').
        output_dir: Base output directory (same semantics as main.py).

    Returns:
        A dict summarising key results (sha_n, sha_m, pr_number, image_tag, tar_path).
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    context: Dict[str, Any] = {
        "model_id": model_id,
        "output_dir": str(output_path),
    }

    try:
        # Step 1
        sha_n = step1_get_nightly_sha_task.submit().result()
        context["sha_n"] = sha_n

        # Step 2
        pr_result = step2_match_pr_task.submit(model_id).result()
        sha_m = pr_result["sha_m"]
        model_registrations = pr_result["model_registrations"]
        pr_number = pr_result["pr_number"]

        if model_registrations:
            primary_model_key = (
                model_registrations[0].get("registration_key")
                or model_registrations[0].get("class_name")
                or "unknown-model"
            )
        else:
            primary_model_key = model_id.split("/")[-1] if "/" in model_id else model_id

        context["sha_m"] = sha_m
        context["pr_number"] = pr_number
        context["primary_model_key"] = primary_model_key

        # Step 3
        nightly_image_tag = step3_pull_and_verify_task.submit(sha_n).result()

        # Step 4
        is_ancestor = step4_check_ancestor_task.submit(sha_m, sha_n).result()

        sha_n_tag = f"nightly-{sha_n}"

        if is_ancestor:
            image_tag_final = nightly_image_tag
            package_source = "pull"
            package_pr_number: int | None = None
        else:
            image_tag_final = step4b_docker_build_task.submit(
                sha_m=sha_m,
                sha_n=sha_n,
                pr_number=pr_number,
                model_key=primary_model_key,
                output_root=output_path,
            ).result()
            package_source = "build"
            package_pr_number = pr_number

        # Step 5
        step5_validate_task.submit(image_tag_final, model_registrations).result()

        # Step 6
        tar_path = step6_package_task.submit(
            image_tag=image_tag_final,
            output_root=output_path,
            source=package_source,
            sha_n_tag=sha_n_tag,
            pr_number=package_pr_number,
        ).result()

        return {
            "model_id": model_id,
            "sha_n": sha_n,
            "sha_m": sha_m,
            "pr_number": pr_number,
            "image_tag": image_tag_final,
            "tar_path": str(tar_path),
            "output_dir": str(output_path),
        }

    except Exception as e:
        # Reuse existing error handler so notification behaviour is identical
        handle_error("Build Pipeline (Prefect flow)", e, context)


