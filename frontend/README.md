# Smart Doc Flow Web 工作台

React、TypeScript 和 Vite 构建的 Web 前端。完整环境准备见[项目说明](../README.md)。

在仓库根目录执行：

```powershell
npm --prefix frontend ci
npm run dev:frontend
npm run build:frontend
```

默认监听 `3000`，通过 Vite 将 `/api`、`/extract`、`/module1`、`/module3`、`/module4` 和 `/gateway` 请求转发到 `3001`。使用 `npm run dev` 可以同时启动统一后端。

- `pages/`：页面及工作台。
- `features/`：跨页面业务功能。
- `components/`：通用组件。
- `shared/`：API、状态和共享代码。
- `assets/`：被应用引用的图片、视频等资源。
- `e2e/`：浏览器回归和诊断脚本；执行结果进入忽略目录。

开发服务器和预览服务器允许的公网域名为 `www.smart-doc-flow.cn`。FRP 配置仍需指向实际前端端口。运行数据、构建产物和真实密钥不纳入版本管理。
