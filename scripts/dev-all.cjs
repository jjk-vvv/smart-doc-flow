const path = require('path');
const { spawn } = require('child_process');
const { nodeExec, rootDir } = require('./python-service-utils.cjs');

const enableModule2 = process.env.MODULE2_ENABLED !== '0';
const enableModule4 = process.env.MODULE4_ENABLED !== '0';

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
  services.push({
    name: 'module2',
    command: nodeExec,
    args: [path.join(rootDir, 'scripts', 'dev-module2.cjs')],
    cwd: rootDir,
    required: true,
  });
}

if (enableModule4) {
  services.push({
    name: 'module4',
    command: nodeExec,
    args: [path.join(rootDir, 'scripts', 'dev-module4.cjs')],
    cwd: rootDir,
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
