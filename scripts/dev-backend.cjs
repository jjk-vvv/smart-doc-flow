const path = require('path');
const { spawn } = require('child_process');

const rootDir = path.resolve(__dirname, '..');
const nodeExec = process.execPath;
const pythonExec = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const enableModule2 = process.env.MODULE2_ENABLED !== '0';
const enableModule4 = process.env.MODULE4_ENABLED !== '0';

const services = [
  {
    name: 'auth-backend',
    command: nodeExec,
    args: ['server.cjs'],
    cwd: path.join(rootDir, 'backend', 'auth'),
    required: true,
  },
];

if (enableModule2) {
  services.push({
    name: 'module2-backend',
    command: pythonExec,
    args: ['-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000', '--reload'],
    cwd: path.join(rootDir, 'backend', 'module2'),
    required: true,
  });
}

if (enableModule4) {
  services.push({
    name: 'module4-backend',
    command: pythonExec,
    args: ['-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8100', '--reload'],
    cwd: path.join(rootDir, 'backend', 'module4'),
    required: true,
  });
}

const children = [];
let shuttingDown = false;

const stopAll = (exitCode = 0) => {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const child of children) {
    if (!child.killed) child.kill('SIGTERM');
  }
  setTimeout(() => process.exit(exitCode), 400);
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
    console.error(`[dev-backend] ${service.name} exited with ${exitInfo}`);
    stopAll(typeof code === 'number' ? code : 1);
  });
}

process.on('SIGINT', () => stopAll(0));
process.on('SIGTERM', () => stopAll(0));
