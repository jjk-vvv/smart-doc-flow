# 代码命名与模型配置维护

## 本次检查结果

2026-10-29 遍历项目受 Git 管理及未被忽略的代码、配置、提示词和依赖清单。逐文件路径、内容摘要、检查项目和统计见[审计清单](audits/2026-10-29-code-standards.json)，其中 `summary` 为最终文件数。

检查内容包括 Python 函数、类和文件命名，JavaScript/TypeScript 函数及类命名，脚本文件命名，语法解析，内部模块路径，旧模型和废弃配置引用，重复配置键，以及常见凭据格式。JSON、TOML、INI 和 XML 另做格式解析，PowerShell 使用原生解析器检查。

Java、Gradle 和 SQL 文件完成文本与命名扫描，本轮没有执行 Android 原生编译或数据库在线迁移。检查清单逐项区分解析检查与文本扫描，不将未执行的编译记为通过。

## 模型与配置规范

当前模型保持不变：

| 任务 | 模型 |
| --- | --- |
| 平台助手、模块一文本、模块二助手 | `qwen-plus` |
| 模块二抽取、模块三生成、模块四图谱 | `qwen-max` |
| 模块一、二、三视觉理解 | `qwen3-vl-plus` |
| 模块二、四向量检索 | `text-embedding-3-small` |

- 模块二视觉配置统一为 `MODULE2_VISION_*`，视觉增强开关为 `MODULE2_VISION_ENHANCE_ENABLED`；文本调用使用 `MODULE2_LLM_*`。
- 向量客户端为 `EmbeddingClient`，实现文件为 `assistant_1/embedding_client.py`；视觉客户端为 `VisionExtractor`。名称描述职责，不绑定已经停用的供应商。
- 模块二的已禁用原生传输、原生密钥回退、无效模型回退开关和旧地址别名已经移除。
- 模块三只接受 `chat` 模式，移除旧 Responses 分支和文件直传辅助调用；其他模块仍有效的兼容接口协议不随之删除。
- 默认模型和服务地址与当前本地配置一致；配置示例只放占位值。
- 本地 `.env` 已先备份到 Git 忽略目录，再迁移键名；现有有效密钥及缓存位置保持不变。审计清单只记录键名，不记录密钥值。

## 命名与保留项

Python 模块及函数使用 snake_case，类使用 PascalCase；React 组件使用 PascalCase，普通 JavaScript/TypeScript 函数使用 camelCase；Node/PowerShell 工具文件沿用 kebab-case。标准入口、类型别名和外部接口实现遵循各自语言与框架约定。

以下内容具有当前用途，保留并记录原因：

- OpenAI 兼容协议名称及仍支持的接口形式，不代表调用了旧模型。
- `assistant_1` 包、现有 API 路由和有效数据位置，本轮不做路径重构。
- 四个历史产物清洗器中的旧来源标签，只用于清理过去生成的引用，不参与模型选择或配置读取。
- GraphRAG 0.3.0 使用的 `legacy` 配置形状，是当前依赖所需格式。
- 测试中的 `Rect`、`Matrix` 工厂名遵循被模拟的 PyMuPDF 接口。
- 动态生成的日志键、GraphRAG 查询超时键，以及 POT、tokenizer 消费的环境变量仍有效。

## 复核与后续维护

```powershell
uv tool run --from ruff ruff check backend --config config/quality/ruff.toml
.\.venv\Scripts\python.exe -m pytest
npm run build:frontend
npm run build:frontend:app:web
git diff --check
```

Ruff 配置检测未定义名称、无效导入、未使用代码和表达式错误。项目继续采用既有回调与启动结构，本轮没有对全仓库做纯格式重排。

本轮完整后端回归 1,074 项通过，Web 和移动端 Web 生产构建通过。复核中同时修复了历史动态加载器的导入失败、未定义的数值辅助函数、旧测试接口契约及重复 OpenAPI operation ID。既有病例抽取与 Word 召回回归暴露的问题也已修复并复测。

测试输出仍有第三方弃用提示和测试用短密钥警告；生产认证密钥的长度检查保持启用。构建仍有现有大分块提示。当前旧版组件的 peer 范围与 React 19 不一致，首次安装前端依赖需按锁文件使用 `--legacy-peer-deps`，后续升级组件时应重新验证。

以后增加模型时，应一起更新代码默认值、`.env.example`、实际本地配置、调用消费者和回归测试，不增加新的供应商专属历史别名。
