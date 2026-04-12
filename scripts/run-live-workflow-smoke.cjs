const path = require('path');
const { spawn } = require('child_process');

const rootDir = path.resolve(__dirname, '..');

const buildNpmSpawnSpec = (args) => {
  const normalizedArgs = Array.isArray(args) ? args.map((item) => String(item)) : [];
  if (process.platform === 'win32') {
    return {
      command: process.env.ComSpec || 'cmd.exe',
      args: ['/d', '/s', '/c', 'npm.cmd', ...normalizedArgs],
    };
  }
  return {
    command: 'npm',
    args: normalizedArgs,
  };
};

const runStep = (label, args, extraEnv = {}) =>
  new Promise((resolve, reject) => {
    console.log(`[live-workflow-smoke] start: ${label}`);
    const spawnSpec = buildNpmSpawnSpec(args);
    const child = spawn(spawnSpec.command, spawnSpec.args, {
      cwd: rootDir,
      stdio: 'inherit',
      shell: false,
      env: {
        ...process.env,
        ...extraEnv,
      },
    });

    child.on('error', reject);
    child.on('exit', (code, signal) => {
      if (code === 0) {
        console.log(`[live-workflow-smoke] done: ${label}`);
        resolve();
        return;
      }
      reject(new Error(`${label} failed: code=${code} signal=${signal}`));
    });
  });

const main = async () => {
  const module2FrontendRounds = String(process.env.MODULE2_FRONTEND_ROUNDS || '1').trim() || '1';

  await runStep('wait gateway', ['run', 'wait:gateway']);
  await runStep('module2 frontend', ['run', 'qa:module2:frontend'], {
    MODULE2_FRONTEND_ROUNDS: module2FrontendRounds,
  });
  await runStep('module2 trace', ['run', 'qa:module2:trace']);
  await runStep('module2 assistant', ['run', 'qa:module2:assistant']);
  await runStep('module4 live', ['run', 'qa:module4:live']);
};

main().catch((error) => {
  const message = error instanceof Error ? error.stack || error.message : String(error);
  console.error(`[live-workflow-smoke] failed: ${message}`);
  process.exit(1);
});
