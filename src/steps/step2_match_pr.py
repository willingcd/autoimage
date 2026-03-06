"""Step 2: Match PR and parse model registrations."""
from typing import Dict, List, Optional

import requests

from config import settings
from src.utils.github_api import (
    GitHubAPI, 
    extract_registrations_from_pr,
    extract_search_model_name
)
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


def match_model_pr(model_id: str) -> Dict:
    """
    Match a PR related to the model and extract registrations.
    
    Uses strategy 1: exact match with support keywords / exclude bugfix.
    
    Args:
        model_id: Full model ID (e.g., "Qwen/Qwen3.5-35B-A3B-FP8")
        
    Returns:
        Dictionary with:
            - sha_m: Merge commit SHA
            - model_registrations: List of registration dicts with registration_key and class_name
            - pr_number: PR number
            
    Raises:
        RuntimeError: If no matching merged PR is found
    """
    github_api = GitHubAPI()
    
    # Step 1: Extract search model name from full model ID
    search_model_name = extract_search_model_name(model_id)
    logger.info(
        f"Extracted search model name: '{search_model_name}' from model ID: '{model_id}'"
    )
    
    # Step 2: Search PR using strategy 1 (exact match)
    pr_details = github_api.search_pr_by_model_name_exact(
        search_model_name, 
        full_model_id=model_id
    )
    
    if not pr_details:
        # Build detailed error message
        error_msg = (
            f"No merged PR found for model ID: {model_id}\n"
            f"  - Search model name: {search_model_name}\n"
            f"  - Tried strategy 1a: exact match with support keywords + [MODEL] prefix\n"
            f"  - Tried strategy 1b: exact match excluding bugfix + [MODEL] prefix\n"
            f"  - Please check if:\n"
            f"    1. The model ID is correct\n"
            f"    2. A PR supporting this model has been merged\n"
            f"    3. The PR title starts with [MODEL]\n"
            f"    4. The PR title contains the model name"
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    
    merge_commit_sha = pr_details.get("merge_commit_sha")
    pr_number = pr_details.get("number")
    
    if not merge_commit_sha:
        # Try to get merge commit SHA from PR commits
        logger.warning(f"PR #{pr_number} has no merge_commit_sha, trying to get from commits...")
        try:
            url = (
                f"https://api.github.com/repos/{settings.github_repo_owner}/"
                f"{settings.github_repo_name}/pulls/{pr_number}/commits"
            )
            response = requests.get(url, headers=github_api.headers, timeout=30)
            response.raise_for_status()
            commits = response.json()
            if commits:
                merge_commit_sha = commits[-1].get("sha")
                logger.info(f"Got merge commit SHA from commits: {merge_commit_sha}")
        except Exception as e:
            logger.error(f"Failed to get merge commit SHA: {e}")
            raise RuntimeError(
                f"PR #{pr_number} has no merge_commit_sha and failed to get from commits: {e}"
            )
    
    if not merge_commit_sha:
        raise RuntimeError(f"PR #{pr_number} has no merge commit SHA")
    
    pr_title = pr_details.get("title", "N/A")
    logger.info(
        f"Found merged PR #{pr_number} for model {model_id}:"
    )
    logger.info(f"  PR Title: {pr_title}")
    logger.info(f"  Merge SHA: {merge_commit_sha}")
    
    # Step 3: Extract model registrations from PR
    registrations = extract_registrations_from_pr(
        github_api,
        pr_number,
        merge_commit_sha
    )
    
    if not registrations:
        logger.warning(f"No model registrations found in PR #{pr_number}")
        # This might be okay if the PR doesn't modify registration files
        # But we'll still return empty list
    
    result = {
        "sha_m": merge_commit_sha,
        "model_registrations": registrations,
        "pr_number": pr_number
    }
    
    logger.info(
        f"Step 2 completed: sha_m={merge_commit_sha}, "
        f"found {len(registrations)} registrations"
    )
    
    return result
