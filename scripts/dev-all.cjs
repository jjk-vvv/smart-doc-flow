const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

const rootDir = path.resolve(__dirname, '..');
const nodeExec = process.execPath;
const pythonExec = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');

const venvPythonPath = (venvDir) =>
  process.platform === 'win32'
    ? path.join(venvDir, 'Scripts', 'python.exe')
    : path.join(venvDir, 'bin', 'python');

const resolvePythonExec = (serviceDir, overrideExec, extraVenvDirs = []) => {
  if (overrideExec) return overrideExec;

  const candidateVenvDirs = [path.join(serviceDir, '.venv'), ...extraVenvDirs].filter(Boolean);
  for (const venvDir of candidateVenvDirs) {
    const candidate = venvPythonPath(venvDir);
    if (fs.existsSync(candidate)) return candidate;
  }

  return pythonExec;
};

const module2Dir = path.join(rootDir, 'backend', 'module2');
const module4Dir = path.join(rootDir, 'backend', 'module4');
const module2PythonExec = resolvePythonExec(module2Dir, process.env.MODULE2_PYTHON, [
  path.join(rootDir, '.venv-module2-py311'),
  path.join(rootDir, '.venv'),
]);
const module4PythonExec = resolvePythonExec(module4Dir, process.env.MODULE4_PYTHON, [
  path.join(rootDir, '.venv-module4-py311'),
  path.join(rootDir, '.venv'),
]);
const enableModule2 = process.env.MODULE2_ENABLED !== '0';
const enableModule4 = process.env.MODULE4_ENABLED !== '0';
const reloadEnabled = (name, defaultValue = true) => {
  const raw = process.env[name];
  if (raw == null || raw === '') return defaultValue;
  return !['0', 'false', 'no', 'off'].includes(String(raw).trim().toLowerCase());
};

const buildReloadArgs = ({
  sourceDirs = [],
  excludeGlobs = [],
} = {}) => {
  const args = ['--reload'];
  for (const dir of sourceDirs) {
    args.push('--reload-dir', dir);
  }
  for (const pattern of excludeGlobs) {
    args.push('--reload-exclude', pattern);
  }
  return args;
};

const services = [
  {
    name: 'backend',
    command: nodeExec,
    args: ['server.cjs'],
    cwd: path.join(rootDir, 'backend', 'auth'),
    required: true,
  },
  {
    name: 'frontend',
    command: nodeExec,
    args: [
      path.join(rootDir, 'frontend', 'node_modules', 'vite', 'bin', 'vite.js'),
      '--port',
      '3000',
      '--host',
      '0.0.0.0',
    ],
    cwd: path.join(rootDir, 'frontend'),
    required: true,
  },
];

if (enableModule2) {
  const module2ReloadArgs = reloadEnabled('MODULE2_UVICORN_RELOAD', true)
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
  services.push({
    name: 'module2',
    command: module2PythonExec,
    args: ['-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000', ...module2ReloadArgs],
    cwd: module2Dir,
    required: true,
  });
}

if (enableModule4) {
  const module4ReloadArgs = reloadEnabled('MODULE4_UVICORN_RELOAD', true)
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
  services.push({
    name: 'module4',
    command: module4PythonExec,
    args: ['-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8100', ...module4ReloadArgs],
    cwd: module4Dir,
    required: true,
  });
}

const children = [];
let shuttingDown = false;

const stopAll = (exitCode = 0) => {
  if (shuttingDown) return;
  shuttingDown = true;

  for (const child of children) {
    if (!child.killed) {
      child.kill('SIGTERM');
    }
  }

  setTimeout(() => process.exit(exitCode), 300);
};

for (const service of services) {
  const child = spawn(service.command, service.args, {
    cwd: service.cwd,
    stdio: 'inherit',
    shell: false,
    env: process.env,
  });

  children.push(child);

  child.on('exit', (code, signal) => {
    if (shuttingDown) return;
    const exitInfo = typeof code === 'number' ? `code ${code}` : `signal ${signal}`;
    if (service.required === false) {
      console.warn(`[dev-all] optional service ${service.name} exited with ${exitInfo}`);
      return;
    }
    console.error(`[dev-all] ${service.name} exited with ${exitInfo}`);
    stopAll(typeof code === 'number' ? code : 1);
  });
}

process.on('SIGINT', () => stopAll(0));
process.on('SIGTERM', () => stopAll(0));
