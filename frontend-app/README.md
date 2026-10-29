# Smart Doc Flow 移动端

面向移动设备的 React/Vite 前端，包含 Capacitor Android 工程。完整环境准备见[项目说明](../README.md)。

在仓库根目录执行：

```powershell
npm --prefix frontend-app ci
npm run dev:app
npm run build:frontend:app:web
npm run mobile:cap:doctor
npm run mobile:cap:sync
```

开发入口默认为 `3002`，统一后端为 `3001`；`npm run dev:app` 同时启动两者。Web 构建默认部署在 `/m/`，原生构建产物位于 `dist-native/`。覆盖方式见 `.env.example` 和 `capacitor.config.ts`。

- `pages/`、`features/`、`components/`、`shared/`：移动端界面与业务代码。
- `assets/`：应用资源。
- `android/`：Android 工程源码、资源及 Gradle wrapper，需要提交。
- `e2e/`：移动端 Web 回归脚本。

Android SDK、`local.properties`、Gradle 缓存、构建目录、Capacitor 复制的 Web 产物及真实 `.env` 仅保留在本地。原生设备使用的后端地址应填写可由设备访问的网关地址；浏览器构建变量会进入客户端，不应填写服务端密钥。
