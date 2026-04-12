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

const module2Dir = path.join(rootDir, 'backend', 'module2');
const module2PythonExec = resolvePythonExec({
  overrideExec: process.env.MODULE2_PYTHON,
  preferredVenvDirs: [
    path.join(rootDir, '.venv-module2-py311'),
    path.join(module2Dir, '.venv'),
    path.join(rootDir, '.venv'),
  ],
});

const host = process.env.MODULE2_HOST || '0.0.0.0';
const port = process.env.MODULE2_PORT || '8000';
const reloadArgs = reloadEnabled('MODULE2_UVICORN_RELOAD', true)
  ? buildReloadArgs({
      sourceDirs: ['app'],
      excludeGlobs: [
        'artifacts/*',
        'artifacts/**',
        '.cache/*',
        '.cache/**',
        '.runlogs/*',
        '.runlogs/**',
      ],
    })
  : [];

const args = ['-m', 'uvicorn', 'app.main:app', '--host', host, '--port', port, ...reloadArgs];

console.log(`[dev:module2] python=${module2PythonExec}`);
console.log(`[dev:module2] cwd=${module2Dir}`);
console.log(`[dev:module2] command=${formatCommand(module2PythonExec, args)}`);

const child = spawn(module2PythonExec, args, {
  cwd: module2Dir,
  stdio: 'inherit',
  shell: false,
  env: buildPythonRuntimeEnv({
    baseEnv: buildManagedRuntimeEnv({
      baseEnv: process.env,
      scopes: ['backend', 'module2'],
    }),
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
  console.error(`[dev:module2] exited with ${exitInfo}`);
  stop(typeof code === 'number' ? code : 1);
});

process.on('SIGINT', () => stop(0));
process.on('SIGTERM', () => stop(0));
