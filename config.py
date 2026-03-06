"""Configuration management for the build automation system."""
import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings."""
    
    # Inference Engine Configuration
    engine_name: str = "vllm"  # Inference engine name (e.g., vllm, tensorrt-llm, etc.)
    model_registry_import_path: str = "vllm.model_executor.models"  # Model registry import path
    output_file_prefix: str = "vllm"  # Prefix for output tar files
    
    # GitHub Configuration
    github_token: str
    github_repo_owner: str = "vllm-project"
    github_repo_name: str = "vllm"
    
    # Docker Configuration
    dockerhub_repository: str = "vllm/vllm-openai"  # Official DockerHub repository from engine vendor
    dockerhub_username: Optional[str] = None
    dockerhub_token: Optional[str] = None
    
    # App Notification
    app_webhook_url: Optional[str] = None
    app_api_key: Optional[str] = None
    
    # Git Repository
    git_repo_url: str = "https://github.com/vllm-project/vllm.git"
    git_repo_clone_dir: Path = Path("./.repo_cache")
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
