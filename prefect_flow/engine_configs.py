"""
Per-engine configuration for Prefect multi-engine build.

Each engine runs the existing main.py with its own env overrides.
Output dirs: /output/vllm, /output/vllm_ascend, /output/sglang, /output/mindie.
"""

from typing import Dict

# Engine id -> output subdir under the flow's output_root (e.g. /output)
ENGINE_OUTPUT_SUBDIRS: Dict[str, str] = {
    "vllm": "vllm",
    "vllm_ascend": "vllm_ascend",
    "sglang": "sglang",
    "mindie": "mindie",
}

# Engine id -> env vars to set when running main.py (override or extend base env)
# Fill in real GITHUB_* / DOCKERHUB_* for each engine; GITHUB_TOKEN can come from base env.
ENGINE_ENV_OVERRIDES: Dict[str, Dict[str, str]] = {
    "vllm": {
        "ENGINE_NAME": "vllm",
        "GITHUB_REPO_OWNER": "vllm-project",
        "GITHUB_REPO_NAME": "vllm",
        "DOCKERHUB_REPOSITORY": "vllm/vllm-openai",
        "MODEL_REGISTRY_IMPORT_PATH": "vllm.model_executor.models",
        "OUTPUT_FILE_PREFIX": "vllm",
        "GIT_REPO_URL": "https://github.com/vllm-project/vllm.git",
    },
    "vllm_ascend": {
        "ENGINE_NAME": "vllm-ascend",
        "GITHUB_REPO_OWNER": "vllm-project",
        "GITHUB_REPO_NAME": "vllm-ascend",
        "DOCKERHUB_REPOSITORY": "vllm/vllm-ascend",
        "MODEL_REGISTRY_IMPORT_PATH": "vllm.model_executor.models",
        "OUTPUT_FILE_PREFIX": "vllm-ascend",
        "GIT_REPO_URL": "https://github.com/vllm-project/vllm-ascend.git",
    },
    "sglang": {
        "ENGINE_NAME": "sglang",
        "GITHUB_REPO_OWNER": "sgl-project",
        "GITHUB_REPO_NAME": "sglang",
        "DOCKERHUB_REPOSITORY": "sgl-project/sglang",
        "MODEL_REGISTRY_IMPORT_PATH": "sglang.model_executor.models",
        "OUTPUT_FILE_PREFIX": "sglang",
        "GIT_REPO_URL": "https://github.com/sgl-project/sglang.git",
    },
    "mindie": {
        "ENGINE_NAME": "mindie",
        "GITHUB_REPO_OWNER": "mindspore-lab",
        "GITHUB_REPO_NAME": "mindie",
        "DOCKERHUB_REPOSITORY": "mindspore/mindie",
        "MODEL_REGISTRY_IMPORT_PATH": "mindie.models",
        "OUTPUT_FILE_PREFIX": "mindie",
        "GIT_REPO_URL": "https://github.com/mindspore-lab/mindie.git",
    },
}

# Ordered list of engines to run in parallel
ENGINE_IDS = list(ENGINE_OUTPUT_SUBDIRS.keys())
