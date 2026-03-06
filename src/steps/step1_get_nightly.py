"""Step 1: Get latest nightly build SHA (sha-n)."""
import re
import requests
from typing import Optional

from config import settings
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


def get_nightly_sha_from_dockerhub() -> Optional[str]:
    """
    Get the latest nightly build SHA from DockerHub manifest.
    
    Returns:
        SHA string (e.g., "abc1234") or None if not found
    """
    repository = settings.dockerhub_repository
    # DockerHub API endpoint for tags
    url = f"https://hub.docker.com/v2/repositories/{repository}/tags"
    
    try:
        logger.info(f"Fetching tags from DockerHub: {repository}")
        
        # Fetch tags (may need pagination for large repos)
        all_tags = []
        next_url = url
        
        while next_url:
            response = requests.get(next_url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            tags = data.get("results", [])
            all_tags.extend(tags)
            
            next_url = data.get("next")
            if not next_url:
                break
        
        # Filter nightly tags and extract SHA
        nightly_pattern = re.compile(r"^nightly-([a-f0-9]{7,})$")
        nightly_shas = []
        
        for tag in all_tags:
            tag_name = tag.get("name", "")
            match = nightly_pattern.match(tag_name)
            if match:
                sha = match.group(1)
                # Get last updated time for sorting
                last_updated = tag.get("last_updated")
                nightly_shas.append((sha, last_updated, tag_name))
        
        if not nightly_shas:
            logger.warning("No nightly tags found in DockerHub")
            return None
        
        # Sort by last_updated (most recent first)
        nightly_shas.sort(key=lambda x: x[1] or "", reverse=True)
        latest_sha = nightly_shas[0][0]
        latest_tag = nightly_shas[0][2]
        
        logger.info(f"Found latest nightly build: {latest_tag} (SHA: {latest_sha})")
        return latest_sha
        
    except requests.RequestException as e:
        logger.error(f"Failed to fetch tags from DockerHub: {e}")
        return None


def get_nightly_sha() -> str:
    """
    Get the latest nightly build SHA.
    Tries DockerHub first, falls back to other methods if needed.
    
    Returns:
        SHA string
        
    Raises:
        RuntimeError: If unable to get SHA from any source
    """
    sha = get_nightly_sha_from_dockerhub()
    
    if sha:
        return sha
    
    # Future: Add fallback methods here (e.g., Buildkite API)
    raise RuntimeError("Failed to get nightly build SHA from all available sources")
