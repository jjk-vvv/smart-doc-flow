const path = require('path');
const { spawn } = require('child_process');
const electronExec = require('electron');

const { buildNodeRuntimeEnv, nodeExec, rootDir } = require('./python-service-utils.cjs');

const gatewayPort = process.env.GATEWAY_PORT || '3001';
const frontendPort = process.env.FRONTEND_PORT || '3000';
const gatewayUrl = `http://127.0.0.1:${gatewayPort}`;
const frontendUrl = process.env.SMART_DOC_FLOW_ELECTRON_RENDERER_URL || `http://127.0.0.1:${frontendPort}`;
const readyUrl = `${gatewayUrl}/gateway/ready?scope=${encodeURIComponent(process.env.GATEWAY_READY_SCOPE || 'backend')}`;
const waitTimeoutMs = Math.max(10_000, Number(process.env.GATEWAY_WAIT_TIMEOUT_MS || 180_000));
const waitPollIntervalMs = Math.max(250, Number(process.env.GATEWAY_WAIT_POLL_INTERVAL_MS || 1_000));

let backendChild = null;
let frontendChild = null;
let electronChild = null;
let shuttingDown = false;

const buildElectronChildEnv = (baseEnv) => {
  const env = { ...baseEnv };
  delete env.ELECTRON_RUN_AS_NODE;
  delete env.ELECTRON_NO_ATTACH_CONSOLE;
  return env;
};

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const stopAll = (exitCode = 0) => {
  if (shuttingDown) {
    return;
  }
  shuttingDown = true;
  if (electronChild && !electronChild.killed) {
    electronChild.kill('SIGTERM');
  }
  if (frontendChild && !frontendChild.killed) {
    frontendChild.kill('SIGTERM');
  }
  if (backendChild && !backendChild.killed) {
    backendChild.kill('SIGTERM');
  }
  setTimeout(() => process.exit(exitCode), 500);
};

const waitForHttpOk = async (url) => {
  const startedAt = Date.now();
  while ((Date.now() - startedAt) < waitTimeoutMs) {
    try {
      const response = await fetch(url, { method: 'GET' });
      if (response.ok) {
        return;
      }
    } catch {
      // Retry until timeout.
    }
    await sleep(waitPollIntervalMs);
  }
  throw new Error(`Timed out waiting for ${url}`);
};

backendChild = spawn(nodeExec, [path.join(rootDir, 'scripts', 'dev-backend-fastapi.cjs')], {
  cwd: rootDir,
  stdio: 'inherit',
  shell: false,
  env: buildNodeRuntimeEnv({
    baseEnv: {
      ...process.env,
      MODULE2_ENABLED: process.env.MODULE2_ENABLED || '0',
      UNIFIED_EXTRACT_MODULE2_SIDECAR_MODE: process.env.UNIFIED_EXTRACT_MODULE2_SIDECAR_MODE || 'managed',
    },
  }),
});

frontendChild = spawn(
  nodeExec,
  [
    path.join(rootDir, 'frontend', 'node_modules', 'vite', 'bin', 'vite.js'),
    '--port',
    String(frontendPort),
    '--host',
    '0.0.0.0',
  ],
  {
    cwd: path.join(rootDir, 'frontend'),
    stdio: 'inherit',
    shell: false,
    env: buildNodeRuntimeEnv({ baseEnv: process.env }),
  },
);

for (const [name, child] of [
  ['backend', backendChild],
  ['frontend', frontendChild],
]) {
  child.on('exit', (code, signal) => {
    if (shuttingDown) {
      return;
    }
    const exitInfo = typeof code === 'number' ? `code ${code}` : `signal ${signal}`;
    console.error(`[desktop:dev] ${name} exited with ${exitInfo}`);
    stopAll(typeof code === 'number' ? code : 1);
  });
}

Promise.all([waitForHttpOk(readyUrl), waitForHttpOk(frontendUrl)])
  .then(() => {
    console.log(`[desktop:dev] gateway ready at ${readyUrl}`);
    console.log(`[desktop:dev] renderer ready at ${frontendUrl}`);

    electronChild = spawn(electronExec, [rootDir], {
      cwd: rootDir,
      stdio: 'inherit',
      shell: false,
      env: buildElectronChildEnv({
        ...process.env,
        SMART_DOC_FLOW_ELECTRON_MANAGED_BACKEND: '0',
        SMART_DOC_FLOW_ELECTRON_GATEWAY_URL: gatewayUrl,
        SMART_DOC_FLOW_ELECTRON_RENDERER_URL: frontendUrl,
        SMART_DOC_FLOW_ELECTRON_READY_SCOPE: process.env.SMART_DOC_FLOW_ELECTRON_READY_SCOPE || 'backend',
        SMART_DOC_FLOW_ELECTRON_OPEN_DEVTOOLS:
          process.env.SMART_DOC_FLOW_ELECTRON_OPEN_DEVTOOLS || '1',
      }),
    });

    electronChild.on('exit', (code, signal) => {
      if (shuttingDown) {
        return;
      }
      const exitInfo = typeof code === 'number' ? `code ${code}` : `signal ${signal}`;
      console.log(`[desktop:dev] electron exited with ${exitInfo}`);
      stopAll(typeof code === 'number' ? code : 0);
    });
  })
  .catch((error) => {
    console.error(`[desktop:dev] ${error instanceof Error ? error.message : String(error)}`);
    stopAll(1);
  });

process.on('SIGINT', () => stopAll(0));
process.on('SIGTERM', () => stopAll(0));
