const path = require('path');
const { spawn } = require('child_process');

const {
  buildPythonRuntimeEnv,
  resolvePythonExec,
  rootDir,
} = require('./python-service-utils.cjs');

const pythonExec = resolvePythonExec({
  overrideExec: process.env.GATEWAY_PYTHON || process.env.PYTHON,
  preferredVenvDirs: [path.join(rootDir, '.venv')],
});

const args = [
  '-m',
  'ruff',
  'check',
  '--config',
  path.join(rootDir, 'config', 'quality', 'ruff.toml'),
  path.join(rootDir, 'backend', 'app'),
  path.join(rootDir, 'backend', 'tests'),
  path.join(rootDir, 'backend', 'run_service.py'),
];

const child = spawn(pythonExec, args, {
  cwd: rootDir,
  stdio: 'inherit',
  shell: false,
  env: buildPythonRuntimeEnv({ baseEnv: process.env, pythonExec }),
});

child.on('exit', (code, signal) => {
  if (code === 0) {
    process.exit(0);
  }
  console.error(`[lint:backend] ruff exited with ${signal ? `signal ${signal}` : `code ${code}`}`);
  process.exit(typeof code === 'number' ? code : 1);
});
