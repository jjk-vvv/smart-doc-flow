# Smart Doc Flow 最终最优整体架构与目录蓝图

Date: 2026-03-29

Status: approved-target

## 文档目的

本文档用于固化当前项目在“完成统一框架迁移之后”的最终最优整体架构、目录结构、职责边界和打包边界。

它不是一次临时讨论记录，而是后续所有迁移、归并、清理、打包和验收的共同基线。

这份文档回答以下核心问题：

1. 当前项目最终应该长成什么样的整体框架
2. 最优目录结构到底应该如何定义
3. 项目更适合 MVC 还是 MVVM
4. 哪些目录是主线源码，哪些只是兼容层、运行产物或历史遗留
5. 后续重构时哪些边界必须冻结，哪些内容可以继续迁移
6. 如何在不影响完整工作流的前提下，为后续软件封装和持续开发做好准备

## 最终结论

当前项目最终最优的整体框架不是“把全部代码硬塞进一个教科书式单体 MVC 后端”，也不是“前端再额外套一层 MVVM”。

最优方案是：

`统一 FastAPI 公共入口 + 保持 Module2 / Module4 为边界清晰的内部引擎 + React/Vite 前端 + Electron 桌面封装壳`

这一定义下的核心判断如下：

- FastAPI 是唯一权威后端框架
- `backend/app` 是唯一对外公共后端入口
- `backend/module2` 是文档抽取主引擎
- `backend/module4` 是图谱与风控主引擎
- `backend/auth/server.cjs` 仅保留为兼容代理，不再视为主业务后端
- 前端继续保持 `React + Vite`
- 桌面端继续保持 `Electron`
- 后端采用“分层 MVC 风格”而不是“教科书单体 MVC”
- 前端采用“页面容器 + 特性模块 + shared api + 本地状态”结构，而不是 MVVM

这是当前项目在以下三个目标同时成立时的最优解：

- 保留完整功能链路
- 不发生降级和功能回退
- 为后续打包、发布、继续开发预留最稳的结构

## 为什么这才是最优方案

当前项目不是普通 CRUD 系统，而是一个强工作流系统。

它的主业务链路包含：

- auth 认证
- 文件上传
- DOC / DOCX 异步转 PDF
- PDF 解析
- MinerU 解析与切块
- Gemini Vision 图表增强理解
- 结构化字段抽取
- trace / summarize
- assistant1 基于抽取结果的 grounded chat
- Module2 -> Module4 同步
- Module4 图谱、告警、规则、解释、模拟
- Electron 打包与本地运行

这种系统如果强行做成单体扁平 MVC，会有三个问题：

- 解析链路、异步任务、图谱链路会全部挤在同一个应用层，职责会进一步混乱
- 为了“看起来统一”而移动大量成熟业务逻辑，迁移风险远高于收益
- 打包、运行时数据、内部引擎、兼容层之间的边界会变得更模糊

因此，本项目最优的不是“物理全合并”，而是“公共入口统一 + 内部引擎边界稳定 + 层次清晰”。

## MVC 还是 MVVM

## 最终判断

- 后端最适合：分层 MVC
- 前端最适合：React 特性分层
- 项目整体不适合：MVVM

## 为什么后端适合分层 MVC

在本项目中，MVC 应该这样落位：

- Controller: FastAPI routers
- Service: `service.py`、`runtime/*`、`app_runtime.py`
- Model: `schemas.py`、`repository.py`、`db/*`、`parser.py`、规则逻辑、领域逻辑
- View: React 页面和组件

之所以强调“分层 MVC 风格”，而不是教科书式 MVC，是因为你的项目包含：

- 异步任务
- 文档解析流水线
- 非结构化转结构化
- 多模态增强
- 图谱下游同步
- explain / simulate 这类应用服务行为

这些都不是一个扁平 `controller / model / view` 三层就能优雅承接的。

因此最适合的是：

- 路由层负责对外接口
- 服务层和 runtime 层负责应用编排
- model / schema / db / parser 负责核心数据与领域逻辑

## 为什么前端不适合 MVVM

