# 推理引擎模型构建自动化系统

根据 PR 变更自动构建和验证推理引擎（如 vLLM、TensorRT-LLM 等）模型 Docker 镜像的自动化系统。

**注意**：系统只使用推理引擎厂商官方在 Docker Hub 发布的镜像。

## 功能特性

- 🔍 自动获取最新 nightly 构建
- 📋 智能匹配模型相关 PR
- 🔗 判断 commit 祖先关系
- 🐳 Docker 镜像拉取/构建
- ✅ 模型注册验证
- 📦 镜像打包导出

## 项目结构

```
.
├── main.py                 # 主入口文件
├── config.py              # 配置管理
├── requirements.txt       # Python 依赖
├── .env.example          # 环境变量示例
├── src/
│   ├── steps/            # 各步骤实现
│   │   ├── step1_get_nightly.py
│   │   ├── step2_match_pr.py
│   │   ├── step3_check_ancestor.py
│   │   ├── step4_docker_ops.py
│   │   ├── step5_validate.py
│   │   └── step6_package.py
│   ├── utils/            # 工具函数
│   │   ├── git_utils.py
│   │   ├── docker_utils.py
│   │   ├── github_api.py
│   │   └── logger.py
│   └── error_handler.py  # 错误处理
└── README.md
```

## 安装

1. 克隆仓库（如果适用）

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 配置环境变量：
```bash
cp .env.example .env
# 编辑 .env 文件，填入必要的配置
```

## 配置说明

在 `.env` 文件中配置以下变量：

### 必需配置

- `GITHUB_TOKEN`: GitHub Personal Access Token（需要 repo 权限）
- `GITHUB_REPO_OWNER`: GitHub 仓库所有者（默认: vllm-project）
- `GITHUB_REPO_NAME`: GitHub 仓库名称（默认: vllm）

### 推理引擎配置

- `ENGINE_NAME`: 推理引擎名称（默认: vllm），用于标识当前使用的引擎
- `MODEL_REGISTRY_IMPORT_PATH`: 模型注册表的 Python 导入路径（默认: vllm.model_executor.models）
- `OUTPUT_FILE_PREFIX`: 输出 tar 文件的前缀（默认: vllm）

### 可选配置

- `DOCKERHUB_REPOSITORY`: DockerHub 仓库（**必须是推理引擎厂商官方仓库**，默认: vllm/vllm-openai）
- `DOCKERHUB_USERNAME`: DockerHub 用户名（用于私有仓库）
- `DOCKERHUB_TOKEN`: DockerHub Token（用于私有仓库）
- `APP_WEBHOOK_URL`: 错误通知 Webhook URL
- `APP_API_KEY`: Webhook API Key
- `GIT_REPO_URL`: Git 仓库 URL
- `GIT_REPO_CLONE_DIR`: Git 仓库本地缓存目录（默认: ./.repo_cache）
- `LOG_LEVEL`: 日志级别（默认: INFO）

## 使用方法

```bash
python main.py \
  --model-id Qwen/Qwen3.5-35B-A3B-FP8 \
  --image-tag qwen3.5-v1.0 \
  --output-dir ./output
```

### 参数说明

- `--model-id`: 完整模型 ID（如 `Qwen/Qwen3.5-35B-A3B-FP8`），系统会自动提取搜索关键词
- `--image-tag`: 输出镜像的自定义标签名称
- `--output-dir`: 输出目录（tar 文件将保存在此）

**注意**：`--model-id` 支持完整模型 ID 格式，系统会自动去除尺寸、dtype、量化等信息，提取核心模型名用于搜索。

## 工作流程

1. **Step 1**: 从 DockerHub 获取最新 nightly 构建的 SHA (sha-n)
2. **Step 2**: 
   - 从完整模型 ID 中提取搜索关键词（去除尺寸、dtype、量化等信息）
   - 使用策略1（精确匹配 + 支持关键词/排除bugfix）搜索已合并 PR
   - 获取 merge commit SHA (sha-m)，并解析模型注册信息
