const path = require('path');
const { spawn } = require('child_process');
const {
  buildManagedRuntimeEnv,
  buildNodeRuntimeEnv,
  buildPythonRuntimeEnv,
  nodeExec,
  resolvePythonExec,
  rootDir,
} = require('./python-service-utils.cjs');

const backendPythonExec = resolvePythonExec({
  overrideExec: process.env.GATEWAY_PYTHON || process.env.PYTHON,
  preferredVenvDirs: [
    path.join(rootDir, '.venv-module2-py311'),
    path.join(rootDir, '.venv'),
  ],
});

const services = [
  {
    name: 'backend',
    command: backendPythonExec,
    args: [path.join(rootDir, 'backend', 'run_service.py'), 'backend', '--reload'],
    cwd: rootDir,
    required: true,
    env: buildPythonRuntimeEnv({
      baseEnv: buildManagedRuntimeEnv({
        baseEnv: {
          ...process.env,
          UNIFIED_EXTRACT_MODULE2_SIDECAR_MODE:
            process.env.UNIFIED_EXTRACT_MODULE2_SIDECAR_MODE || 'auto',
          UNIFIED_GATEWAY_MODULE4_SIDECAR_MODE:
            process.env.UNIFIED_GATEWAY_MODULE4_SIDECAR_MODE || 'auto',
        },
        scopes: ['backend', 'module2'],
      }),
      pythonExec: backendPythonExec,
    }),
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
    env: service.env || buildNodeRuntimeEnv({ baseEnv: process.env }),
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
