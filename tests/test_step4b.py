#!/usr/bin/env python3
"""
测试脚本：测试 Step 4-B (Docker Build) 功能

使用方法：
    python tests/test_step4b.py --sha-m <merge_commit_sha> --sha-n <nightly_sha> --pr-number <pr_number>
    
或者使用默认测试数据：
    python tests/test_step4b.py
"""

import sys
import argparse
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.steps.step4_docker_ops import docker_build_custom, generate_dockerfile
from src.utils.github_api import GitHubAPI
from src.utils.logger import setup_logger
from config import settings

logger = setup_logger(__name__)


def test_step4b(
    sha_m: str,
    sha_n: str,
    pr_number: int,
    dry_run: bool = False,
    model_key: str = "test-model",
):
    """
    测试 Step 4-B: Docker Build
    
    Args:
        sha_m: PR merge commit SHA
        sha_n: Nightly build SHA
        pr_number: PR number
        dry_run: 如果为 True，只生成 Dockerfile 不实际构建
        model_key: 用于命名的模型 key（测试环境下可随意指定）
    """
    logger.info("=" * 80)
    logger.info("测试 Step 4-B: Docker Build")
    logger.info("=" * 80)
    logger.info(f"输入参数:")
    logger.info(f"  - sha_m (PR merge commit): {sha_m}")
    logger.info(f"  - sha_n (Nightly SHA): {sha_n}")
    logger.info(f"  - pr_number: {pr_number}")
    logger.info(f"  - dry_run: {dry_run}")
    logger.info("")
    
    try:
        # Step 1: 获取 PR 文件变更
        logger.info("Step 1: 获取 PR 文件变更...")
        github_api = GitHubAPI()
        files = github_api.get_pr_files(pr_number)
        
        if not files:
            logger.error(f"PR #{pr_number} 没有变更的文件")
            return False
        
        logger.info(f"找到 {len(files)} 个变更文件:")
        for i, file_info in enumerate(files[:10], 1):  # 只显示前10个
            status = file_info.get("status", "unknown")
            filename = file_info.get("filename", "unknown")
            logger.info(f"  {i}. [{status}] {filename}")
        if len(files) > 10:
            logger.info(f"  ... 还有 {len(files) - 10} 个文件")
        logger.info("")
        
        # Step 2: 生成 Dockerfile（测试）
        logger.info("Step 2: 生成 Dockerfile...")
        dockerfile_content = generate_dockerfile(sha_n, files)
        logger.info("生成的 Dockerfile:")
        logger.info("-" * 80)
        print(dockerfile_content)
        logger.info("-" * 80)
        logger.info("")
        
        # Step 3: 测试文件下载（可选）
        logger.info("Step 3: 测试文件下载（前3个文件）...")
        downloaded_count = 0
        for file_info in files[:3]:
            file_path = file_info.get("filename")
            file_status = file_info.get("status")
            
            if file_status in ("added", "modified"):
                try:
                    content = github_api.get_file_content(file_path, ref=sha_m)
                    logger.info(f"  ✓ 成功下载: {file_path} ({len(content)} 字节)")
                    downloaded_count += 1
                except Exception as e:
                    logger.warning(f"  ✗ 下载失败: {file_path} - {e}")
        
        logger.info(f"成功下载 {downloaded_count}/{min(3, len(files))} 个文件")
        logger.info("")
        
        # Step 4: 实际构建（如果 dry_run=False）
        if dry_run:
            logger.info("Step 4: 跳过实际构建（dry_run=True）")
            logger.info("")
            logger.info("=" * 80)
            logger.info("✅ 测试完成（dry run）")
            logger.info("=" * 80)
            logger.info("")
            logger.info("提示：要实际构建镜像，运行:")
            logger.info(f"  python tests/test_step4b.py --sha-m {sha_m} --sha-n {sha_n} --pr-number {pr_number} --no-dry-run")
            return True
        else:
            logger.info("Step 4: 执行 Docker 构建...")
            logger.info("⚠️  注意：这将实际构建 Docker 镜像，可能需要较长时间")
            logger.info("")
            
            output_root = Path("output")
            output_root.mkdir(parents=True, exist_ok=True)
            image_tag = docker_build_custom(
                sha_m=sha_m,
                sha_n=sha_n,
                pr_number=pr_number,
                model_key=model_key,
                output_root=output_root,
            )
            
            logger.info("")
            logger.info("=" * 80)
            logger.info("✅ 测试完成！")
            logger.info(f"构建的镜像标签: {image_tag}")
            logger.info("=" * 80)
            return True
            
    except Exception as e:
        logger.error("")
        logger.error("=" * 80)
        logger.error(f"❌ 测试失败: {e}")
        logger.error("=" * 80)
        import traceback
        logger.error(traceback.format_exc())
        return False


def main():
    parser = argparse.ArgumentParser(
        description="测试 Step 4-B: Docker Build",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用默认测试数据（dry run）
  python tests/test_step4b.py
  
  # 使用自定义数据（dry run）
  python tests/test_step4b.py --sha-m abc1234 --sha-n def5678 --pr-number 12345
  
  # 实际构建镜像
  python tests/test_step4b.py --sha-m abc1234 --sha-n def5678 --pr-number 12345 --no-dry-run
        """
    )
    
    parser.add_argument(
        "--sha-m",
        type=str,
        help="PR merge commit SHA (默认: 使用示例数据)"
    )
    
    parser.add_argument(
        "--sha-n",
        type=str,
        help="Nightly build SHA (默认: 使用示例数据)"
    )
    
    parser.add_argument(
        "--pr-number",
        type=int,
        help="PR number (默认: 使用示例数据)"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="只测试不实际构建（默认: True）"
    )
    
    parser.add_argument(
        "--no-dry-run",
        action="store_false",
        dest="dry_run",
        help="实际构建镜像（需要 Docker）"
    )
    
    args = parser.parse_args()
    
    # 默认测试数据（需要替换为真实的 PR 数据）
    # 这些是示例数据，实际使用时需要替换
    default_sha_m = args.sha_m or "abc1234567890abcdef1234567890abcdef1234"
    default_sha_n = args.sha_n or "def567890abcdef1234567890abcdef1234567890"
    default_pr_number = args.pr_number or 12345
    
    if not args.sha_m or not args.sha_n or not args.pr_number:
        logger.warning("⚠️  使用默认测试数据，这些可能不是真实的 commit/PR")
        logger.warning("   请使用 --sha-m, --sha-n, --pr-number 提供真实数据")
        logger.warning("")
    
    success = test_step4b(
        sha_m=default_sha_m,
        sha_n=default_sha_n,
        pr_number=default_pr_number,
        dry_run=args.dry_run,
        model_key="test-model",
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
