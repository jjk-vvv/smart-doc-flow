const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const { app, BrowserWindow, dialog, shell } = require('electron');

const gatewayHost = process.env.SMART_DOC_FLOW_ELECTRON_GATEWAY_HOST || process.env.GATEWAY_HOST || '127.0.0.1';
const gatewayPort = process.env.SMART_DOC_FLOW_ELECTRON_GATEWAY_PORT || process.env.GATEWAY_PORT || '3001';
const gatewayUrl = (
  process.env.SMART_DOC_FLOW_ELECTRON_GATEWAY_URL
  || `http://${gatewayHost}:${gatewayPort}`
).replace(/\/+$/, '');
const rendererUrl = (
  process.env.SMART_DOC_FLOW_ELECTRON_RENDERER_URL
  || gatewayUrl
).replace(/\/+$/, '');
const managedBackendEnabled = !['0', 'false', 'no', 'off'].includes(
  String(process.env.SMART_DOC_FLOW_ELECTRON_MANAGED_BACKEND || '1').trim().toLowerCase(),
);
const gatewayReadyScope = String(process.env.SMART_DOC_FLOW_ELECTRON_READY_SCOPE || 'all').trim() || 'all';
const gatewayWaitTimeoutMs = Math.max(10_000, Number(process.env.SMART_DOC_FLOW_ELECTRON_WAIT_TIMEOUT_MS || 180_000));
const gatewayWaitPollIntervalMs = Math.max(
  250,
  Number(process.env.SMART_DOC_FLOW_ELECTRON_WAIT_POLL_INTERVAL_MS || 1_000),
);
const openDevtools = !app.isPackaged || String(process.env.SMART_DOC_FLOW_ELECTRON_OPEN_DEVTOOLS || '').trim() === '1';
const appSourceDir = app.getAppPath();
const appRootDir = app.isPackaged ? process.resourcesPath : appSourceDir;
const windowIconPath = path.join(appSourceDir, 'electron', 'icon.png');
const packagedDataRoot = app.isPackaged ? path.join(app.getPath('userData'), 'runtime-data') : '';
const electronLogFile = (() => {
  const configured = String(process.env.SMART_DOC_FLOW_ELECTRON_LOG_FILE || '').trim();
  if (configured) {
    return configured;
  }
  try {
    return path.join(app.getPath('temp'), 'smart-doc-flow-electron.log');
  } catch {
    return path.join(process.cwd(), 'smart-doc-flow-electron.log');
  }
})();

let mainWindow = null;
let backendProcess = null;
let quitting = false;

const writeElectronLog = (...parts) => {
  try {
    fs.mkdirSync(path.dirname(electronLogFile), { recursive: true });
    const line = `[${new Date().toISOString()}] ${parts.map((item) => {
      if (item instanceof Error) {
        return item.stack || item.message;
      }
      if (typeof item === 'object') {
        try {
          return JSON.stringify(item);
        } catch {
          return String(item);
        }
      }
      return String(item);
    }).join(' ')}\n`;
    fs.appendFileSync(electronLogFile, line, 'utf8');
  } catch {
    // Ignore logging failures.
  }
};

const escapeHtml = (value) =>
  String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

const buildLoadingHtml = (message, detail = '') => `
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Smart Doc Flow</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #f5f2ea;
        --panel: rgba(255, 252, 246, 0.88);
        --text: #1d1a16;
        --muted: #6d655a;
        --accent: #0f766e;
        --border: rgba(29, 26, 22, 0.08);
      }
      body {
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background:
          radial-gradient(circle at top left, rgba(15, 118, 110, 0.18), transparent 38%),
          radial-gradient(circle at bottom right, rgba(180, 83, 9, 0.14), transparent 32%),
          var(--bg);
        font-family: "Microsoft YaHei UI", "PingFang SC", "Segoe UI", sans-serif;
        color: var(--text);
      }
      .panel {
        width: min(560px, calc(100vw - 48px));
        border: 1px solid var(--border);
        border-radius: 24px;
        background: var(--panel);
        box-shadow: 0 20px 60px rgba(29, 26, 22, 0.12);
        padding: 28px 30px;
        backdrop-filter: blur(12px);
      }
      .eyebrow {
        margin: 0 0 10px;
        color: var(--accent);
        font-size: 12px;
        letter-spacing: 0.12em;
        text-transform: uppercase;
      }
      h1 {
        margin: 0;
        font-size: 26px;
        line-height: 1.2;
      }
      p {
        margin: 14px 0 0;
        color: var(--muted);
        line-height: 1.65;
        font-size: 14px;
        white-space: pre-wrap;
        word-break: break-word;
      }
      .pulse {
        width: 12px;
        height: 12px;
        border-radius: 999px;
        background: var(--accent);
        box-shadow: 0 0 0 rgba(15, 118, 110, 0.45);
        animation: pulse 1.6s infinite;
        margin-bottom: 18px;
      }
      @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(15, 118, 110, 0.45); }
        70% { box-shadow: 0 0 0 18px rgba(15, 118, 110, 0); }
        100% { box-shadow: 0 0 0 0 rgba(15, 118, 110, 0); }
      }
    </style>
  </head>
  <body>
    <section class="panel">
      <div class="pulse"></div>
      <div class="eyebrow">Smart Doc Flow</div>
      <h1>${escapeHtml(message)}</h1>
      <p>${escapeHtml(detail)}</p>
    </section>
  </body>
</html>`;

