const path = require('path');
const { spawn } = require('child_process');
const {
  buildManagedRuntimeEnv,
  buildNodeRuntimeEnv,
  nodeExec,
  rootDir,
} = require('./python-service-utils.cjs');

const frontendDir = path.join(rootDir, 'frontend');
const managedEnv = buildManagedRuntimeEnv({
  baseEnv: process.env,
  scopes: ['backend'],
});
const host = managedEnv.FRONTEND_HOST || process.env.FRONTEND_HOST || '0.0.0.0';
const port = managedEnv.FRONTEND_PORT || process.env.FRONTEND_PORT || '3000';

const args = [
  path.join(frontendDir, 'node_modules', 'vite', 'bin', 'vite.js'),
  '--host',
  String(host),
  '--port',
  String(port),
  '--strictPort',
  '--force',
];

const child = spawn(nodeExec, args, {
  cwd: frontendDir,
  stdio: 'inherit',
  shell: false,
  env: buildNodeRuntimeEnv({ baseEnv: managedEnv }),
});

let shuttingDown = false;

const stop = (exitCode = 0) => {
  if (shuttingDown) return;
  shuttingDown = true;
  if (!child.killed) child.kill('SIGTERM');
  setTimeout(() => process.exit(exitCode), 300);
};

child.on('exit', (code, signal) => {
  if (shuttingDown) return;
  const exitInfo = typeof code === 'number' ? `code ${code}` : `signal ${signal}`;
  console.error(`[dev:frontend] exited with ${exitInfo}`);
  stop(typeof code === 'number' ? code : 1);
});

process.on('SIGINT', () => stop(0));
process.on('SIGTERM', () => stop(0));

