"""Step 3: Docker pull nightly-sha-n and verify image digest against Docker Hub."""
from src.utils.docker_utils import (
    check_image_exists,
    pull_image,
    get_manifest_digest_from_registry,
    verify_image_digest_after_pull,
)
from src.utils.logger import setup_logger
from config import settings

logger = setup_logger(__name__)


def pull_nightly_and_verify(sha_n: str) -> str:
    """
    Step 3: Pull nightly image (nightly-{sha_n}) and verify digest matches Docker Hub.

    Args:
        sha_n: Nightly build SHA from Step 1.

    Returns:
        Full image tag that was pulled (e.g. repo:nightly-abc1234).

    Raises:
        RuntimeError: If image does not exist, pull fails, or digest verification fails.
    """
    image_tag = f"{settings.dockerhub_repository}:nightly-{sha_n}"

    logger.info(f"Step 3: Pulling {image_tag}")

    if not check_image_exists(image_tag):
        raise RuntimeError(
            f"Image {image_tag} does not exist in DockerHub. "
            "Cannot proceed."
        )

    if not pull_image(image_tag):
        raise RuntimeError(f"Failed to pull image: {image_tag}")

    logger.info(f"Successfully pulled image: {image_tag}")

    # Verify pulled image digest matches registry
    expected_digest = get_manifest_digest_from_registry(image_tag)
    if expected_digest:
        if not verify_image_digest_after_pull(image_tag, expected_digest):
            raise RuntimeError(
                f"Digest verification failed for {image_tag}: "
                "local image does not match registry digest. "
                "The image may have been tampered with or pull was incomplete."
            )
        logger.info(f"Step 3: Digest verified for {image_tag}")
    else:
        logger.warning(
            f"Could not obtain registry digest for {image_tag}, skipping digest verification"
        )

    return image_tag