const loadWindowHtml = async (window, message, detail = '') => {
  if (!window || window.isDestroyed()) {
    return;
  }
  writeElectronLog('loadWindowHtml', { message, detail });
  await window.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(buildLoadingHtml(message, detail))}`);
};

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const waitForHttpOk = async (url, { timeoutMs, pollIntervalMs, validator } = {}) => {
  const startedAt = Date.now();
  const effectiveTimeoutMs = Math.max(2_000, Number(timeoutMs || gatewayWaitTimeoutMs));
  const effectivePollIntervalMs = Math.max(200, Number(pollIntervalMs || gatewayWaitPollIntervalMs));
  let lastError = '';

  while ((Date.now() - startedAt) < effectiveTimeoutMs) {
    try {
      const response = await fetch(url, { method: 'GET', cache: 'no-store' });
      if (response.ok) {
        const payload = await response.json().catch(() => ({}));
        if (!validator || validator(payload, response)) {
          return { ok: true, payload, response };
        }
      } else {
        lastError = `HTTP ${response.status}`;
      }
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await sleep(effectivePollIntervalMs);
  }

  throw new Error(`Timed out waiting for ${url}${lastError ? `: ${lastError}` : ''}`);
};

const spawnManagedBackend = () => {
  if (backendProcess) {
    return backendProcess;
  }

  const backendScriptPath = app.isPackaged
    ? path.join(process.resourcesPath, 'app-runtime', 'scripts', 'start-backend-fastapi.cjs')
    : path.join(appSourceDir, 'scripts', 'start-backend-fastapi.cjs');
  const childEnv = {
    ...process.env,
    ELECTRON_RUN_AS_NODE: '1',
    ELECTRON_NO_ATTACH_CONSOLE: process.env.ELECTRON_NO_ATTACH_CONSOLE || '1',
    MODULE2_ENABLED: process.env.MODULE2_ENABLED || '0',
    UNIFIED_EXTRACT_MODULE2_SIDECAR_MODE: process.env.UNIFIED_EXTRACT_MODULE2_SIDECAR_MODE || 'disabled',
    UNIFIED_GATEWAY_MODULE4_SIDECAR_MODE: process.env.UNIFIED_GATEWAY_MODULE4_SIDECAR_MODE || 'disabled',
    SMART_DOC_FLOW_PARENT_PID: String(process.pid),
  };
  if (!String(childEnv.SMART_DOC_FLOW_DATA_ROOT || '').trim() && packagedDataRoot) {
    childEnv.SMART_DOC_FLOW_DATA_ROOT = packagedDataRoot;
  }
  writeElectronLog('spawnManagedBackend', { backendScriptPath, cwd: appRootDir, gatewayUrl });

  backendProcess = spawn(process.execPath, [backendScriptPath], {
    cwd: appRootDir,
    env: childEnv,
    stdio: app.isPackaged ? 'ignore' : 'inherit',
    shell: false,
    windowsHide: true,
  });

  backendProcess.on('exit', (code, signal) => {
    const exitInfo = typeof code === 'number' ? `code ${code}` : `signal ${signal}`;
    writeElectronLog('managedBackendExit', { code, signal, exitInfo });
    backendProcess = null;
    if (quitting) {
      return;
    }
    const detail = `本地后端已经退出：${exitInfo}\n\n请检查 FastAPI 启动配置、Module2 sidecar 和日志后再重试。`;
    if (mainWindow && !mainWindow.isDestroyed()) {
      void loadWindowHtml(mainWindow, '本地服务已中断', detail);
    }
    dialog.showErrorBox('Smart Doc Flow', detail);
  });

  return backendProcess;
};

const stopManagedBackend = () => {
  if (!backendProcess) {
    return;
  }
  writeElectronLog('stopManagedBackend');
  const child = backendProcess;
  backendProcess = null;
  if (!child.killed) {
    child.kill('SIGTERM');
  }
};

const createMainWindow = async () => {
  writeElectronLog('createMainWindow');
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 1180,
    minHeight: 760,
    show: false,
    backgroundColor: '#f5f2ea',
    title: 'Smart Doc Flow',
    icon: fs.existsSync(windowIconPath) ? windowIconPath : undefined,
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    writeElectronLog('openExternal', { url });
    void shell.openExternal(url);
    return { action: 'deny' };
  });
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith(rendererUrl) && !url.startsWith(gatewayUrl)) {
      event.preventDefault();
      void shell.openExternal(url);
    }
  });
  mainWindow.once('ready-to-show', () => {
    writeElectronLog('mainWindowReadyToShow');
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.show();
    }
  });
  mainWindow.on('closed', () => {
    writeElectronLog('mainWindowClosed');
    mainWindow = null;
  });

  await loadWindowHtml(
    mainWindow,
    '正在启动 Smart Doc Flow',
    '统一 FastAPI 后端和文档处理链路正在准备中，请稍候。',
  );
};

const bootRenderer = async () => {
  writeElectronLog('bootRendererStart', { managedBackendEnabled, gatewayUrl, rendererUrl, gatewayReadyScope });
  if (managedBackendEnabled) {
    spawnManagedBackend();
  }

  await loadWindowHtml(
    mainWindow,
    '正在连接本地服务',
    `正在等待网关就绪：${gatewayUrl}\n\n就绪范围：${gatewayReadyScope}`,
  );
  await waitForHttpOk(
    `${gatewayUrl}/gateway/ready?scope=${encodeURIComponent(gatewayReadyScope)}`,
    {
      timeoutMs: gatewayWaitTimeoutMs,
      pollIntervalMs: gatewayWaitPollIntervalMs,
      validator: (payload) => Boolean(payload && payload.ok),
    },
  );

  if (rendererUrl !== gatewayUrl) {
    await waitForHttpOk(rendererUrl, {
      timeoutMs: gatewayWaitTimeoutMs,
      pollIntervalMs: gatewayWaitPollIntervalMs,
    });
  }

  if (!mainWindow || mainWindow.isDestroyed()) {
    writeElectronLog('bootRendererAbortedWindowGone');
    return;
  }
  writeElectronLog('loadRendererUrl', { rendererUrl });
  await mainWindow.loadURL(rendererUrl);
  if (openDevtools) {
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  }
};

app.setAppUserModelId('com.smartdocflow.desktop');
writeElectronLog('electronMainLoaded', {
  pid: process.pid,
  appRootDir,
  rendererUrl,
  gatewayUrl,
  managedBackendEnabled,
  electronLogFile,
  windowIconPath,
  packagedDataRoot,
});

app.whenReady().then(async () => {
  try {
    writeElectronLog('appWhenReady');
    await createMainWindow();
    await bootRenderer();
  } catch (error) {
    writeElectronLog('appWhenReadyError', error);
    const detail = error instanceof Error ? error.stack || error.message : String(error);
    if (mainWindow && !mainWindow.isDestroyed()) {
      await loadWindowHtml(mainWindow, '启动失败', detail);
    }
    dialog.showErrorBox('Smart Doc Flow 启动失败', detail);
  }
});

app.on('activate', async () => {
  writeElectronLog('appActivate');
  if (BrowserWindow.getAllWindows().length === 0) {
    await createMainWindow();
    try {
      await bootRenderer();
    } catch (error) {
      writeElectronLog('appActivateError', error);
      const detail = error instanceof Error ? error.stack || error.message : String(error);
      dialog.showErrorBox('Smart Doc Flow 启动失败', detail);
    }
  }
});

app.on('window-all-closed', () => {
  writeElectronLog('windowAllClosed', { platform: process.platform });
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  writeElectronLog('beforeQuit');
  quitting = true;
  stopManagedBackend();
});
