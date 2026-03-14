"""Step 4-B: Docker build from PR changes (base image nightly-sha-n already pulled in Step 3)."""
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.utils.docker_utils import build_image
from src.utils.github_api import GitHubAPI
from src.utils.logger import setup_logger
from config import settings

logger = setup_logger(__name__)


def docker_build_custom(
    sha_m: str,
    sha_n: str,
    pr_number: int,
    model_key: str,
    output_root: Optional[Path] = None,
) -> str:
    """
    Step 4-B: Build custom image from PR changes.
    
    Args:
        sha_m: PR merge commit SHA
        sha_n: Nightly build SHA
        pr_number: PR number
        model_key: Primary model registration key (used for naming)
        output_root: Root output directory (e.g., ./output). If None, defaults to ./output
        
    Returns:
        Image tag of the built image
        
    Raises:
        RuntimeError: If build fails
    """
    logger.info(
        f"Step 4-B: Building custom image for PR #{pr_number} "
        f"(sha_m: {sha_m}, sha_n: {sha_n}, model_key: {model_key})"
    )
    # Base image nightly-{sha_n} was already pulled and digest-verified in Step 3.

    github_api = GitHubAPI()
    
    # Get changed files from PR
    files = github_api.get_pr_files(pr_number)
    
    if not files:
        raise RuntimeError(f"No changed files found in PR #{pr_number}")
    
    # Prepare output directories
    output_root = output_root or Path("output")
    docker_build_root = output_root / "docker_build"
    dockerfiles_dir = docker_build_root / "dockerfiles"
    contexts_root = docker_build_root / "build_contexts"

    dockerfiles_dir.mkdir(parents=True, exist_ok=True)
    contexts_root.mkdir(parents=True, exist_ok=True)

    engine_name = settings.engine_name
    safe_model_key = model_key.replace("/", "_").replace(" ", "_")
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")

    # 命名中显式标出 sha_m / sha_n，避免混淆
    context_dir_name = (
        f"{engine_name}-{safe_model_key}-sham-{sha_m[:7]}-shan-{sha_n[:7]}-{timestamp}"
    )
    context_dir = contexts_root / context_dir_name
    context_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Build context directory: {context_dir}")

    # Download changed files into build context
    for file_info in files:
        file_path = file_info["filename"]
        file_status = file_info.get("status")
        
        if file_status in ("added", "modified"):
            try:
                # Get file content at merge commit
                content = github_api.get_file_content(file_path, ref=sha_m)
                
                # Create file in context directory maintaining structure
                target_path = context_dir / file_path
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(content)
                
                logger.debug(f"Downloaded file to context: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to download {file_path}: {e}")
                continue
    
    # Generate Dockerfile content
    dockerfile_content = generate_dockerfile(sha_n, files)

    # Dockerfile inside build context (used for actual build)
    dockerfile_in_context = context_dir / "Dockerfile"
    dockerfile_in_context.write_text(dockerfile_content)

    # Archive Dockerfile under docker_build/dockerfiles with naming convention
    archive_name = (
        f"Dockerfile.{engine_name}-{safe_model_key}-sham-{sha_m[:7]}-shan-{sha_n[:7]}.generated"
    )
    dockerfile_archive_path = dockerfiles_dir / archive_name
    dockerfile_archive_path.write_text(dockerfile_content)

    logger.info(
        f"Generated Dockerfile for build (context: {dockerfile_in_context}) "
        f"and archived as {dockerfile_archive_path}"
    )
    
    # Build image: tag = <sha_n's tag>_PR<pr_number> (e.g. nightly-abc1234_PR123)
    image_tag = f"{settings.dockerhub_repository}:nightly-{sha_n}_PR{pr_number}"
    if not build_image(dockerfile_in_context, image_tag, build_context=context_dir):
        raise RuntimeError(f"Failed to build image: {image_tag}")
    logger.info(f"Successfully built image: {image_tag}")
    return image_tag


def generate_dockerfile(base_sha: str, changed_files: List[Dict]) -> str:
    """
    Generate Dockerfile for building custom image.
    
    Args:
        base_sha: Base image SHA (sha-n)
        changed_files: List of changed file information
        
    Returns:
        Dockerfile content as string
    """
    base_image = f"{settings.dockerhub_repository}:nightly-{base_sha}"
    
    dockerfile_lines = [
        f"FROM {base_image}",
        "",
        "# Copy changed files",
    ]
    
    # Add COPY commands for each changed file
    for file_info in changed_files:
        file_path = file_info["filename"]
        if file_info.get("status") in ("added", "modified"):
            dockerfile_lines.append(f"COPY {file_path} /app/{file_path}")
    
    dockerfile_lines.extend([
        "",
        "# Set working directory",
        "WORKDIR /app",
    ])
    
    return "\n".join(dockerfile_lines)
