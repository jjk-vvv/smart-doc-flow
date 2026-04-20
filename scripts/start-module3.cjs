const path = require('path');
const { spawn } = require('child_process');
const {
  buildManagedRuntimeEnv,
  buildPythonRuntimeEnv,
  formatCommand,
  resolvePythonExec,
  rootDir,
} = require('./python-service-utils.cjs');

const module3ConfigDir = path.join(rootDir, 'backend', 'app', 'modules', 'module3');
const module3RunCwd = path.join(rootDir, 'backend');
const module3PythonExec = resolvePythonExec({
  overrideExec: process.env.MODULE3_PYTHON,
  preferredVenvDirs: [
    path.join(rootDir, '.venv'),
    path.join(rootDir, '.venv-module3-py311'),
    path.join(module3ConfigDir, '.venv'),
    path.join(rootDir, '.venv-module2-py311'),
  ],
});

const managedEnv = buildManagedRuntimeEnv({
  baseEnv: process.env,
  scopes: ['backend', 'module3'],
});
const host = managedEnv.MODULE3_HOST || process.env.MODULE3_HOST || '0.0.0.0';
const port = managedEnv.MODULE3_PORT || process.env.MODULE3_PORT || '8001';
const args = ['-m', 'uvicorn', 'app.modules.module3.main:app', '--host', host, '--port', port];

console.log(`[start:module3] python=${module3PythonExec}`);
console.log(`[start:module3] cwd=${module3RunCwd}`);
console.log(`[start:module3] command=${formatCommand(module3PythonExec, args)}`);

const child = spawn(module3PythonExec, args, {
  cwd: module3RunCwd,
  stdio: 'inherit',
  shell: false,
  env: buildPythonRuntimeEnv({
    baseEnv: managedEnv,
    pythonExec: module3PythonExec,
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
  console.error(`[start:module3] exited with ${exitInfo}`);
  stop(typeof code === 'number' ? code : 1);
});

process.on('SIGINT', () => stop(0));
process.on('SIGTERM', () => stop(0));
