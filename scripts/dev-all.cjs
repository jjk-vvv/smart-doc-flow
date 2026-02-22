const path = require('path');
const { spawn } = require('child_process');

const rootDir = path.resolve(__dirname, '..');
const nodeExec = process.execPath;

const services = [
  {
    name: 'backend',
    command: nodeExec,
    args: ['server.cjs'],
    cwd: path.join(rootDir, 'backend', 'auth'),
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
  });

  children.push(child);

  child.on('exit', (code, signal) => {
    if (shuttingDown) return;
    const exitInfo = typeof code === 'number' ? `code ${code}` : `signal ${signal}`;
    console.error(`[dev-all] ${service.name} exited with ${exitInfo}`);
    stopAll(typeof code === 'number' ? code : 1);
  });
}

process.on('SIGINT', () => stopAll(0));
process.on('SIGTERM', () => stopAll(0));
