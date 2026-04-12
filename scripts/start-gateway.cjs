const path = require('path');
const { spawn } = require('child_process');
const {
  buildManagedRuntimeEnv,
  buildPythonRuntimeEnv,
  formatCommand,
  resolvePythonExec,
  rootDir,
} = require('./python-service-utils.cjs');

const backendDir = path.join(rootDir, 'backend');
const gatewayPythonExec = resolvePythonExec({
  overrideExec: process.env.GATEWAY_PYTHON,
  preferredVenvDirs: [
    path.join(rootDir, '.venv-module2-py311'),
    path.join(rootDir, '.venv'),
  ],
});

const managedEnv = buildManagedRuntimeEnv({
  baseEnv: { ...process.env },
  scopes: ['module2', 'backend'],
});
const host = managedEnv.GATEWAY_HOST || process.env.GATEWAY_HOST || '0.0.0.0';
const port = managedEnv.GATEWAY_PORT || process.env.GATEWAY_PORT || '3001';
const module2Port = managedEnv.MODULE2_PORT || process.env.MODULE2_PORT || '8000';
const module2UpstreamUrl =
  managedEnv.MODULE2_UPSTREAM_URL
  || process.env.MODULE2_UPSTREAM_URL
  || `http://127.0.0.1:${module2Port}`;
const module4UpstreamUrl =
  managedEnv.MODULE4_UPSTREAM_URL
  || process.env.MODULE4_UPSTREAM_URL
  || 'http://127.0.0.1:8100';
const args = ['-m', 'uvicorn', 'app.main:app', '--host', host, '--port', port];

console.log(`[start:gateway] python=${gatewayPythonExec}`);
console.log(`[start:gateway] cwd=${backendDir}`);
console.log(`[start:gateway] command=${formatCommand(gatewayPythonExec, args)}`);

const child = spawn(gatewayPythonExec, args, {
  cwd: backendDir,
  stdio: 'inherit',
  shell: false,
  env: buildPythonRuntimeEnv({
    baseEnv: {
      ...managedEnv,
      MODULE2_UPSTREAM_URL: module2UpstreamUrl,
      MODULE4_UPSTREAM_URL: module4UpstreamUrl,
      UNIFIED_GATEWAY_MODULE4_SIDECAR_MODE: process.env.UNIFIED_GATEWAY_MODULE4_SIDECAR_MODE || 'auto',
    },
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
  console.error(`[start:gateway] exited with ${exitInfo}`);
  stop(typeof code === 'number' ? code : 1);
});

process.on('SIGINT', () => stop(0));
process.on('SIGTERM', () => stop(0));
