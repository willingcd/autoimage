"""Git utilities for repository operations."""
import subprocess
import shutil
from pathlib import Path
from typing import Optional

from git import Repo, GitCommandError
from git.exc import InvalidGitRepositoryError

from config import settings
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


def ensure_repo_cloned(
    repo_url: Optional[str] = None, 
    clone_dir: Optional[Path] = None,
    required_shas: Optional[list[str]] = None
) -> Path:
    """
    Ensure the repository is cloned locally and up-to-date.
    
    Args:
        repo_url: Git repository URL. If None, uses settings.git_repo_url
        clone_dir: Directory to clone to. If None, uses settings.git_repo_clone_dir
        required_shas: List of commit SHAs that must be available. If provided,
                       will fetch until these commits are available.
        
    Returns:
        Path to the cloned repository
    """
    repo_url = repo_url or settings.git_repo_url
    clone_dir = Path(clone_dir or settings.git_repo_clone_dir)
    
    # Check if already cloned
    if clone_dir.exists() and (clone_dir / ".git").exists():
        try:
            repo = Repo(clone_dir)
            logger.info(f"Repository already exists at {clone_dir}")
            
            # If required SHAs are provided, check if they exist
            if required_shas:
                missing_shas = []
                for sha in required_shas:
                    try:
                        repo.commit(sha)
                    except (ValueError, GitCommandError):
                        missing_shas.append(sha)
                
                if missing_shas:
                    logger.info(
                        f"Required commits not found locally: {missing_shas}, "
                        f"fetching from remote..."
                    )
                    # Fetch with depth to get the missing commits
                    # Try fetching specific commits first
                    for sha in missing_shas:
                        try:
                            repo.remotes.origin.fetch(f"+{sha}:refs/remotes/origin/{sha}")
                        except GitCommandError:
                            pass  # If specific fetch fails, will do full fetch
                    
                    # Full fetch to ensure we have all needed commits
                    repo.remotes.origin.fetch()
                    
                    # Verify again
                    still_missing = []
                    for sha in missing_shas:
                        try:
                            repo.commit(sha)
                        except (ValueError, GitCommandError):
                            still_missing.append(sha)
                    
                    if still_missing:
                        logger.warning(
                            f"Some commits still not found after fetch: {still_missing}. "
                            f"This may indicate they don't exist in the repository."
                        )
                else:
                    logger.info("All required commits are available locally")
            else:
                # No specific SHAs required, just fetch latest changes
                logger.info("Fetching latest changes from remote...")
                repo.remotes.origin.fetch()
            
            return clone_dir
        except (InvalidGitRepositoryError, GitCommandError) as e:
            logger.warning(f"Existing directory is not a valid git repo: {e}, re-cloning...")
            shutil.rmtree(clone_dir)
    
    # Clone repository
    logger.info(f"Cloning repository {repo_url} to {clone_dir}...")
    clone_dir.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        repo = Repo.clone_from(repo_url, clone_dir)
        logger.info(f"Repository cloned successfully to {clone_dir}")
        
        # If required SHAs are provided, verify they exist
        if required_shas:
            missing_shas = []
            for sha in required_shas:
                try:
                    repo.commit(sha)
                except (ValueError, GitCommandError):
                    missing_shas.append(sha)
            
            if missing_shas:
                logger.info(f"Fetching missing commits: {missing_shas}")
                repo.remotes.origin.fetch()
                
                # Verify again
                still_missing = []
                for sha in missing_shas:
                    try:
                        repo.commit(sha)
                    except (ValueError, GitCommandError):
                        still_missing.append(sha)
                
                if still_missing:
                    logger.warning(
                        f"Some commits not found after clone and fetch: {still_missing}"
                    )
        
        return clone_dir
    except GitCommandError as e:
        logger.error(f"Failed to clone repository: {e}")
        raise


def is_ancestor(repo_path: Path, ancestor_sha: str, descendant_sha: str) -> bool:
    """
    Check if ancestor_sha is an ancestor of descendant_sha.
    
    Args:
        repo_path: Path to the git repository
        ancestor_sha: SHA of the potential ancestor commit
        descendant_sha: SHA of the potential descendant commit
        
    Returns:
        True if ancestor_sha is an ancestor of descendant_sha, False otherwise
    """
    try:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor_sha, descendant_sha],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False
        )
        
        is_ancestor_result = (result.returncode == 0)
        logger.info(
            f"Ancestor check: {ancestor_sha} {'is' if is_ancestor_result else 'is not'} "
            f"ancestor of {descendant_sha}"
        )
        return is_ancestor_result
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to check ancestor relationship: {e}")
        raise
    except FileNotFoundError:
        logger.error("git command not found. Please ensure git is installed.")
        raise


def validate_commit_sha(repo_path: Path, sha: str) -> bool:
    """
    Validate that a commit SHA exists in the repository.
    
    Args:
        repo_path: Path to the git repository
        sha: Commit SHA to validate
        
    Returns:
        True if commit exists, False otherwise
    """
    try:
        repo = Repo(repo_path)
        repo.commit(sha)
        return True
    except (ValueError, GitCommandError):
        return False
