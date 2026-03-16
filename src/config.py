"""Configuration management for the build automation system.

This project intentionally avoids Pydantic BaseSettings and dotenv loaders.
Configuration is loaded strictly from environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .engine_config import get_engine_config


def _getenv(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name, default)
    if value is None:
        return None
    value = value.strip()
    return value if value != "" else None


def _getenv_bool(name: str, default: bool = False) -> bool:
    raw = _getenv(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "y", "on")


def _getenv_int(name: str, default: int) -> int:
    raw = _getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as e:
        raise RuntimeError(f"Invalid int for {name}: {raw}") from e


def _getenv_path(name: str, default: Path) -> Path:
    raw = _getenv(name)
    if raw is None:
        return default
    return Path(raw)


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables.

    NOTE: Engine-specific fields (engine_name, dockerhub_repository, etc.)
    are driven by src/engine_config.py and can be overridden by env vars.
    """

    # Engine / repo / Docker configuration
    engine_name: str
    model_registry_import_path: str
    output_file_prefix: str

    github_token: str
    github_repo_owner: str
    github_repo_name: str

    dockerhub_repository: str
    dockerhub_username: Optional[str]
    dockerhub_token: Optional[str]

    git_repo_url: str
    git_repo_clone_dir: Path

    # App Notification
    app_webhook_url: Optional[str]
    app_api_key: Optional[str]

    # Logging
    log_level: str

    @staticmethod
    def from_env() -> "Settings":
        github_token = _getenv("GITHUB_TOKEN")
        if not github_token:
            raise RuntimeError(
                "Missing required env var: GITHUB_TOKEN. "
                "Please set it in your environment or .env file."
            )

        # Determine engine name first (for engine-specific config via config_engine.yaml)
        engine_name = _getenv("ENGINE_NAME", "vllm") or "vllm"
        engine_cfg = get_engine_config(engine_name)

        return Settings(
            engine_name=engine_name,
            model_registry_import_path=_getenv(
                "MODEL_REGISTRY_IMPORT_PATH",
                engine_cfg.model_registry_import_path,
            )
            or engine_cfg.model_registry_import_path,
            output_file_prefix=_getenv(
                "OUTPUT_FILE_PREFIX",
                engine_cfg.output_file_prefix,
            )
            or engine_cfg.output_file_prefix,
            github_token=github_token,
            github_repo_owner=_getenv(
                "GITHUB_REPO_OWNER",
                engine_cfg.github_repo_owner,
            )
            or engine_cfg.github_repo_owner,
            github_repo_name=_getenv(
                "GITHUB_REPO_NAME",
                engine_cfg.github_repo_name,
            )
            or engine_cfg.github_repo_name,
            dockerhub_repository=_getenv(
                "DOCKERHUB_REPOSITORY",
                engine_cfg.dockerhub_repository,
            )
            or engine_cfg.dockerhub_repository,
            dockerhub_username=_getenv("DOCKERHUB_USERNAME"),
            dockerhub_token=_getenv("DOCKERHUB_TOKEN"),
            git_repo_url=_getenv("GIT_REPO_URL", engine_cfg.git_repo_url)
            or engine_cfg.git_repo_url,
            git_repo_clone_dir=_getenv_path("GIT_REPO_CLONE_DIR", Path("./.repo_cache")),
            app_webhook_url=_getenv("APP_WEBHOOK_URL"),
            app_api_key=_getenv("APP_API_KEY"),
            log_level=_getenv("LOG_LEVEL", "INFO") or "INFO",
        )


# Global settings instance
settings = Settings.from_env()