本项目的前端已经天然更适合 React 生态的特性分层，而不是 MVVM。

原因如下：

- React 本身已经天然适配组件化和页面容器拆分
- 你当前的主要问题是“工作流组织”和“大组件拆分”，不是“双向绑定抽象不足”
- 如果强加 ViewModel 层，只会制造新的状态重复和理解成本
- 当前前端已经存在 `shared/api`、`lib`、大模块组件和页面入口，继续沿这个方向优化更自然

因此前端最优结构应当是：

- `pages/` 页面容器
- `components/` 通用和大模块组件
- `features/` 特性域
- `shared/api/` 接口调用
- `lib/` 会话、本地状态、通用工具

## 最终最优总体拓扑

```text
frontend (React + Vite)
        |
        v
backend/app (Unified FastAPI Gateway, public entry only)
        |
        |--- /api/*        -> auth / assistant / other platform modules
        |--- /extract/*    -> extraction gateway contract layer
        |--- /module4/*    -> module4 proxy / sidecar coordination
        |--- /             -> frontend static hosting in packaged mode
        |
        |---------------------------> backend/module2 (document extraction engine)
        |
        |---------------------------> backend/module4 (graph & risk engine)
        |
        |---------------------------> backend/auth/server.cjs (compat only, transitional)
        |
        v
electron/main.cjs (desktop shell and managed runtime host)
```

这个拓扑的关键点不是“只有一个 Python 目录”，而是：

- 对外只有一个公共入口
- 对内保留专业引擎边界
- 桌面打包时只暴露一个平台入口

## 最终最优目录蓝图

```text
smart-doc-flow/
  backend/
    app/                                        # 统一 FastAPI 公共后端入口
      main.py
      create_app.py
      core/
        config.py
        deps.py
        env.py
        paths.py
        lifespan.py
        middleware.py
        exceptions.py
        health.py
      modules/
        auth/                                   # 统一认证核心
          router.py
          service.py
          repository.py
          security.py
          schemas.py
          notifier.py
          config.py
        assistant/                              # 平台级聊天入口
          router.py
          service.py
          provider.py
          prompting.py
          schemas.py
          config.py
        extraction/                             # 对外 /extract 合约层
          router.py
          service.py
          schemas.py
          config.py
          artifact_runtime.py
          assistant1_runtime.py
          cache_runtime.py
          summary_runtime.py
          module2_execution_facade.py
          module2_request_runtime.py
          module2_sidecar_runtime.py
          module2_upstream_runtime.py
          module2_shadow_runtime.py
          module2_worker_runtime.py
          module2_compat_worker.py
        gateway/                                # gateway info / health / ready / module4 代理
          router.py
          service.py
          module4_sidecar_runtime.py
        frontend_static/                        # 生产态前端静态资源托管
          router.py
          service.py
        module1_placeholder/                    # module1 页面占位
          router.py
          service.py

    auth/                                       # 兼容代理层，不是主线业务后端
      server.cjs

    module2/                                    # 文档抽取主引擎
      app/
        main.py
        schemas.py
        agent/
        assistant_1/
        assets/
        core/
        db/
        prompts/
        routes/
        runtime/

    module4/                                    # 图谱与风控主引擎
      app/
        main.py
        router.py
        schemas.py
        db/
        services/

    tests/                                      # 统一 FastAPI 入口相关测试

  frontend/
    App.tsx                                     # 前端总壳
    pages/                                      # 页面级容器
    components/                                 # 通用组件 / 大模块组件
    features/                                   # 特性域
    shared/
      api/                                      # auth / extraction / module4 / client
    lib/                                        # session / stores / utils
    public/
    e2e/                                        # 端到端回归脚本，不参与打包

  electron/
    main.cjs                                    # Electron 主进程
    icon.ico
    icon.png

  scripts/                                      # dev / start / wait / desktop / smoke 编排脚本
  docs/                                         # 架构、迁移、验收、回归文档
  datasets/                                     # 回归样本数据
  package.json                                  # 顶层工作区入口
  electron-builder.json                         # 桌面打包配置
  pytest.ini
```

