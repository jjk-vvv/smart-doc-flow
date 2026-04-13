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

const module4Dir = path.join(rootDir, 'backend', 'module4');
const module4PythonExec = resolvePythonExec({
  overrideExec: process.env.MODULE4_PYTHON,
  preferredVenvDirs: [
    path.join(rootDir, '.venv-module4-py311'),
    path.join(rootDir, '.venv'),
  ],
});

const managedEnv = buildManagedRuntimeEnv({
  baseEnv: process.env,
  scopes: ['backend', 'module4'],
});
const host = managedEnv.MODULE4_HOST || process.env.MODULE4_HOST || '0.0.0.0';
const port = managedEnv.MODULE4_PORT || process.env.MODULE4_PORT || '8100';
const reloadArgs = reloadEnabled('MODULE4_UVICORN_RELOAD', true)
  ? buildReloadArgs({
      sourceDirs: ['app'],
      excludeGlobs: [
        'workspaces/*',
        'workspaces/**',
        '.cache/*',
        '.cache/**',
        '.runlogs/*',
        '.runlogs/**',
      ],
    })
  : [];

const args = ['-m', 'uvicorn', 'app.main:app', '--host', host, '--port', port, ...reloadArgs];

console.log(`[dev:module4] python=${module4PythonExec}`);
console.log(`[dev:module4] cwd=${module4Dir}`);
console.log(`[dev:module4] command=${formatCommand(module4PythonExec, args)}`);

const child = spawn(module4PythonExec, args, {
  cwd: module4Dir,
  stdio: 'inherit',
  shell: false,
  env: buildPythonRuntimeEnv({
    baseEnv: managedEnv,
    pythonExec: module4PythonExec,
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
  console.error(`[dev:module4] exited with ${exitInfo}`);
  stop(typeof code === 'number' ? code : 1);
});

process.on('SIGINT', () => stop(0));
process.on('SIGTERM', () => stop(0));
