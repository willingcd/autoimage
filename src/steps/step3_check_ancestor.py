"""Step 3: Check if sha-m is an ancestor of sha-n."""
from pathlib import Path
from typing import Optional

from src.utils.github_api import GitHubAPI
from src.utils.git_utils import ensure_repo_cloned, is_ancestor, validate_commit_sha
from src.utils.logger import setup_logger
from config import settings

logger = setup_logger(__name__)


def check_ancestor_relationship(sha_m: str, sha_n: str, use_api: bool = True) -> bool:
    """
    Check if sha-m is an ancestor of sha-n.
    
    Uses GitHub API by default (fast, no clone needed).
    Falls back to git merge-base if API fails.
    
    Args:
        sha_m: Potential ancestor commit SHA
        sha_n: Potential descendant commit SHA
        use_api: If True, use GitHub API (default). If False, use git merge-base.
        
    Returns:
        True if sha_m is an ancestor of sha_n, False otherwise
        
    Raises:
        RuntimeError: If commits are invalid or check fails
    """
    logger.info(f"Checking if {sha_m} is an ancestor of {sha_n}")
    
    if use_api:
        try:
            # Use GitHub API (fast, no clone needed)
            github_api = GitHubAPI()
            comparison = github_api.compare_commits(sha_m, sha_n)
            
            status = comparison.get("status", "")
            
            # status meanings:
            # - "ahead": sha_n is ahead of sha_m (sha_m is ancestor) → True
            # - "behind": sha_n is behind sha_m (sha_m is not ancestor) → False
            # - "identical": same commit → True
            # - "diverged": diverged (neither is ancestor) → False
            is_ancestor_result = status in ("ahead", "identical")
            
            logger.info(
                f"GitHub API compare result: status={status}, "
                f"{sha_m} {'IS' if is_ancestor_result else 'IS NOT'} "
                f"an ancestor of {sha_n}"
            )
            
            return is_ancestor_result
            
        except Exception as e:
            logger.warning(
                f"GitHub API compare failed: {e}, "
                f"falling back to git merge-base..."
            )
            # Fall through to git merge-base method
    
    # Fallback: Use git merge-base (requires clone)
    logger.info("Using git merge-base method (requires local repository)...")
    # Pass required SHAs to ensure they are fetched if not present
    repo_path = ensure_repo_cloned(required_shas=[sha_m, sha_n])
    
    # Validate both commits exist
    if not validate_commit_sha(repo_path, sha_m):
        raise RuntimeError(f"Invalid commit SHA: {sha_m}")
    
    if not validate_commit_sha(repo_path, sha_n):
        raise RuntimeError(f"Invalid commit SHA: {sha_n}")
    
    # Check ancestor relationship
    result = is_ancestor(repo_path, sha_m, sha_n)
    
    logger.info(
        f"Ancestor check result: {sha_m} {'IS' if result else 'IS NOT'} "
        f"an ancestor of {sha_n}"
    )
    
    return result
