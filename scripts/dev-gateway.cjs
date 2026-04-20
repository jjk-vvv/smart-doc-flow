const path = require('path');
const { spawn } = require('child_process');
const {
  buildManagedRuntimeEnv,
  buildPythonRuntimeEnv,
  buildReloadArgs,
  formatCommand,
  reloadEnabled,
  resolvePythonExec,
  rootDir,
} = require('./python-service-utils.cjs');

const backendDir = path.join(rootDir, 'backend');
const gatewayPythonExec = resolvePythonExec({
  overrideExec: process.env.GATEWAY_PYTHON,
  preferredVenvDirs: [
    path.join(rootDir, '.venv'),
    path.join(rootDir, '.venv-module2-py311'),
  ],
});

const managedEnv = buildManagedRuntimeEnv({
  baseEnv: process.env,
  scopes: ['backend'],
});
const host = managedEnv.GATEWAY_HOST || process.env.GATEWAY_HOST || '0.0.0.0';
const port = managedEnv.GATEWAY_PORT || process.env.GATEWAY_PORT || '3001';
const loopbackHost = host === '0.0.0.0' || host === '::' ? '127.0.0.1' : host;
const gatewayBaseUrl =
  (managedEnv.GATEWAY_BASE_URL || process.env.GATEWAY_BASE_URL || `http://${loopbackHost}:${port}`)
    .replace(/\/+$/, '');
const reloadArgs = reloadEnabled('GATEWAY_UVICORN_RELOAD', true)
  ? buildReloadArgs({
      sourceDirs: ['app'],
    })
  : [];

const args = ['-m', 'uvicorn', 'app.main:app', '--host', host, '--port', port, ...reloadArgs];

console.log(`[dev:gateway] python=${gatewayPythonExec}`);
console.log(`[dev:gateway] cwd=${backendDir}`);
console.log(`[dev:gateway] command=${formatCommand(gatewayPythonExec, args)}`);

const child = spawn(gatewayPythonExec, args, {
  cwd: backendDir,
  stdio: 'inherit',
  shell: false,
  env: buildPythonRuntimeEnv({
    baseEnv: buildManagedRuntimeEnv({
      baseEnv: {
        ...managedEnv,
        GATEWAY_BASE_URL: gatewayBaseUrl,
        MODULE2_UPSTREAM_URL: gatewayBaseUrl,
        MODULE4_UPSTREAM_URL: gatewayBaseUrl,
        UNIFIED_EXTRACT_MODULE2_SIDECAR_MODE: 'disabled',
        UNIFIED_GATEWAY_MODULE4_SIDECAR_MODE: 'disabled',
      },
      scopes: ['backend'],
    }),
    pythonExec: gatewayPythonExec,
  }),
});

let shuttingDown = false;

const stop = (exitCode = 0) => {
  if (shuttingDown) return;
  shuttingDown = true;
  if (!child.killed) {
    child.kill('SIGTERM');
  }
  setTimeout(() => process.exit(exitCode), 300);
};

child.on('exit', (code, signal) => {
  if (shuttingDown) return;
  const exitInfo = typeof code === 'number' ? `code ${code}` : `signal ${signal}`;
  console.error(`[dev:gateway] exited with ${exitInfo}`);
  stop(typeof code === 'number' ? code : 1);
});

process.on('SIGINT', () => stop(0));
process.on('SIGTERM', () => stop(0));
