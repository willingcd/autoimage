"""GitHub API utilities."""
import re
from typing import Optional, List, Dict, Any

import requests

from config import settings
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

GITHUB_API_BASE = "https://api.github.com"


def extract_search_model_name(full_model_id: str) -> str:
    """
    从完整的模型 ID 中提取用于 GitHub 搜索的模型名关键词。
    去除尺寸信息（如 35B, 122B, 9B）、dtype 信息（如 FP8, FP16, INT8, A3B, A10B 等）
    以及常见标签（如 -Base, -Chat, -Instruct, -Code 等），
    保留变体信息（如 -VL, -Vision 等）。
    
    Examples:
        - Qwen/Qwen2.5-VL -> Qwen2.5-VL（保留 -VL）
        - Qwen/Qwen3.5-0.8B-Base -> Qwen3.5（去除 0.8B, -Base）
        - Qwen/Qwen3.5-35B-A3B-FP8 -> Qwen3.5（去除 35B, -A3B-FP8）
        - Qwen/Qwen3.5-122B-A10B -> Qwen3.5（去除 122B, -A10B）
        - Qwen/Qwen3.5-35B-FP16 -> Qwen3.5（去除 35B, -FP16）
        - Qwen/Qwen3.5-35B -> Qwen3.5（去除 35B）
        - deepseek-ai/DeepSeek-V3 -> DeepSeek-V3（无尺寸/dtype 信息，保留完整）
        - ZhipuAI/GLM-5-9B -> GLM-5（去除 9B）
    
    Args:
        full_model_id: 完整模型 ID，如 "Qwen/Qwen3.5-35B-A3B-FP8"
        
    Returns:
        提取后的搜索关键词，如 "Qwen3.5"
    """
    # 取出 repo 名称部分
    name = full_model_id.split("/")[-1] if "/" in full_model_id else full_model_id

    # 去除尺寸信息（形如 35B, 122B, 9B, 0.8B, 1.5B, 70B 等）
    # 匹配模式：数字（可选小数）+ B（可能大小写）
    size_pattern = r"-\d+(?:\.\d+)?[Bb]"
    name = re.sub(size_pattern, "", name)

    # 去除开头的尺寸信息（如果模型名以尺寸开头，如 "9B-GLM-5"）
    name = re.sub(r"^\d+(?:\.\d+)?[Bb]-", "", name)

    # 去除 dtype 信息（形如 FP8, FP16, FP32, FP64, FP4, INT8, INT4, BF16 等）
    # 匹配模式：-FP8, -FP16, -INT8, -BF16 等（大小写不敏感）
    dtype_patterns = [
        r"-FP\d+",  # FP8, FP16, FP32, FP64, FP4
        r"-fp\d+",  # fp8, fp16, fp32, fp64, fp4
        r"-INT\d+",  # INT8, INT4, INT16
        r"-int\d+",  # int8, int4, int16
        r"-BF\d+",  # BF16
        r"-bf\d+",  # bf16
        r"-A\d+[Bb]",  # A3B, A10B（量化相关）
        r"-a\d+[Bb]",  # a3b, a10b
    ]
    for pattern in dtype_patterns:
        name = re.sub(pattern, "", name, flags=re.IGNORECASE)

    # 去除量化相关后缀（GPTQ, AWQ, GGUF, GGML, Q4, Q8 等）
    # 这些是模型量化格式，在搜索 PR 时不需要
    quantization_patterns = [
        r"-GPTQ$",      # GPTQ
        r"-gptq$",      # gptq
        r"-AWQ$",       # AWQ
        r"-awq$",       # awq
        r"-GGUF$",      # GGUF
        r"-gguf$",      # gguf
        r"-GGML$",      # GGML
        r"-ggml$",      # ggml
        r"-Q\d+$",      # Q4, Q8, Q16 等量化位数
        r"-q\d+$",      # q4, q8, q16
    ]
    for pattern in quantization_patterns:
        name = re.sub(pattern, "", name, flags=re.IGNORECASE)

    # 去除常见标签（如 -Base, -Chat, -Instruct, -Code 等）
    # 这些标签通常表示模型变体类型，但在搜索 PR 时不需要
    label_patterns = [
        r"-Base$",      # -Base
        r"-base$",      # -base
        r"-Chat$",      # -Chat
        r"-chat$",      # -chat
        r"-Instruct$",  # -Instruct
        r"-instruct$",  # -instruct
        r"-Code$",      # -Code
        r"-code$",      # -code
    ]
    for pattern in label_patterns:
        name = re.sub(pattern, "", name, flags=re.IGNORECASE)

    return name


