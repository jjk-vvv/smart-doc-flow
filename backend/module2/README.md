# Module 2 Backend

非结构化文档抽取与溯源服务。

该服务负责：

- 批量文档抽取
- 表格 / 图像 /字段溯源定位
- 文档摘要生成
- 助手式查询与可选落库
- Office 文档预览转换
- Dify / 工作流桥接调用

## 启动方式

### 从仓库根目录启动全链路

根目录的 `npm run dev` 现已默认启动：

- `frontend`：Vite 前端，端口 `3000`
- `auth`：认证与聊天服务，端口 `3001`
- `module2`：本文档对应服务，端口 `8000`
- `module4`：知识图谱服务，端口 `8100`

如果只想跳过模块二或模块四，可在 PowerShell 中临时设置：

```powershell
$env:MODULE2_ENABLED="0"
$env:MODULE4_ENABLED="0"
npm run dev
```

### 单独启动模块二

在仓库根目录执行：

```powershell
npm run dev:module2
```

或直接执行：

```powershell
python -m uvicorn app.main:app --app-dir backend/module2 --host 0.0.0.0 --port 8000 --reload
```

## 环境准备

### Python 依赖

先安装 `backend/module2/requirements.txt` 中依赖：

```powershell
pip install -r backend/module2/requirements.txt
```

关键 Python 依赖包括：

- `fastapi` / `uvicorn`
- `asyncpg` / `pgvector`
- `pypdf` / `python-docx` / `openpyxl` / `pymupdf`
- `rapidocr-onnxruntime`
- `mineru`
- `langgraph`
- `langchain-google-genai`

参考依赖清单：`backend/module2/requirements.txt`

### 环境变量

先复制环境变量模板：

```powershell
Copy-Item backend/module2/.env.example backend/module2/.env
```

模块二核心配置集中在：

- `MODULE2_DATABASE_DSN`
- `MODULE2_MAX_FILE_MB`
- `MODULE2_BATCH_CONCURRENCY`
- `MODULE2_PARSE_TIMEOUT_SEC`
- `MODULE2_EXTRACT_TIMEOUT_SEC`
- `MODULE2_MODULE4_SYNC_ENABLED`
- `MODULE2_MODULE4_BASE_URL`
- `MODULE2_MODULE4_SYNC_RETRIES`
- `MODULE2_PIPELINE_MODE`
- `MODULE2_ENABLE_MINERU_LAYOUT`
- `MODULE2_DOC_TO_PDF_ENABLE`
- `GEMINI_API_KEY`

配置样例见：`backend/module2/.env.example`

## 外部依赖要求

### PostgreSQL（推荐，非强制）

模块二默认会连接 PostgreSQL 保存：

- 抽取缓存
- 字段 staging 数据
- 表格 staging 数据
- 助手交互记录

默认 DSN：

```text
postgresql://postgres:postgres@localhost:5432/a23
```

如果数据库不可用，服务会自动降级为内存模式，但这只适合本地调试，不适合长期使用。

### Gemini API Key（建议开启）

模块二有两类能力会使用 Gemini：

- 结构化字段抽取图中的 LLM 抽取
- 视觉增强链路中的表格 / 图像理解

至少配置其一：

```text
GEMINI_API_KEY=
GOOGLE_API_KEY=
```

若未配置，部分智能抽取能力会退化或关闭。

### MinerU（视觉优先链路）

当启用 `visual_first` / `VisualTrack` 时，模块二会使用 MinerU 做版面理解、表格/图像对象定位和内容清单生成。

需要满足：

- 已安装 `mineru`
- 运行环境能够拉起 MinerU 所需模型与依赖
- `.env` 中相关变量已正确配置，例如：
  - `MODULE2_ENABLE_MINERU_LAYOUT=true`
  - `MODULE2_MINERU_BACKEND=pipeline`
  - `MODULE2_MINERU_METHOD=auto`
  - `MODULE2_MINERU_DEVICE=cpu`

若 MinerU 不可用，PDF 视觉链路可能回退到 `FastTrack`，严格模式下也可能直接失败。

### LibreOffice / Word COM（Office 预览与转换）

当需要对 `.doc` / `.docx` 做 PDF 预览转换时，模块二优先尝试：

1. `LibreOffice soffice`
2. Windows 下的 `Word COM`

Windows 常见 LibreOffice 路径：

- `C:\Program Files\LibreOffice\program\soffice.exe`
- `C:\Program Files (x86)\LibreOffice\program\soffice.exe`

也可以显式配置：

```text
MODULE2_SOFFICE_PATH=C:\Program Files\LibreOffice\program\soffice.exe
```

如果你在 Windows 且装有桌面版 Word，也可以通过 Word COM 完成转换。

## 支持文件类型

### 前端上传控件当前接受

