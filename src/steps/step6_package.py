"""Step 6: Package Docker image as tar file."""
from pathlib import Path

from config import settings
from src.utils.docker_utils import save_image
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


def package_image(image_tag: str, output_dir: Path, image_tag_name: str) -> Path:
    """
    Step 6: Save Docker image as tar file.
    
    Args:
        image_tag: Docker image tag to package
        output_dir: Directory to save the tar file
        image_tag_name: Custom tag name for the output file
        
    Returns:
        Path to the saved tar file
        
    Raises:
        RuntimeError: If packaging fails
    """
    logger.info(f"Step 6: Packaging image {image_tag} to {output_dir}")
    
    # Generate output filename using configured prefix
    output_filename = f"{settings.output_file_prefix}-{image_tag_name}.tar"
    output_path = output_dir / output_filename
    
    # Save image
    if not save_image(image_tag, output_path):
        raise RuntimeError(f"Failed to save image {image_tag} to {output_path}")
    
    logger.info(f"Successfully packaged image to {output_path}")
    return output_path
