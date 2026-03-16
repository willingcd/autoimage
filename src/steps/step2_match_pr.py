"""Step 2: Get latest merged PR and parse model registrations."""
from typing import Dict, List, Optional

import requests

from src.config import settings
from src.utils.github_api import GitHubAPI, extract_registrations_from_pr
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


def match_model_pr(model_id: str) -> Dict:
    """
    Get the latest merged PR (no name matching) and extract registrations.
    
    Args:
        model_id: Full model ID (e.g., "Qwen/Qwen3.5-35B-A3B-FP8"); kept for API compatibility, not used for matching.
        
    Returns:
        Dictionary with:
            - sha_m: Merge commit SHA
            - model_registrations: List of registration dicts with registration_key and class_name
            - pr_number: PR number
            
    Raises:
        RuntimeError: If no merged PR is found
    """
    github_api = GitHubAPI()
    
    logger.info("Step 2: Fetching latest merged PR (no name matching)")
    
    pr_details = github_api.get_latest_merged_pr()
    
    if not pr_details:
        error_msg = (
            "No merged PR found in the repository.\n"
            "  - Only closed-and-merged PRs are considered.\n"
            "  - Please ensure at least one PR has been merged."
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
    logger.info(f"Found latest merged PR #{pr_number}:")
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