## 各目录的权威职责

## 1. backend/app

`backend/app` 是整个项目未来唯一的公共后端入口，也是最终桌面打包时的平台后端入口。

它的职责包括：

- 统一注册所有公共 API 路由
- 托管 auth 主逻辑
- 托管平台 assistant 入口
- 承接 `/extract/*` 公共接口契约
- 承接 `/module4/*` 公共代理与协调
- 提供 `/gateway/info`、`/gateway/health`、`/gateway/ready`
- 在生产或桌面模式下提供前端静态资源
- 统一生命周期、配置、依赖、中间件和异常处理

它不应该承担的职责：

- 不直接吞并所有 Module2 解析细节
- 不直接吞并所有 Module4 图谱实现细节
- 不应该变成一个新的超级大杂烩目录

## 2. backend/app/modules/auth

这是认证主线，不再是兼容层。

它负责：

- 注册
- 登录
- 登出
- 当前用户 `me`
- 找回密码验证码
- 密码重置
- cookie / session 语义
- 用户存储迁移与管理

它应该被视为 auth 的权威实现。

## 3. backend/auth

这是兼容代理层，不是未来主业务后端。

它只应该负责：

- 保持历史调用路径可继续工作
- 把老入口转发给统一 FastAPI

它不应该继续接收新的主业务逻辑。

## 4. backend/app/modules/extraction

这是统一对外抽取接口层，是公共平台面向前端和桌面的 `/extract/*` 合约所有者。

它负责：

- `/extract/jobs/create`
- `/extract/jobs/status`
- `/extract/batch`
- `/extract/summarize`
- `/extract/trace/locate`
- `/extract/assistant1/chat/stream`
- `/extract/cache/clear`
- office preview 对外接口
- artifact 对外访问接口
- 协调 module2 sidecar / upstream / compat worker

它不应该负责：

- 重写 Module2 的真实解析引擎
- 直接持有 MinerU、OCR、Gemini 具体实现细节

## 5. backend/module2

这是文档抽取主引擎，是真正承载完整文档处理流水线的地方。

它负责：

- 文件内容物化
- 文档抽取任务管理
- DOC / DOCX 转 PDF
- PDF 解析
- MinerU 链路
- OCR 与图片解析
- Gemini Vision 图表理解
- 结构化字段抽取
- trace hits
- summarize 支撑数据
- assistant1 grounding 数据准备与回答链路
- Module2 -> Module4 下游同步
- artifact 落盘与缓存

其内部最优结构应当继续收敛为：

- `routes/`：入口拆分
- `runtime/`：HTTP / job / workflow / bundle / callback 编排
- `core/`：parser、非结构化转结构化、视觉解析、规则逻辑
- `assistant_1/`：知识切分、向量、检索、streaming
- `db/`：持久化
- `assets/` 与 `prompts/`：规则和提示词资产

## 6. backend/module4

这是图谱与风控主引擎。

它负责：

- 接收 Module2 文档结果并 ingest
- graph files / graph versions 管理
- alerts / rules / evidence
- explain / simulate
- 图谱查询
- GraphRAG 相关能力
- Neo4j projection 相关能力

其内部最优结构应当继续收敛为：

- `router.py`：API 层
- `services/`：ingest / query / rule / insight / app_runtime
- `db/`：图谱和任务存储
- `schemas.py`：统一响应与请求模型

## 7. frontend

前端是统一的 View 层。

最优职责划分应当是：

- `App.tsx`：总壳和主导航切换
- `pages/`：页面级容器
- `components/`：跨页面组件和大模块工作台组件
- `features/`：特性域组件与逻辑
- `shared/api/`：统一接口客户端
- `lib/`：本地 session、store、工具函数

它不应该再额外引入一套 MVVM 结构。

## 8. electron

Electron 只应当作为桌面封装壳和运行时宿主。

它负责：

- 启动统一后端
- 等待 gateway ready
- 装载 renderer
- 管理桌面进程生命周期
- 将运行时数据导向用户可写目录

它不应该直接承载抽取或图谱业务逻辑。

## 9. scripts

