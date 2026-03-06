"""Error handling and notification module."""
import requests
from typing import Optional, Dict, Any

from config import settings
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


def send_error_notification(
    step: str,
    error_message: str,
    context: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Send error notification to App via webhook.
    
    Args:
        step: Step name where error occurred
        error_message: Error message
        context: Additional context (e.g., sha_m, sha_n, model_name)
        
    Returns:
        True if notification sent successfully, False otherwise
    """
    if not settings.app_webhook_url:
        logger.warning("No webhook URL configured, skipping notification")
        return False
    
    payload = {
        "step": step,
        "error": error_message,
        "context": context or {}
    }
    
    headers = {}
    if settings.app_api_key:
        headers["Authorization"] = f"Bearer {settings.app_api_key}"
    
    try:
        response = requests.post(
            settings.app_webhook_url,
            json=payload,
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        
        logger.info(f"Error notification sent successfully for step: {step}")
        return True
        
    except requests.RequestException as e:
        logger.error(f"Failed to send error notification: {e}")
        return False


def handle_error(
    step: str,
    error: Exception,
    context: Optional[Dict[str, Any]] = None
) -> None:
    """
    Handle error: log and send notification.
    
    Args:
        step: Step name where error occurred
        error: Exception object
        context: Additional context
    """
    error_message = str(error)
    logger.error(f"Error in {step}: {error_message}")
    
    # Send notification
    send_error_notification(step, error_message, context)
    
    # Re-raise to allow caller to handle cleanup
    raise
