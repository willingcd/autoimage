"""Docker utilities for image operations."""
import subprocess
from pathlib import Path
from typing import Optional, Tuple

import requests

try:
    import docker
    from docker.errors import APIError, ImageNotFound, ContainerError
except ImportError:
    docker = None
    APIError = Exception
    ImageNotFound = Exception
    ContainerError = Exception

from src.config import settings
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

# Docker Hub registry (for digest fetch)
DOCKERHUB_REGISTRY = "https://registry-1.docker.io"
DOCKERHUB_AUTH = "https://auth.docker.io/token"

# Initialize Docker client
try:
    docker_client = docker.from_env()
except Exception as e:
    logger.warning(f"Failed to initialize Docker client: {e}")
    docker_client = None


def check_image_exists(image_tag: str) -> bool:
    """
    Check if a Docker image exists in DockerHub.
    
    Args:
        image_tag: Full image tag (e.g., 'vllm/vllm-openai:nightly-abc1234')
        
    Returns:
        True if image exists, False otherwise
    """
    try:
        # Try to inspect the manifest
        result = subprocess.run(
            ["docker", "manifest", "inspect", image_tag],
            capture_output=True,
            text=True,
            check=False
        )
        return result.returncode == 0
    except FileNotFoundError:
        logger.warning("docker command not found, trying Docker SDK...")
        # Fallback: try to pull (this will fail if image doesn't exist)
        # Note: This is not ideal, but works as a fallback
        return False


def pull_image(image_tag: str) -> bool:
    """
    Pull a Docker image.
    
    Args:
        image_tag: Full image tag to pull
        
    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"Pulling image: {image_tag}")
        
        if docker_client:
            image = docker_client.images.pull(image_tag)
            logger.info(f"Successfully pulled image: {image.id[:12]}")
            return True
        else:
            # Fallback to subprocess
            result = subprocess.run(
                ["docker", "pull", image_tag],
                check=True,
                capture_output=True,
                text=True
            )
            logger.info(f"Successfully pulled image: {image_tag}")
            return True
            
    except (APIError, ImageNotFound, subprocess.CalledProcessError) as e:
        logger.error(f"Failed to pull image {image_tag}: {e}")
        return False


def _parse_image_tag(image_tag: str) -> Tuple[str, str]:
    """Split image_tag into repository and tag. e.g. 'vllm/vllm-openai:nightly-abc' -> ('vllm/vllm-openai', 'nightly-abc')."""
    if ":" in image_tag:
        repo, tag = image_tag.rsplit(":", 1)
        return repo.strip(), tag.strip()
    return image_tag.strip(), "latest"


def get_manifest_digest_from_registry(image_tag: str) -> Optional[str]:
    """
    Get the image digest (sha256:...) from the registry for the given tag.
    Only supports Docker Hub (registry-1.docker.io) for now.

    Args:
        image_tag: Full image tag (e.g. 'vllm/vllm-openai:nightly-abc1234')

    Returns:
        Digest string (e.g. 'sha256:abc...') or None if failed
    """
    repo, tag = _parse_image_tag(image_tag)
    scope = f"repository:{repo}:pull"
    try:
        # Get token (optional basic auth for Docker Hub)
        auth = None
        if settings.dockerhub_username and settings.dockerhub_token:
            auth = (settings.dockerhub_username, settings.dockerhub_token)
        r = requests.get(
            DOCKERHUB_AUTH,
            params={"service": "registry.docker.io", "scope": scope},
            auth=auth,
            timeout=15,
        )
        r.raise_for_status()
        token = r.json().get("token")
        if not token:
            logger.warning("No token in registry auth response")
            return None

        # HEAD manifest to get Docker-Content-Digest
        url = f"{DOCKERHUB_REGISTRY}/v2/{repo}/manifests/{tag}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.docker.distribution.manifest.v2+json",
        }
        resp = requests.head(url, headers=headers, timeout=15)
        resp.raise_for_status()
        digest = resp.headers.get("Docker-Content-Digest") or resp.headers.get("docker-content-digest")
        if digest:
            logger.info(f"Registry digest for {image_tag}: {digest}")
        return digest
    except Exception as e:
        logger.warning(f"Failed to get manifest digest from registry for {image_tag}: {e}")
        return None


def verify_image_digest_after_pull(image_tag: str, expected_digest: str) -> bool:
    """
    Verify that the locally pulled image matches the expected registry digest.

    Args:
        image_tag: Full image tag (e.g. 'vllm/vllm-openai:nightly-abc1234')
        expected_digest: Expected digest from registry (e.g. 'sha256:...')

    Returns:
        True if local image has matching RepoDigest
    """
    if not expected_digest:
        return False
    try:
        if docker_client:
            image = docker_client.images.get(image_tag)
            # image.attrs has RepoDigests like ["repo@sha256:..."]
            repo_digests = image.attrs.get("RepoDigests") or []
        else:
            result = subprocess.run(
                ["docker", "inspect", "--format", "{{json .RepoDigests}}", image_tag],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                logger.error(f"docker inspect failed: {result.stderr}")
                return False
            import json
            repo_digests = json.loads(result.stdout or "[]")
        # Expected form: repo@sha256:xxx
        for rd in repo_digests:
            if rd.endswith("@" + expected_digest) or expected_digest in rd:
                logger.info(f"Digest verified: local image matches registry {expected_digest}")
                return True
        logger.error(
            f"Digest mismatch: expected {expected_digest}, local RepoDigests: {repo_digests}"
        )
        return False
    except Exception as e:
        logger.error(f"Failed to verify image digest: {e}")
        return False


def build_image(
    dockerfile_path: Path,
    image_tag: str,
    build_context: Optional[Path] = None,
    **kwargs
) -> bool:
    """
    Build a Docker image from a Dockerfile.
    
    Args:
        dockerfile_path: Path to Dockerfile
        image_tag: Tag for the built image
        build_context: Build context directory (default: dockerfile_path.parent)
        **kwargs: Additional build arguments
        
    Returns:
        True if successful, False otherwise
    """
    try:
        build_context = build_context or dockerfile_path.parent
        logger.info(f"Building image {image_tag} from {dockerfile_path}")
        
        if docker_client:
            with open(dockerfile_path, 'r') as f:
                dockerfile_content = f.read()
            
            image, logs = docker_client.images.build(
                path=str(build_context),
                dockerfile=str(dockerfile_path.name),
                tag=image_tag,
                **kwargs
            )
            
            # Log build output
            for log in logs:
                if 'stream' in log:
                    logger.debug(log['stream'].strip())
            
            logger.info(f"Successfully built image: {image.id[:12]}")
            return True
        else:
            # Fallback to subprocess
            result = subprocess.run(
                [
                    "docker", "build",
                    "-f", str(dockerfile_path),
                    "-t", image_tag,
                    str(build_context)
                ],
                check=True,
                capture_output=True,
                text=True
            )
            logger.info(f"Successfully built image: {image_tag}")
            return True
            
    except (APIError, subprocess.CalledProcessError) as e:
        logger.error(f"Failed to build image: {e}")
        if hasattr(e, 'stderr') and e.stderr:
            logger.error(f"Build error output: {e.stderr}")
        return False


def save_image(image_tag: str, output_path: Path) -> bool:
    """
    Save a Docker image to a tar file.
    
    Args:
        image_tag: Image tag to save
        output_path: Path to save the tar file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"Saving image {image_tag} to {output_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if docker_client:
            image = docker_client.images.get(image_tag)
            with open(output_path, 'wb') as f:
                for chunk in image.save():
                    f.write(chunk)
        else:
            # Fallback to subprocess
            result = subprocess.run(
                ["docker", "save", "-o", str(output_path), image_tag],
                check=True,
                capture_output=True,
                text=True
            )
        
        # Verify file was created and has content
        if output_path.exists() and output_path.stat().st_size > 0:
            logger.info(f"Successfully saved image to {output_path} ({output_path.stat().st_size / 1024 / 1024:.2f} MB)")
            return True
        else:
            logger.error(f"Saved file is empty or doesn't exist: {output_path}")
            return False
            
    except (APIError, ImageNotFound, subprocess.CalledProcessError) as e:
        logger.error(f"Failed to save image: {e}")
        return False