`scripts/` 是整个项目的运行编排层。

它负责：

- `dev-*` 本地开发启动
- `start-*` 生产或准生产启动
- `wait-for-gateway` readiness 等待
- desktop doctor / smoke / clean
- 统一启动 FastAPI-first 模式

它不应该承担业务逻辑本体，只承担编排职责。

## 现有仓库中的“主线源码”与“非主线内容”判定

为了避免后续迁移继续把运行产物或历史目录误认为源码主线，必须建立明确分类。

## A 类：最终主线源码

以下目录是最终架构中的权威主线源码：

- `backend/app/**`
- `backend/module2/app/**`
- `backend/module4/app/**`
- `frontend/App.tsx`
- `frontend/pages/**`
- `frontend/components/**`
- `frontend/features/**`
- `frontend/shared/api/**`
- `frontend/lib/**`
- `electron/**`
- `scripts/**`
- `docs/**`

## B 类：兼容层源码

以下目录是当前仍需保留，但不应视为未来主业务中心的兼容层：

- `backend/auth/server.cjs`
- `backend/app/modules/extraction/module2_compat_worker.py`
- `backend/app/modules/extraction/module2_execution_facade.py`

## C 类：开发辅助但不参与主线打包

以下内容对开发和回归有价值，但不属于运行时主线包：

- `backend/tests/**`
- `backend/module2/tests/**`
- `backend/module4/tests/**`
- `frontend/e2e/**`
- `datasets/**`

## D 类：运行产物、缓存、历史残留，不得视为主线源码

以下内容不应继续作为迁移目标，也不应打进最终桌面包：

- `.runlogs/**`
- `frontend/.runlogs/**`
- `module2/runlogs/**`
- `dist-electron/**`
- `.pytest_cache/**`
- `.pytest_tmp/**`
- `.codex-temp/**`
- `__pycache__/**`
- `node_modules/**`
- `frontend/dist/**` 仅作为构建产物，不是源码
- `backend/backend/**` 这类嵌套历史产物目录
- 根目录 `auth/users.json` 这类运行数据文件

## 特别说明：当前仓库里容易混淆的目录

### 1. `backend/backend`

这个目录不应被视为最终主线源码结构的一部分。

它更接近历史遗留或运行产物残留，尤其其中的 `artifacts` 一类内容，不应该参与未来主线架构设计，也不应该打进包里。

### 2. 根目录 `module2`

当前它主要表现为运行日志目录，而不是源码目录。

因此：

- 不应将它视为迁移目标
- 不应将它纳入最终架构蓝图
- 不应将它打入桌面安装包

### 3. `frontend/dist`

这是构建产物，不是源码。

它在生产和 Electron 打包阶段需要被消费，但不应被当成前端源码结构的一部分。

## 对外入口与内部引擎的关系

最终结构中必须严格区分：

- 公共入口
- 内部引擎
- 兼容代理
- 运行产物

具体定义如下：

- `backend/app`：唯一公共入口
- `backend/module2`：内部文档抽取引擎
- `backend/module4`：内部图谱与风控引擎
- `backend/auth`：历史兼容代理
- `.runlogs` / `dist-electron` / `module2/runlogs`：运行产物

这一定义非常重要，因为后续所有“代码归并”都不能破坏这个边界。

## 最终最优的运行方式

最终推荐运行方式应当围绕统一入口展开：

- 前端默认运行在 `3000`
- 统一 FastAPI 网关默认运行在 `3001`
- 前端以统一网关作为公共 API 面
- Electron 以统一网关作为桌面后端入口

内部 Module2 / Module4 是否仍然使用自身进程、sidecar 或 managed 模式，不影响“对外统一”的成立。

换句话说：

`统一的是公共入口，不是强制取消一切内部引擎边界。`

## 打包边界与软件封装要求

最终架构必须服务于桌面软件封装，而不是只服务于源码树好看。

因此必须遵守以下原则。

## 必须打包的内容

- `backend/app/**`
- `backend/module2/app/**`
- `backend/module4/app/**`
- `backend/auth/server.cjs`
- `frontend/dist/**`
- `scripts/**/*.cjs`
- `electron/**`
- 运行所需配置文件

