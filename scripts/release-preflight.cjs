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
    const startedAt = Date.now();
    console.log(`[release-preflight] start: ${label}`);
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
        const elapsedMs = Date.now() - startedAt;
        console.log(`[release-preflight] done: ${label} (${elapsedMs}ms)`);
        resolve();
        return;
      }
      reject(new Error(`${label} failed: code=${code} signal=${signal}`));
    });
  });

const parseArgSet = () => new Set(process.argv.slice(2).map((item) => String(item || '').trim()).filter(Boolean));

const main = async () => {
  const argSet = parseArgSet();
  const skipMobileSync = argSet.has('--skip-mobile-sync');
  const skipDesktopBuild = argSet.has('--skip-desktop-build');

  await runStep('desktop doctor', ['run', 'desktop:doctor']);
  await runStep('frontend typecheck', ['run', 'typecheck']);

  if (!skipDesktopBuild) {
    await runStep('desktop frontend build', ['run', 'build:frontend']);
  } else {
    console.log('[release-preflight] skip: desktop frontend build');
  }

  await runStep('mobile web build', ['run', 'build:frontend:app:web']);
  await runStep('mobile native build', ['run', 'build:frontend:app:native']);
  await runStep('capacitor doctor', ['run', 'mobile:cap:doctor']);

  if (!skipMobileSync) {
    await runStep('capacitor sync', ['run', 'mobile:cap:sync']);
  } else {
    console.log('[release-preflight] skip: capacitor sync');
  }

  console.log('[release-preflight] all checks passed');
};

main().catch((error) => {
  const message = error instanceof Error ? error.stack || error.message : String(error);
  console.error(`[release-preflight] failed: ${message}`);
  process.exit(1);
});
