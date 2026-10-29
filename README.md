# Smart Doc Flow · 文枢智动

文档处理工作台，包含文档解析、结构化信息提取、智能填表、知识图谱和 AI 助手。项目采用统一 FastAPI 后端、React/Vite 前端，并提供 Electron 桌面端和 Capacitor 移动端入口。

## 目录

| 路径 | 用途 |
| --- | --- |
| `backend/` | 统一 FastAPI 后端、业务模块和后端测试 |
| `frontend/` | Web 工作台 |
| `frontend-app/` | 移动端 Web 和 Capacitor 工程 |
| `electron/` | Electron 入口及桌面图标 |
| `scripts/` | 启动、打包、回归与维护脚本 |
| `config/` | 可公开的配置模板；真实配置仅在本地保存 |
| `datasets/` | 已跟踪的回归样本及本地补充语料，见[样本说明](docs/operations/sample-data.md) |
| `docs/` | 架构、设计、操作说明和维护规范 |
| `runtime-data/` | 本地运行数据，不纳入 Git |

根目录只保留项目说明、包管理与构建配置、编辑器规范、工具约定。文件入库和归档规则见[仓库维护规范](docs/operations/repository-hygiene.md)。

## 本地准备

需要 Node.js、Python 3.11 和 PostgreSQL。本机使用 Node.js 24；数据库示例使用 `5433` 端口。图谱投影、OCR、LLM 等能力还需各模块配置中的外部服务或模型。

```powershell
npm ci
npm --prefix frontend ci
npm --prefix frontend-app ci
```

统一 Python 环境位于根目录 `.venv/`，依赖基线为 `backend/requirements.txt`。MinerU 与 GraphRAG 的依赖元数据存在兼容约束，详见该文件的说明。已有种子环境时可使用 `npm run setup:backend:venv`；这个脚本依赖本地 `.venv-module2-py311/`，不是全新机器的一键安装器。

首次配置时，将 `backend/.env.example` 和需要的 `backend/app/modules/module*/.env.example` 复制为同目录的 `.env`，再填写数据库、认证密钥和模型接口。已有 `.env` 时不要用示例覆盖。移动端配置参考 `frontend-app/.env.example`。

启动前确保 PostgreSQL 可连接，并准备配置指定的数据库。现有示例涉及 `Data_Extraction`、`Knowledge_Graph` 和 `module3`；认证默认使用专用 schema。真实密码和 API 密钥只写入本地配置。

## 启动与检查

```powershell
npm run dev                  # Web 前端 + 统一 FastAPI 后端
npm run dev:frontend         # 仅 Web 前端
npm run dev:app              # 移动端 Web + 统一后端
```

| 服务 | 默认地址 |
| --- | --- |
| Web 前端 | http://localhost:3000 |
| 统一后端 | http://localhost:3001 |
| 移动端 Web | http://localhost:3002 |

`npm run dev` 使用统一后端，模块二、三、四由后端组合装配。模块独立入口保留作专项调试用途，正常前端请求应经统一后端。端口冲突时可以通过启动进程的 `FRONTEND_PORT` 等环境变量调整，不要关闭无关项目的服务。

```powershell
npm run wait:gateway
npm run build:frontend
npm run build:frontend:app:web
.\.venv\Scripts\python.exe -m pytest
```

在线工作流回归需要已启动的后端、外部服务及本地测试语料，入口为 `npm run qa:live:workflow`。有关样本依赖见[样本说明](docs/operations/sample-data.md)。

## 桌面端、移动端与穿透

- 桌面调试：`npm run desktop:dev`；桌面构建检查：`npm run desktop:doctor`。
- 移动端同步：`npm run mobile:cap:sync`；Android 工程在 `frontend-app/android/`。
- FRP 模板：`config/frp/frpc.example.toml`。复制到根目录 `frpc.toml` 后在本地填写，客户端需另行安装；真实配置和下载程序不上传。

更多后端细节见 [backend/README.md](backend/README.md)，端侧打包见 [docs/前端打包落地手册_20260422.md](docs/前端打包落地手册_20260422.md)。
