"""Step 6: Package Docker image as tar file."""
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import settings
from src.utils.docker_utils import save_image
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


def package_image(
    image_tag: str,
    output_root: Path,
    source: str,
    sha_n_tag: str,
    pr_number: Optional[int] = None,
) -> Path:
    """
    Step 6: Save Docker image as tar file.

    Tar filename:
    - pull: {prefix}-pull-{sha_n_tag}-{timestamp}.tar
    - build: {prefix}-build-{sha_n_tag}-PR{pr_number}-{timestamp}.tar

    Args:
        image_tag: Docker image tag to package (e.g. repo:nightly-abc or repo:nightly-abc_PR123)
        output_root: Root output directory; tar files stored under output_root / "images_tar"
        source: "pull" or "build"
        sha_n_tag: Nightly tag part (e.g. nightly-abc1234)
        pr_number: PR number (required when source == "build")

    Returns:
        Path to the saved tar file

    Raises:
        RuntimeError: If packaging fails
    """
    images_dir = output_root / "images_tar"
    images_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    safe_tag = sha_n_tag.replace("/", "_").replace(":", "-")

    if source == "pull":
        output_filename = f"{settings.output_file_prefix}-pull-{safe_tag}-{timestamp}.tar"
    elif source == "build":
        if pr_number is None:
            raise ValueError("pr_number is required when source is 'build'")
        output_filename = f"{settings.output_file_prefix}-build-{safe_tag}-PR{pr_number}-{timestamp}.tar"
    else:
        raise ValueError(f"source must be 'pull' or 'build', got {source!r}")

    output_path = images_dir / output_filename
    logger.info(f"Step 6: Packaging image {image_tag} to {output_path}")

    if not save_image(image_tag, output_path):
        raise RuntimeError(f"Failed to save image {image_tag} to {output_path}")

    logger.info(f"Successfully packaged image to {output_path}")
    return output_path
