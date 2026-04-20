const path = require('path');
const { spawn } = require('child_process');
const {
  buildManagedRuntimeEnv,
  buildPythonRuntimeEnv,
  formatCommand,
  resolvePythonExec,
  rootDir,
} = require('./python-service-utils.cjs');

const module2Dir = path.join(rootDir, 'backend');
const module2PythonExec = resolvePythonExec({
  overrideExec: process.env.MODULE2_PYTHON,
  preferredVenvDirs: [
    path.join(rootDir, '.venv'),
    path.join(rootDir, '.venv-module2-py311'),
  ],
});

const managedEnv = buildManagedRuntimeEnv({
  baseEnv: process.env,
  scopes: ['backend', 'module2'],
});
const host = managedEnv.MODULE2_HOST || process.env.MODULE2_HOST || '0.0.0.0';
const port = managedEnv.MODULE2_PORT || process.env.MODULE2_PORT || '8010';
const args = ['-m', 'uvicorn', 'app.main:app', '--host', host, '--port', port];

console.log(`[start:module2] python=${module2PythonExec}`);
console.log(`[start:module2] cwd=${module2Dir}`);
console.log(`[start:module2] command=${formatCommand(module2PythonExec, args)}`);

const child = spawn(module2PythonExec, args, {
  cwd: module2Dir,
  stdio: 'inherit',
  shell: false,
  env: buildPythonRuntimeEnv({
    baseEnv: managedEnv,
    pythonExec: module2PythonExec,
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
  console.error(`[start:module2] exited with ${exitInfo}`);
  stop(typeof code === 'number' ? code : 1);
});

process.on('SIGINT', () => stop(0));
process.on('SIGTERM', () => stop(0));
