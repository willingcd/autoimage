# Prefect 多引擎并行构建

在**不修改现有项目代码**的前提下，用 Prefect 编排一次触发、同时构建 vllm、vllm-ascend、sglang、mindie 四个厂商的镜像，并分别写入不同目录。

## 行为说明

- **触发一次**：执行 `multi_engine_build_flow`，对 4 个引擎各起一个子进程运行现有 `main.py`。
- **并行**：4 个引擎的构建任务并行执行（Prefect 的 task 并发）。
- **输出目录**（在 `--output-root` 下按引擎分子目录）：
  - vllm → `<output_root>/vllm/`
  - vllm_ascend → `<output_root>/vllm_ascend/`
  - sglang → `<output_root>/sglang/`
  - mindie → `<output_root>/mindie/`

每个引擎使用 `engine_configs.py` 里配置的 env 覆盖（GitHub 仓库、Docker 仓库、模型注册路径等），共享当前环境里的 `GITHUB_TOKEN` 等基础变量。

## 安装

在项目根目录安装主项目依赖后，再安装 Prefect（可只用 prefect_flow 的 requirements）：

```bash
# 项目根目录
pip install -r requirements.txt
pip install -r prefect_flow/requirements.txt
```

## 运行

**必须在项目根目录执行**（即 `autoimages/v2` 所在目录）：

```bash
# 项目根目录
python -m prefect_flow.run --model-id Qwen/Qwen3.5-35B-A3B-FP8 --output-root /output
```

- `--model-id`：与现有 `main.py` 的 `--model-id` 一致。
- `--output-root`：根输出目录，默认 `/output`；各引擎的 tar 等会落在其下 `vllm/`、`vllm_ascend/`、`sglang/`、`mindie/`。

运行前请设置好环境变量（至少包含 `GITHUB_TOKEN`；各引擎如需不同 Docker/Git 配置，在 `engine_configs.py` 中修改）。

## 配置各引擎

编辑 `prefect_flow/engine_configs.py`：

- **ENGINE_OUTPUT_SUBDIRS**：引擎 id 与输出子目录名（已按 vllm / vllm_ascend / sglang / mindie 配置）。
- **ENGINE_ENV_OVERRIDES**：每个引擎的 env 覆盖（`GITHUB_REPO_OWNER`、`GITHUB_REPO_NAME`、`DOCKERHUB_REPOSITORY`、`MODEL_REGISTRY_IMPORT_PATH`、`OUTPUT_FILE_PREFIX`、`GIT_REPO_URL` 等）。其中的仓库/镜像名请按实际填写；当前 sglang、mindie 等为示例，需改成真实值。

## 与现有代码的关系

- 本目录下**仅新增** Prefect 相关文件，**不修改** 根目录的 `main.py`、`config.py`、`src/` 等。
- 实际构建仍由现有 `main.py` 完成；Prefect 只负责按引擎设置环境变量并指定 `--output-dir`，然后并行调用多个 `main.py` 子进程。
