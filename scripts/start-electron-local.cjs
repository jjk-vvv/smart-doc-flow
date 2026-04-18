const path = require('path');
const { spawn } = require('child_process');
const electronExec = require('electron');

const {
  buildManagedRuntimeEnv,
  buildNodeRuntimeEnv,
  nodeExec,
  rootDir,
} = require('./python-service-utils.cjs');

const managedBackendEnv = buildManagedRuntimeEnv({
  baseEnv: process.env,
  scopes: ['backend'],
});
const gatewayPort = managedBackendEnv.GATEWAY_PORT || process.env.GATEWAY_PORT || '3001';
const gatewayUrl = (process.env.SMART_DOC_FLOW_ELECTRON_GATEWAY_URL || `http://127.0.0.1:${gatewayPort}`).replace(/\/+$/, '');
const readyUrl = `${gatewayUrl}/gateway/ready?scope=${encodeURIComponent(process.env.GATEWAY_READY_SCOPE || 'all')}`;
const waitTimeoutMs = Math.max(10_000, Number(process.env.GATEWAY_WAIT_TIMEOUT_MS || 180_000));
const waitPollIntervalMs = Math.max(250, Number(process.env.GATEWAY_WAIT_POLL_INTERVAL_MS || 1_000));

let backendChild = null;
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
  if (backendChild && !backendChild.killed) {
    backendChild.kill('SIGTERM');
  }
  setTimeout(() => process.exit(exitCode), 500);
};

const waitForGatewayReady = async () => {
  const startedAt = Date.now();
  while ((Date.now() - startedAt) < waitTimeoutMs) {
    try {
      const response = await fetch(readyUrl, { method: 'GET' });
      if (response.ok) {
        const payload = await response.json().catch(() => ({}));
        if (payload && payload.ok) {
          console.log(`[desktop:local] gateway ready at ${readyUrl}`);
          return;
        }
      }
    } catch {
      // Retry until timeout.
    }
    await sleep(waitPollIntervalMs);
  }
  throw new Error(`Timed out waiting for ${readyUrl}`);
};

backendChild = spawn(nodeExec, [path.join(rootDir, 'scripts', 'start-backend-fastapi.cjs')], {
  cwd: rootDir,
  stdio: 'inherit',
  shell: false,
  env: buildNodeRuntimeEnv({
    baseEnv: {
      ...managedBackendEnv,
      MODULE2_ENABLED: process.env.MODULE2_ENABLED || '0',
      UNIFIED_EXTRACT_MODULE2_SIDECAR_MODE: process.env.UNIFIED_EXTRACT_MODULE2_SIDECAR_MODE || 'disabled',
      UNIFIED_GATEWAY_MODULE4_SIDECAR_MODE: process.env.UNIFIED_GATEWAY_MODULE4_SIDECAR_MODE || 'disabled',
    },
  }),
});

backendChild.on('exit', (code, signal) => {
  if (shuttingDown) {
    return;
  }
  const exitInfo = typeof code === 'number' ? `code ${code}` : `signal ${signal}`;
  console.error(`[desktop:local] backend exited with ${exitInfo}`);
  stopAll(typeof code === 'number' ? code : 1);
});

waitForGatewayReady()
  .then(() => {
    electronChild = spawn(electronExec, [rootDir], {
      cwd: rootDir,
      stdio: 'inherit',
      shell: false,
      env: buildElectronChildEnv({
        ...process.env,
        ...managedBackendEnv,
        SMART_DOC_FLOW_ELECTRON_MANAGED_BACKEND: '0',
        SMART_DOC_FLOW_ELECTRON_GATEWAY_URL: gatewayUrl,
        SMART_DOC_FLOW_ELECTRON_READY_SCOPE: process.env.SMART_DOC_FLOW_ELECTRON_READY_SCOPE || 'all',
      }),
    });

    electronChild.on('exit', (code, signal) => {
      if (shuttingDown) {
        return;
      }
      const exitInfo = typeof code === 'number' ? `code ${code}` : `signal ${signal}`;
      console.log(`[desktop:local] electron exited with ${exitInfo}`);
      stopAll(typeof code === 'number' ? code : 0);
    });
  })
  .catch((error) => {
    console.error(`[desktop:local] ${error instanceof Error ? error.message : String(error)}`);
    stopAll(1);
  });

process.on('SIGINT', () => stopAll(0));
process.on('SIGTERM', () => stopAll(0));
