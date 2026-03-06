"""Docker utilities for image operations."""
import subprocess
from pathlib import Path
from typing import Optional

try:
    import docker
    from docker.errors import APIError, ImageNotFound, ContainerError
except ImportError:
    docker = None
    APIError = Exception
    ImageNotFound = Exception
    ContainerError = Exception

from config import settings
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

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