3. **Step 3**: 使用 `git merge-base` 判断 sha-m 是否为 sha-n 的祖先
4. **Step 4-A**: 如果是祖先，直接拉取 `nightly-{sha-n}` 镜像
5. **Step 4-B**: 如果不是祖先，提取 PR 变更文件并构建新镜像
6. **Step 5**: 在容器中验证模型类是否已注册到 ModelRegistry
7. **Step 6**: 将镜像打包为 `{output_file_prefix}-{image-tag}.tar` 文件

## 错误处理

如果任何步骤失败，系统会：
1. 记录详细错误日志
2. 发送错误通知到配置的 Webhook（如果已配置）
3. 退出并返回错误码

## 依赖要求

- Python 3.8+
- Docker（已安装并运行）
- Git（已安装）
- 网络连接（访问 GitHub API、DockerHub）

## 注意事项

1. **GitHub Token**: 需要足够的权限访问仓库和 PR 信息
2. **Docker**: 确保 Docker daemon 正在运行
3. **磁盘空间**: 构建的镜像可能占用数 GB 空间
4. **网络**: 需要稳定的网络连接以下载镜像和访问 API

## 测试

### 测试 Step 4-B (Docker Build)

提供了一个测试脚本来测试 Step 4-B 的功能：

```bash
# 使用默认测试数据（dry run，不实际构建）
python tests/test_step4b.py

# 使用真实的 PR 数据测试（dry run）
python tests/test_step4b.py \
  --sha-m <merge_commit_sha> \
  --sha-n <nightly_sha> \
  --pr-number <pr_number>

# 实际构建镜像（需要 Docker）
python tests/test_step4b.py \
  --sha-m <merge_commit_sha> \
  --sha-n <nightly_sha> \
  --pr-number <pr_number> \
  --no-dry-run
```

测试脚本会：
1. 获取 PR 的文件变更列表
2. 生成 Dockerfile（显示内容）
3. 测试下载前几个文件
4. （可选）实际构建 Docker 镜像

## 故障排查

### 问题：无法获取 nightly SHA
- 检查 DockerHub 仓库名称是否正确（必须是厂商官方仓库）
- 确认网络连接正常
- 检查是否有 nightly 标签存在
- 确认仓库是公开的或已配置正确的认证信息

### 问题：找不到匹配的 PR
- 确认模型 ID 格式正确（如 `Qwen/Qwen3.5-35B-A3B-FP8`）
- 检查系统提取的搜索关键词是否正确（查看日志中的 "Extracted search model name"）
- 检查是否有已合并的相关 PR，且 PR 标题包含模型名
- 确认 GitHub Token 有足够权限
- 查看详细错误信息，了解尝试了哪些搜索策略

### 问题：Docker 操作失败
- 确认 Docker daemon 正在运行：`docker ps`
- 检查磁盘空间是否充足
- 确认有权限访问 Docker

### 问题：验证失败
- 检查模型类名是否正确
- 确认镜像中包含推理引擎代码
- 检查 `MODEL_REGISTRY_IMPORT_PATH` 配置是否正确
- 查看详细日志了解具体错误

## 多引擎支持

系统设计支持多个推理引擎厂商，当前默认配置为 vLLM。要切换到其他引擎（如 TensorRT-LLM），只需修改 `.env` 文件中的相关配置：

```bash
# 示例：切换到 TensorRT-LLM
ENGINE_NAME=tensorrt-llm
MODEL_REGISTRY_IMPORT_PATH=tensorrt_llm.models
OUTPUT_FILE_PREFIX=tensorrt-llm
DOCKERHUB_REPOSITORY=nvcr.io/nvidia/tensorrt-llm  # 官方仓库
GITHUB_REPO_OWNER=nvidia
GITHUB_REPO_NAME=TensorRT-LLM
```

**重要**：确保 `DOCKERHUB_REPOSITORY` 配置的是该推理引擎厂商的**官方 Docker Hub 仓库**。

## 许可证

[根据项目实际情况填写]