- `pdf`
- `doc`
- `docx`
- `xlsx`
- `txt`
- `md`
- `png`
- `jpg`
- `jpeg`
- `bmp`
- `webp`
- `tif`
- `tiff`

### 解析层额外支持的文本扩展名

除上述类型外，解析器内部还支持部分文本类扩展名：

- `csv`
- `json`
- `xml`
- `html`
- `htm`
- `markdown`

说明：前端上传控件当前未放开所有这些后缀；如需前端直接上传，可再同步调整前端 `accept` 配置。

## 处理链路概览

模块二的单文档处理流程大致为：

1. 读取文件并计算 hash
2. 命中缓存则直接返回
3. 对 PDF 在 `FastTrack / VisualTrack` 间分流
4. 在子进程中解析文档，产出：
   - `markdown`
   - `bbox_map`
   - `table_blocks`
   - `figure_blocks`
5. 交给 LangGraph 抽取图执行字段抽取与校验
6. 生成 `trace_hits`、`diagnostics`
7. 写入缓存 / staging / 助手历史

返回结构的核心字段包括：

- `file_name`
- `file_hash`
- `track`
- `cached`
- `result`
- `errors`
- `soft_warnings`
- `trace_hits`
- `trace_stats`
- `diagnostics`

## 主要接口

### 1. 批量抽取

`POST /extract/batch`

表单字段：

- `files`: 多文件，最多 5 个
- `schema`: JSON 字符串
- `tenant_id`: 可选，传给模块四做租户隔离

返回：

- `documents: DocumentExtractionResponse[]`

额外行为：

- 当 `MODULE2_MODULE4_SYNC_ENABLED=true` 时，抽取完成后会由模块二服务端异步把结果同步到模块四
- 同步请求默认带 `X-Tenant-Id`，并使用稳定的 `source_batch_key` 做幂等去重
- 同步失败会按 `MODULE2_MODULE4_SYNC_RETRIES` 与 `MODULE2_MODULE4_SYNC_BACKOFF_SEC` 自动重试
- 服务关闭时会在 `MODULE2_MODULE4_SHUTDOWN_DRAIN_SEC` 窗口内尽量等待模块四同步任务完成

### 2. Office 预览转换任务

启动任务：

- `POST /extract/preview/office/start`

查询任务：

- `GET /extract/preview/office/status/{job_id}`

适用于：

- `.doc`
- `.docx`

### 3. 智能摘要

`POST /extract/summarize`

输入文档抽取结果后，返回简短摘要：

- `summary`

### 4. 溯源定位

`POST /extract/trace/locate`

输入：

- `document`
- `field_name`（可选）
- `keyword`（可选）
- `top_k`

返回：

- `hit_count`
- `truncated`
- `hits`

### 5. 助手查询

`POST /extract/assistant/query`

输入：

- `document`
- `summary`
- `user_instruction`
- `persist`
- `top_k`

返回：

- `answer`
- `matched_fields`
- `matched_trace_hits`
- `persisted`
- `persisted_rows`
- `warnings`

### 6. 缓存清理

`POST /extract/cache/clear`

用于清理：

- 运行时缓存
- artifact 缓存
- Office 预览任务缓存

### 7. Dify / 工作流桥接接口

创建任务：

- `POST /dify/module2/jobs/create`

查询任务：

- `POST /dify/module2/jobs/status`

桥接溯源：

- `POST /dify/module2/trace/locate`

这组接口支持通过：

- `file_url`
- `file_base64`

方式提交远端文件或内联文件。

### 8. 健康检查

`GET /healthz`

重点查看：

- `storage_db_connected`
- `storage_degraded_memory_mode`
- `bridge_jobs_in_memory`
- `office_preview_jobs_in_memory`

## 常见联调端口

- 前端：`http://localhost:3000`
- 认证服务：`http://localhost:3001`
- 模块二：`http://localhost:8000`
- 模块四：`http://localhost:8100`

前端代理配置见：`frontend/vite.config.ts`

## 常见问题

### 1. `npm run dev` 启动后前端能打开，但抽取失败

优先检查：

- 模块二依赖是否安装完成
- `python` 是否可用
- `backend/module2/.env` 是否存在
- `http://localhost:8000/healthz` 是否可访问

### 2. Word 预览一直失败

优先检查：

- 是否安装 LibreOffice
- `MODULE2_SOFFICE_PATH` 是否正确
- Windows 下是否可使用 Word COM
- `.doc/.docx` 文件是否超出大小限制

### 3. 抽取效果较弱或摘要/视觉能力缺失

优先检查：

- 是否配置 `GEMINI_API_KEY`
- 是否启用 MinerU 相关配置
- 是否被回退到 `FastTrack`

### 4. 数据库未连接

模块二会降级到内存模式继续运行，但你会失去：

- 持久化缓存
- 助手历史持久化
- 更稳定的联调行为

建议尽快补齐 PostgreSQL。
