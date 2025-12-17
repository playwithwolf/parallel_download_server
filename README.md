# 并行分块下载服务（FastAPI）说明

## 项目结构
- `parallel_download_server/main.py` 服务入口
- `parallel_download_server/requirements.txt` 依赖
- `parallel_download_server/file.jkpg_chunks/` 分块目录（含 `chunk_*.part` 与 `manifest.json`）
- `parallel_download_server/file.jkpg_merge/file.jkpg` 服务端合并版（用于基准对比）
- 可选 `parallel_download_server/file.jkpg` 原始完整文件（用于 `/file` 端点）

## 提供的端点
- `GET /health` 健康检查
- `GET /chunks/manifest` 返回清单，含分块顺序、每块大小、每块 `sha256` 与整文件 `sha256`（parallel_download_server/main.py:40）
- `GET /chunks/list?offset=<int>&limit=<int>` 分页列名，仅用于调试或增量浏览（parallel_download_server/main.py:49）
- `GET /chunks/{name}` 下载分块，支持并发、`ETag`、`If-None-Match`、`Cache-Control`（parallel_download_server/main.py:57）
- `GET /merge/file` 下载服务端合并版（parallel_download_server/main.py:34）
- `GET /file` 下载原始完整文件（parallel_download_server/main.py:28）

## 并发与 workers 的关系
- 并行下载由“客户端同时发起多个请求”实现；服务器端不会限制你只能并发 2 或 3。
- `uvicorn ... --workers 2` 表示启动 2 个进程（workers），不是“只有 2 个并发连接”。每个 worker 内部是异步事件循环，可同时处理大量 I/O 并发。
- 你在客户端设置“3 个并行下载”，即同时发起 3 个 `GET /chunks/{name}` 请求，单个 worker 也可以并发处理；增加 `--workers` 主要提升吞吐和利用多核。
- 结论：为 3 并行下载，不需要把 `--workers` 设为 3；`--workers 1~2` 就能稳定支撑 3 并行。更高并发时，适当增大 `--workers` 与实例规格以提升吞吐。

## Render 部署
- 方案 A（根目录为仓库根）
  - 构建命令：`pip install -r parallel_download_server/requirements.txt`
  - 启动命令：`uvicorn parallel_download_server.main:app --host 0.0.0.0 --port $PORT`
  - 可选提升吞吐：`uvicorn parallel_download_server.main:app --host 0.0.0.0 --port $PORT --workers 2`
- 方案 B（Root Directory = `parallel_download_server`，更简洁）
  - Render 的 Root Directory 设置为 `parallel_download_server`
  - 构建命令：`pip install -r requirements.txt`
  - 启动命令：`uvicorn main:app --host 0.0.0.0 --port $PORT`
  - 可选提升吞吐：`uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2`
- 注意：Render 会注入 `$PORT` 环境变量；请确保 `file.jkpg_chunks/`、`file.jkpg_merge/file.jkpg` 随代码一并部署。

## 客户端下载流程建议
1. 读取 `manifest.json`（`GET /chunks/manifest`）
2. 按 `manifest["chunks"]` 初始化下载队列（包含顺序与每块 `sha256`）
3. 固定 2~3 并行拉取 `GET /chunks/{name}`
4. 单块完成后计算 `sha256` 校验，不匹配重试（指数退避，最多 3 次）
5. 全部成功后，严格按清单顺序本地合并
6. 对合成结果计算整文件 `sha256`，与 `manifest["sha256"]` 比对
7. 将合成后的文件交给原解压逻辑使用
- 说明：生产流程不需要 `chunks/list`；它仅用于分页浏览或调试，权威信息以 `manifest` 为准。

## 服务端优化点
- `ETag`/`If-None-Match`：`/chunks/{name}` 返回 `ETag` 为该块 `sha256`，客户端命中后可获 `304`（parallel_download_server/main.py:57）
- `Cache-Control`：分块响应含 `Cache-Control: public, max-age=3600`，便于中间层缓存（parallel_download_server/main.py:83）
- `Last-Modified`：暴露文件修改时间（parallel_download_server/main.py:79）
- 路径使用 `BASE_DIR = Path(__file__).resolve().parent`，部署时自动定位到 `parallel_download_server/`（parallel_download_server/main.py:18）

## 本地验证
- 方案 A：
  - 安装依赖：`pip install -r parallel_download_server/requirements.txt`
  - 启动服务：`uvicorn parallel_download_server.main:app --host 0.0.0.0 --port 8000`
- 方案 B（切换到 `parallel_download_server` 目录）：
  - 安装依赖：`pip install -r requirements.txt`
  - 启动服务：`uvicorn main:app --host 0.0.0.0 --port 8000`
- 验证：
  - `http://localhost:8000/health`
  - `http://localhost:8000/chunks/manifest`
  - `http://localhost:8000/chunks/list?offset=0&limit=3`
  - `http://localhost:8000/chunks/chunk_00001.part`
  - `http://localhost:8000/merge/file`

## 常见问题
- 并发是否必须 `--workers=3`？不需要。并发由客户端来决定，服务端 worker 内部可同时处理多个 I/O 请求；`workers` 只影响进程数量与整体吞吐。
- 是否必须用 `chunks/list`？不必须。按 `manifest` 下载更严谨；`chunks/list` 用于辅助分页与调试。
- 部署文件存储：Render 的代码包内文件可直接作为静态资源；如需动态写入或持久存储，请结合 Render 的持久化存储方案（或使用外部对象存储）。*** End Patch