## 必须排除的内容

- `backend/backend/**`
- `module2/runlogs/**`
- `.runlogs/**`
- `frontend/.runlogs/**`
- `backend/module2/artifacts/**`
- `backend/module4/workspaces/**`
- `backend/tests/**`
- `backend/module2/tests/**`
- `backend/module4/tests/**`
- `frontend/e2e/**`
- `dist-electron/**`
- `.pytest_cache/**`
- `.pytest_tmp/**`
- 各类 `trace_rois`、临时截图、测试样本输出

## 打包总原则

运行时代码可以被打包，运行时产生的数据不能被预打包。

也就是说：

- code 进入包
- runtime data 进入用户可写目录

## 对“最终最优目录结构”的进一步约束

为了防止后续重构又变回混乱状态，必须遵守以下约束。

## 1. 不把所有逻辑硬搬进 `backend/app`

`backend/app` 是公共平台壳，不是业务内核总仓库。

## 2. 不再新增第二套公共后端入口

未来不应再出现新的对外公共 API 根目录去和 `backend/app` 竞争。

## 3. Module2 和 Module4 可以继续内部拆分，但只能在各自边界内进行

也就是说：

- Module2 的 parser、runtime、assistant1 可以继续优化
- Module4 的 app_runtime、query、ingest、rule 可以继续优化
- 但它们不应该被“视觉统一”冲动驱动，强行回塞到 `backend/app`

## 4. 前端继续走特性分层，不引入 MVVM

后续前端优化应重点关注：

- 巨型工作台组件拆分
- 页面容器与模块组件解耦
- `shared/api` 保持稳定
- `lib` 保持轻量

## 5. 运行产物永远不参与架构归类

日志、截图、构建输出、历史 artifact、workspace、trace 图像，都不能再被视为“目录结构的一部分”。

## 面向后续迁移的执行边界

从现在开始，后续所有迁移都应当围绕这份目录蓝图执行。

允许继续做的事情：

- 在 `backend/module2/app/runtime` 和 `core` 内继续中粒度归并
- 在 `backend/module4/app/services` 内继续收敛职责
- 在 `frontend/pages`、`features`、`components` 中继续拆分大组件
- 清理兼容层之外的历史死代码
- 清理运行产物和不应打包的目录

不允许做的事情：

- 破坏 `/api/*`、`/extract/*`、`/module4/*` 对外契约
- 改变 artifact 语义
- 破坏 DOCX -> PDF -> PDF 解析主链路
- 破坏 MinerU / Gemini Vision 能力链路
- 在迁移中把运行产物重新打包进去
- 为了“文件看起来少”而重新把多个边界完全不同的职责揉回一个巨型文件

## 验收标准

当项目最终迁移达到本文档定义的目标时，应满足以下验收条件：

1. `backend/app` 成为唯一公共后端入口
2. auth、assistant、extract、module4 对外契约全部稳定
3. frontend 默认围绕统一网关工作
4. Electron 默认围绕统一网关工作
5. DOCX 异步转 PDF 与 PDF 主解析链路保持完整
6. MinerU 与 Gemini Vision 能力仍在主工作流中
7. assistant1 grounded chat 保持可用
8. Module2 -> Module4 同步保持可用
9. Module4 graph / alerts / rules / explain / simulate 保持可用
10. 打包结果不再携带运行垃圾、历史 artifacts、trace_rois、测试输出
11. 打包后的软件仍然可以继续迭代开发，而不是“一次性死结构”

## 最终推荐语句

对当前项目而言，最终最优整体框架与目录结构可以正式表述为：

`以 backend/app 作为唯一统一 FastAPI 公共入口，以 backend/module2 和 backend/module4 作为边界清晰的内部业务引擎，前端继续保持 React + Vite，桌面封装继续保持 Electron，并通过严格区分主线源码、兼容层、运行产物和打包边界，构建一个既不降级当前完整工作流、又适合后续持续开发和软件封装的分层 MVC 风格架构。`

这就是当前项目的最终最优方案。