class GitHubAPI:
    """GitHub API client."""
    
    def __init__(self, token: Optional[str] = None):
        self.token = token or settings.github_token
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }
    
    def _is_model_support_pr(self, pr: Dict) -> bool:
        """
        判断 PR 是否是添加新模型支持的 PR（而非 bugfix）。
        
        Args:
            pr: PR 字典（包含 title 等信息）
            
        Returns:
            True 如果是模型支持 PR，False 如果是纯 bugfix
        """
        title = pr.get("title", "").lower()

        # 排除明显的 bugfix
        bugfix_keywords = ["bugfix", "[bugfix]", "fix:", "fixes", "bug:", "[bug]"]
        for keyword in bugfix_keywords:
            if keyword in title:
                # 如果标题同时包含支持关键词，可能是修复新模型支持的 bug
                support_keywords = ["support", "add", "implement", "new model"]
                if any(kw in title for kw in support_keywords):
                    return True
                return False

        # 优先匹配包含支持关键词的 PR
        support_keywords = ["support", "add", "implement", "new model", "model support"]
        if any(kw in title for kw in support_keywords):
            return True

        return True  # 其他情况，保留（可能是模型相关）
    
    def _pr_supports_model_variant(self, pr_details: Dict, full_model_id: str) -> bool:
        """
        检查 PR 是否真的支持这个具体的模型变体（简单验证）。
        
        Args:
            pr_details: PR 详细信息
            full_model_id: 完整模型 ID
            
        Returns:
            True 如果 PR 可能支持该模型变体
        """
        title = pr_details.get("title", "").lower()
        body = pr_details.get("body", "").lower()
        full_text = f"{title} {body}"

        # 提取搜索用的模型名（已去除尺寸，保留变体）
        search_model_name = extract_search_model_name(full_model_id).lower()

        # 检查 PR 中是否包含模型名（允许部分匹配）
        model_parts = search_model_name.split("-")
        base_name = model_parts[0]  # 基础名，如 "qwen3.5"

        # 如果 PR 明确提到完整模型名，认为支持
        if search_model_name in full_text:
            return True

        # 如果 PR 提到基础名，检查是否也提到了变体部分
        if base_name in full_text:
            if len(model_parts) > 1:
                # 有变体，检查 PR 是否提到变体关键词
                variant_parts = model_parts[1:]
                variant_keywords = ["vl", "vision", "multimodal", "audio", "a3b", "a10b", "fp8", "fp16"]
                # 检查变体部分是否在 PR 中出现
                if any(part in full_text for part in variant_parts if part in variant_keywords or len(part) <= 5):
                    return True
                # 如果变体部分很短（如 A3B），直接检查是否在 PR 中
                if any(part in full_text for part in variant_parts):
                    return True
            else:
                # 没有变体，只提到基础名就认为支持
                return True

        return False
    
    def search_prs(self, query: str, state: str = "closed") -> List[Dict[str, Any]]:
        """
        Search for pull requests.
        
        Args:
            query: Search query (e.g., "qwen3 model")
            state: PR state (open, closed, all). Only 'closed' with merged=true are valid.
            
        Returns:
            List of PR dictionaries
        """
        url = f"{GITHUB_API_BASE}/search/issues"
        params = {
            "q": f"repo:{settings.github_repo_owner}/{settings.github_repo_name} "
                 f"type:pr state:{state} {query}",
            "sort": "updated",
            "order": "desc",
            "per_page": 10
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            prs = data.get("items", [])
            
            logger.info(f"Found {len(prs)} PRs matching query: {query}")
            return prs
            
        except requests.RequestException as e:
            logger.error(f"Failed to search PRs: {e}")
            raise
    
    def search_pr_by_model_name_exact(
        self, 
        search_model_name: str, 
        full_model_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        策略1：模型名精确匹配（标题）+ 只匹配 [MODEL] 开头的 PR + 排除 bugfix + 优先支持关键词。
        
        Args:
            search_model_name: 预处理后的搜索模型名（如 "Qwen3.5"）
            full_model_id: 完整模型 ID（用于验证变体支持，可选）
            
        Returns:
            PR 详细信息字典，包含 merge_commit_sha，如果未找到返回 None
        """
        # 策略1a：先尝试包含支持关键词的搜索，只匹配 [MODEL] 开头的 PR
        query_1a = (
            f'in:title "[MODEL]" AND "{search_model_name}" AND ("support" OR "add" OR "implement" OR "new model")'
        )
        logger.info(f"[PR搜索-策略1a] 精确匹配+支持关键词+[MODEL]前缀: {query_1a}")
        prs = self.search_prs(query_1a, state="closed")
        
        for pr in prs:
            pr_title = pr.get("title", "N/A")
            logger.info(f"[PR搜索-策略1a] 候选 PR #{pr.get('number')}: {pr_title}")
            
            # 检查 PR 标题是否以 [MODEL] 开头
            if not pr_title.startswith("[MODEL]"):
                logger.debug(f"PR #{pr.get('number')} 标题不以 [MODEL] 开头，跳过")
                continue
            
            if pr.get("pull_request", {}).get("merged_at") and self._is_model_support_pr(pr):
                pr_details = self.get_pr_details(pr["number"])
                if pr_details and pr_details.get("merge_commit_sha"):
                    # 如果提供了完整模型ID，进行简单验证
                    if full_model_id and not self._pr_supports_model_variant(pr_details, full_model_id):
                        logger.warning(
                            f"PR #{pr_details.get('number')} ({pr_details.get('title', 'N/A')}) "
                            f"可能不支持模型变体 {full_model_id}，继续搜索..."
                        )
                        continue
                    logger.info(
                        f"[PR搜索-策略1a] ✓ 找到匹配的 PR: "
                        f"#{pr_details.get('number', 'unknown')} - {pr_details.get('title', 'N/A')}"
                    )
                    return pr_details

        # 策略1b：如果没找到，尝试排除 bugfix 的搜索，只匹配 [MODEL] 开头的 PR
        query_1b = (
            f'in:title "[MODEL]" AND "{search_model_name}" -"bugfix" -"[bugfix]" -"fix:"'
        )
        logger.info(f"[PR搜索-策略1b] 精确匹配-排除bugfix+[MODEL]前缀: {query_1b}")
        prs = self.search_prs(query_1b, state="closed")
        
        for pr in prs:
            pr_title = pr.get("title", "N/A")
            logger.info(f"[PR搜索-策略1b] 候选 PR #{pr.get('number')}: {pr_title}")
            
            # 检查 PR 标题是否以 [MODEL] 开头
            if not pr_title.startswith("[MODEL]"):
                logger.debug(f"PR #{pr.get('number')} 标题不以 [MODEL] 开头，跳过")
                continue
            
            if pr.get("pull_request", {}).get("merged_at") and self._is_model_support_pr(pr):
                pr_details = self.get_pr_details(pr["number"])
                if pr_details and pr_details.get("merge_commit_sha"):
                    # 如果提供了完整模型ID，进行简单验证
                    if full_model_id and not self._pr_supports_model_variant(pr_details, full_model_id):
                        logger.warning(
                            f"PR #{pr_details.get('number')} ({pr_details.get('title', 'N/A')}) "
                            f"可能不支持模型变体 {full_model_id}，继续搜索..."
                        )
                        continue
                    logger.info(
                        f"[PR搜索-策略1b] ✓ 找到匹配的 PR: "
                        f"#{pr_details.get('number', 'unknown')} - {pr_details.get('title', 'N/A')}"
                    )
                    return pr_details

        return None
    
    def get_latest_merged_pr(self) -> Optional[Dict[str, Any]]:
        """
        Get the latest merged PR in the repo (no title/name matching).
        Uses list pulls with state=closed, then filters by merged_at and returns the most recent.

        Returns:
            PR details dict including merge_commit_sha, or None if no merged PR found.
        """
        url = f"{GITHUB_API_BASE}/repos/{settings.github_repo_owner}/{settings.github_repo_name}/pulls"
        params = {
            "state": "closed",
            "sort": "updated",
            "direction": "desc",
            "per_page": 50,
        }
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            closed_prs = response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to list closed PRs: {e}")
            raise

        merged = [pr for pr in closed_prs if pr.get("merged_at")]
        if not merged:
            logger.warning("No merged PRs found in recent closed PRs")
            return None

        # Sort by merged_at descending (latest first)
        merged.sort(key=lambda pr: pr["merged_at"], reverse=True)
        latest = merged[0]
        pr_number = latest["number"]
        pr_details = self.get_pr_details(pr_number)
        if not pr_details.get("merge_commit_sha"):
            logger.warning(f"PR #{pr_number} has no merge_commit_sha, skipping")
            return None
        return pr_details

    def get_pr_details(self, pr_number: int) -> Dict[str, Any]:
        """
        Get detailed information about a PR.
        
        Args:
            pr_number: PR number
            
        Returns:
            PR details dictionary
        """
        url = f"{GITHUB_API_BASE}/repos/{settings.github_repo_owner}/{settings.github_repo_name}/pulls/{pr_number}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get PR details: {e}")
            raise
    
    def get_pr_files(self, pr_number: int) -> List[Dict[str, Any]]:
        """
        Get files changed in a PR.
        
        Args:
            pr_number: PR number
            
        Returns:
            List of file change dictionaries
        """
        url = f"{GITHUB_API_BASE}/repos/{settings.github_repo_owner}/{settings.github_repo_name}/pulls/{pr_number}/files"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get PR files: {e}")
            raise
    
    def compare_commits(self, base_sha: str, head_sha: str) -> Dict[str, Any]:
        """
        Compare two commits using GitHub API.
        
        Args:
            base_sha: Base commit SHA (potential ancestor)
            head_sha: Head commit SHA (potential descendant)
            
        Returns:
            Comparison result dictionary with 'status' field:
            - 'ahead': head is ahead of base (base is ancestor)
            - 'behind': head is behind base (base is not ancestor)
            - 'identical': same commit
            - 'diverged': diverged (neither is ancestor)
        """
        url = f"{GITHUB_API_BASE}/repos/{settings.github_repo_owner}/{settings.github_repo_name}/compare/{base_sha}...{head_sha}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to compare commits: {e}")
            raise
    
    def get_file_content(self, file_path: str, ref: str = "main") -> str:
        """
        Get file content from repository.
        
        Args:
            file_path: Path to file in repository
            ref: Git reference (branch, tag, or SHA)
            
        Returns:
            File content as string
        """
        url = f"{GITHUB_API_BASE}/repos/{settings.github_repo_owner}/{settings.github_repo_name}/contents/{file_path}"
        params = {"ref": ref}
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            import base64
            content = base64.b64decode(data["content"]).decode("utf-8")
            return content
            
        except requests.RequestException as e:
            logger.error(f"Failed to get file content: {e}")
            raise


def parse_model_registrations(content: str) -> List[Dict[str, str]]:
    """
    Parse model registrations from __init__.py or registry.py file.
    
    Expected format:
        "model_name": ("file.py", "ClassName"),
    
    Args:
        content: File content
        
    Returns:
        List of registration dictionaries with 'registration_key' and 'class_name'
    """
    registrations = []
    
    # Pattern to match: "key": ("file.py", "ClassName"),
    pattern = r'["\'](\w+)["\']:\s*\(["\']([^"\']+)["\'],\s*["\'](\w+)["\']\)'
    
    matches = re.finditer(pattern, content)
    for match in matches:
        registration_key = match.group(1)
        file_name = match.group(2)
        class_name = match.group(3)
        
        registrations.append({
            "registration_key": registration_key,
            "file_name": file_name,
            "class_name": class_name
        })
    
    logger.info(f"Parsed {len(registrations)} model registrations")
    return registrations


def extract_registrations_from_pr(
    github_api: GitHubAPI,
    pr_number: int,
    merge_sha: str
) -> List[Dict[str, str]]:
    """
    Extract model registrations from PR's changed files.
    
    Args:
        github_api: GitHubAPI instance
        pr_number: PR number
        merge_sha: Merge commit SHA
        
    Returns:
        List of registration dictionaries
    """
    # Get changed files
    files = github_api.get_pr_files(pr_number)
    
    # Find registration files
    registration_files = [
        f for f in files
        if f["filename"].endswith("__init__.py") or "registry" in f["filename"].lower()
    ]
    
    all_registrations = []
    
    for file_info in registration_files:
        file_path = file_info["filename"]
        
        # Get file content at merge commit
        try:
            content = github_api.get_file_content(file_path, ref=merge_sha)
            registrations = parse_model_registrations(content)
            
            # Filter registrations that were added/modified in this PR
            # (This is a simplified check - in reality, you'd parse the diff)
            for reg in registrations:
                # Check if this registration appears in the diff
                if file_info.get("status") in ("added", "modified"):
                    all_registrations.append(reg)
                    
        except Exception as e:
            logger.warning(f"Failed to parse registrations from {file_path}: {e}")
            continue
    
    logger.info(f"Extracted {len(all_registrations)} registrations from PR #{pr_number}")
    return all_registrations
