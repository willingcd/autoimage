"""Step 5: Validate model registrations in Docker container."""
from typing import Dict, List

from src.config import settings
from src.utils.docker_utils import run_validation_container
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


def validate_model_registrations(
    image_tag: str,
    model_registrations: List[Dict[str, str]]
) -> bool:
    """
    Validate that model classes are registered in ModelRegistry.
    
    Args:
        image_tag: Docker image tag to validate
        model_registrations: List of registration dicts with 'class_name' field
        
    Returns:
        True if all validations pass, False otherwise
        
    Raises:
        RuntimeError: If validation fails
    """
    if not model_registrations:
        logger.warning("No model registrations to validate")
        return True
    
    # Extract class names for validation
    class_names = [reg["class_name"] for reg in model_registrations]
    
    logger.info(
        f"Step 5: Validating {len(class_names)} model classes in {image_tag}"
    )
    
    # Generate validation script
    validation_script = generate_validation_script(class_names)
    
    # Run validation in container
    success, output = run_validation_container(image_tag, validation_script)
    
    # Check if validation actually passed by examining output
    # The script exits with 0 on success, non-zero on failure
    if not success or "Validation failed" in output or "not registered" in output:
        error_msg = f"Validation failed for image {image_tag}:\n{output}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    
    logger.info(f"Validation successful for {len(class_names)} model classes")
    return True


def generate_validation_script(class_names: List[str]) -> str:
    """
    Generate Python script to validate model registrations.
    
    Args:
        class_names: List of class names to validate
        
    Returns:
        Python script as string
    """
    # Build validation checks
    checks = []
    for class_name in class_names:
        checks.append(
            f'    assert "{class_name}" in ModelRegistry.models, '
            f'"Model class {class_name} not registered in ModelRegistry"'
        )
    
    # Use configured import path for model registry
    registry_import = settings.model_registry_import_path
    
    script = f"""
import sys
from {registry_import} import ModelRegistry

try:
{chr(10).join(checks)}
    print("All model classes are registered successfully")
    sys.exit(0)
except AssertionError as e:
    print(f"Validation failed: {{e}}")
    sys.exit(1)
except Exception as e:
    print(f"Unexpected error during validation: {{e}}")
    sys.exit(1)
"""
    return script.strip()