def run_validation_container(image_tag: str, validation_script: str) -> tuple:
    """
    Run a validation script in a container.
    
    Args:
        image_tag: Image to run
        validation_script: Python script content to execute
        
    Returns:
        Tuple of (success: bool, output: str)
    """
    try:
        logger.info(f"Running validation in container: {image_tag}")
        
        if docker_client:
            # Create and run container
            # Note: detach=False means it runs synchronously and returns logs
            # If container exits with non-zero, it raises ContainerError
            try:
                logs = docker_client.containers.run(
                    image_tag,
                    command=["python", "-c", validation_script],
                    remove=True,
                    stdout=True,
                    stderr=True
                )
                
                # Get output (logs is bytes)
                if isinstance(logs, bytes):
                    output = logs.decode('utf-8')
                else:
                    output = str(logs)
                
                # If no exception, container exited with 0
                success = True
                
            except ContainerError as e:
                # Container exited with non-zero code
                output = e.stderr.decode('utf-8') if isinstance(e.stderr, bytes) else str(e.stderr)
                success = False
                logger.warning(f"Container exited with error: {output}")
            
            logger.info(f"Validation output: {output}")
            return success, output
        else:
            # Fallback to subprocess
            result = subprocess.run(
                [
                    "docker", "run", "--rm",
                    image_tag,
                    "python", "-c", validation_script
                ],
                capture_output=True,
                text=True,
                check=False
            )
            
            success = (result.returncode == 0)
            output = result.stdout + result.stderr
            
            logger.info(f"Validation {'succeeded' if success else 'failed'}: {output}")
            return success, output
            
    except (APIError, subprocess.CalledProcessError) as e:
        logger.error(f"Failed to run validation container: {e}")
        return False, str(e)
