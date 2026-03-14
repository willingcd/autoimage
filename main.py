"""Main entry point for build automation."""
import sys
from pathlib import Path
from typing import Optional

import click

from config import settings
from src.utils.logger import setup_logger
from src.error_handler import handle_error
from src.steps.step1_get_nightly import get_nightly_sha
from src.steps.step2_match_pr import match_model_pr
from src.steps.step3_pull_nightly import pull_nightly_and_verify
from src.steps.step4_check_ancestor import check_ancestor_relationship
from src.steps.step4_docker_ops import docker_build_custom
from src.steps.step5_validate import validate_model_registrations
from src.steps.step6_package import package_image

logger = setup_logger(__name__)


@click.command()
@click.option("--model-id", required=True, help="Full model ID (e.g., Qwen/Qwen3.5-35B-A3B-FP8)")
@click.option("--output-dir", required=True, type=click.Path(), help="Output directory for tar file")
def main(model_id: str, output_dir: str):
    """
    Build automation pipeline for inference engine models.

    This script automates the process of building and validating Docker images
    for inference engine models (e.g., vLLM, TensorRT-LLM) based on PR changes.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    logger.info(f"Starting build automation for model ID: {model_id}")
    logger.info(f"Output directory: {output_path}")

    context = {
        "model_id": model_id,
        "output_dir": str(output_path),
    }
    
    try:
        # Step 1: Get latest nightly build SHA
        logger.info("=" * 60)
        logger.info("Step 1: Getting latest nightly build SHA")
        logger.info("=" * 60)
        sha_n = get_nightly_sha()
        context["sha_n"] = sha_n
        logger.info(f"Step 1 completed: sha_n = {sha_n}")
        
        # Step 2: Match PR and parse registrations
        logger.info("=" * 60)
        logger.info("Step 2: Matching PR and parsing registrations")
        logger.info("=" * 60)
        pr_result = match_model_pr(model_id)
        sha_m = pr_result["sha_m"]
        model_registrations = pr_result["model_registrations"]
        pr_number = pr_result["pr_number"]

        # Derive a primary model key for naming (use registration_key if available)
        if model_registrations:
            primary_model_key = (
                model_registrations[0].get("registration_key")
                or model_registrations[0].get("class_name")
                or "unknown-model"
            )
        else:
            # Fallback: derive from model_id
            primary_model_key = model_id.split("/")[-1] if "/" in model_id else model_id

        context["sha_m"] = sha_m
        context["pr_number"] = pr_number
        context["primary_model_key"] = primary_model_key
        logger.info(f"Step 2 completed: sha_m = {sha_m}, found {len(model_registrations)} registrations")

        # Step 3: Pull nightly image and verify digest
        logger.info("=" * 60)
        logger.info("Step 3: Pull nightly-sha-n and verify image digest")
        logger.info("=" * 60)
        nightly_image_tag = pull_nightly_and_verify(sha_n)
        logger.info(f"Step 3 completed: {nightly_image_tag}")

        # Step 4: Is sha-m an ancestor of sha-n?
        logger.info("=" * 60)
        logger.info("Step 4: Check if sha-m is ancestor of sha-n")
        logger.info("=" * 60)
        is_ancestor = check_ancestor_relationship(sha_m, sha_n)
        logger.info(f"Step 4 completed: sha_m {'IS' if is_ancestor else 'IS NOT'} ancestor of sha_n")

        # sha_n_tag = Docker Hub tag part for nightly image (e.g. nightly-abc1234)
        sha_n_tag = f"nightly-{sha_n}"

        if is_ancestor:
            image_tag_final = nightly_image_tag
            logger.info(f"Using pulled nightly image: {image_tag_final}")
            package_source = "pull"
            package_pr_number = None
        else:
            logger.info("Step 4-B: Building custom image from PR changes")
            image_tag_final = docker_build_custom(
                sha_m=sha_m,
                sha_n=sha_n,
                pr_number=pr_number,
                model_key=primary_model_key,
                output_root=output_path,
            )
            package_source = "build"
            package_pr_number = pr_number
        logger.info(f"Final image for Step 5/6: {image_tag_final}")

        # Step 5: Validate model registrations
        logger.info("=" * 60)
        logger.info("Step 5: Validating model registrations")
        logger.info("=" * 60)
        validate_model_registrations(image_tag_final, model_registrations)
        logger.info("Step 5 completed: All validations passed")

        # Step 6: Package image (to output_root / images_tar)
        logger.info("=" * 60)
        logger.info("Step 6: Packaging image")
        logger.info("=" * 60)
        tar_path = package_image(
            image_tag_final,
            output_path,
            source=package_source,
            sha_n_tag=sha_n_tag,
            pr_number=package_pr_number,
        )
        logger.info(f"Step 6 completed: Package saved to {tar_path}")
        
        # Success
        logger.info("=" * 60)
        logger.info("✅ Build automation completed successfully!")
        logger.info(f"Package: {tar_path}")
        logger.info("=" * 60)
        
    except Exception as e:
        # Handle error and exit
        handle_error("Build Pipeline", e, context)
        sys.exit(1)


if __name__ == "__main__":
    main()
