# Prefect 流水线封装（可嵌入公司现有 Prefect 平台）

本目录将现有的 6 步构建流程（Step 1–6）**用 Prefect 进行编排**，不修改任何已有源码。
公司侧只需要把整个 `prefect_flow/` 目录拷贝到自己的代码仓库里，并在 Prefect 流水线中导入使用即可。

## 依赖

在包含本项目代码的虚拟环境中安装 Prefect：

```bash
pip install -r prefect_flow/requirements.txt
```

> 说明：主项目依赖（requests、docker 等）仍由根目录的 `requirements.txt` 提供。

## 核心入口

- 模块：`prefect_flow.flow`
- 流函数：`build_pipeline_flow(model_id: str, output_dir: str) -> dict`

示例（在公司自有 Prefect 流水线中使用）：

```python
from prefect import flow
from prefect_flow.flow import build_pipeline_flow


@flow
def company_flow():
    result = build_pipeline_flow(
        model_id="Qwen/Qwen3.5-35B-A3B-FP8",
        output_dir="/output/vllm",
    )
    # 在这里可以把 result 里的 sha_n/sha_m/pr_number/tar_path 等信息
    # 继续传给下游任务（注册镜像、通知平台等）
```

## 行为说明

`build_pipeline_flow` 内部严格复用原项目的 6 个 Step 实现：

1. **Step 1**：`step1_get_nightly_sha_task` → 调用 `step1_get_nightly.get_nightly_sha`
2. **Step 2**：`step2_match_pr_task` → 调用 `step2_match_pr.match_model_pr`
3. **Step 3**：`step3_pull_and_verify_task` → 调用 `step3_pull_nightly.pull_nightly_and_verify`
4. **Step 4**：`step4_check_ancestor_task` → 调用 `step4_check_ancestor.check_ancestor_relationship`
   - 若 sha-m 是 sha-n 的祖先：直接使用 Step 3 拉取的 nightly 镜像
   - 否则：
     - **Step 4-B**：`step4b_docker_build_task` → 调用 `step4_docker_ops.docker_build_custom`
5. **Step 5**：`step5_validate_task` → 调用 `step5_validate.validate_model_registrations`
6. **Step 6**：`step6_package_task` → 调用 `step6_package.package_image` 生成 tar

返回值是一个包含关键信息的字典，例如：

```python
{
  "model_id": "...",
  "sha_n": "...",
  "sha_m": "...",
  "pr_number": 123,
  "image_tag": "repo:nightly-xxx" or "repo:nightly-xxx_PR123",
  "tar_path": "/output/.../images_tar/xxx.tar",
  "output_dir": "/output/...",
}
```

## 重试与告警

- Prefect 级别：
  - Step 1 / Step 2 / Step 3：`@task(retries=3, retry_delay_seconds=30)`
  - Step 4-B：`@task(retries=3, retry_delay_seconds=60)`
- 流级别异常处理：
  - `build_pipeline_flow` 用 `try/except` 包裹整体，在异常时调用原项目的 `handle_error`：
    - 通过 Webhook 向 App 发送错误告警（如果已配置）
    - 重新抛出异常，使 Prefect 将该 flow 视为失败

这样可以在公司 Prefect 平台上直接看到失败状态，同时保持与原 CLI 版本一致的告警行为。

## 环境约定

- 所有配置仍由原项目的 `config.py` 从 **环境变量** 中读取：
  - `GITHUB_TOKEN`、`GITHUB_REPO_OWNER`、`GITHUB_REPO_NAME`
  - `DOCKERHUB_REPOSITORY`、`ENGINE_NAME`、`MODEL_REGISTRY_IMPORT_PATH`、`OUTPUT_FILE_PREFIX` 等
- Prefect 只负责调度，不改变配置来源。
- 如需支持多引擎（vllm / vllm-ascend / sglang / mindie 等），推荐做法是：
  - 由公司侧的上层 Prefect 流分别设置不同的环境变量或执行环境
  - 针对每个引擎调用一次 `build_pipeline_flow`，并将 `output_dir` 设为不同子目录。

