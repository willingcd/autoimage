"""Per-engine configuration loaded from config_engine.yaml.

This module is the single source of truth for engine-specific settings,
such as GitHub repo, Docker repository, model registry import path, etc.

Code that needs engine information should use EngineConfig / get_engine_config
instead of hard-coding values.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import yaml


@dataclass(frozen=True)
class EngineConfig:
    engine_name: str
    github_repo_owner: str
    github_repo_name: str
    dockerhub_repository: str
    model_registry_import_path: str
    output_file_prefix: str
    git_repo_url: str


_ENGINE_CONFIG_PATH = Path(__file__).resolve().parent / "config_engine.yaml"
_ENGINE_CACHE: Dict[str, EngineConfig] | None = None


def _load_all_engine_configs() -> Dict[str, EngineConfig]:
    global _ENGINE_CACHE
    if _ENGINE_CACHE is not None:
        return _ENGINE_CACHE

    if not _ENGINE_CONFIG_PATH.exists():
        raise FileNotFoundError(f"Engine config file not found: {_ENGINE_CONFIG_PATH}")

    raw = yaml.safe_load(_ENGINE_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    engine_map: Dict[str, EngineConfig] = {}
    for engine_id, cfg in raw.items():
        engine_map[engine_id] = EngineConfig(**cfg)

    _ENGINE_CACHE = engine_map
    return _ENGINE_CACHE


def get_engine_config(engine_id: str) -> EngineConfig:
    """Return EngineConfig for a given engine_id (e.g. 'vllm', 'vllm-ascend')."""
    all_cfgs = _load_all_engine_configs()
    if engine_id not in all_cfgs:
        available = ", ".join(sorted(all_cfgs.keys()))
        raise KeyError(f"Unknown engine_id={engine_id!r}. Available: {available}")
    return all_cfgs[engine_id]


