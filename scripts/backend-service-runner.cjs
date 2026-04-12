const path = require('path');
const { spawn } = require('child_process');

const {
  buildManagedRuntimeEnv,
  buildNodeRuntimeEnv,
  nodeExec,
  reloadEnabled,
  rootDir,
} = require('./python-service-utils.cjs');

const envEnabled = reloadEnabled;

const buildBackendServices = ({
  label,
  scriptPrefix,
  defaultModule2Enabled = true,
  defaultModule4Enabled = true,
}) => {
  const enableModule2 = envEnabled('MODULE2_ENABLED', defaultModule2Enabled);
  const enableModule4 = envEnabled('MODULE4_ENABLED', defaultModule4Enabled);

  const services = [];
  const gatewayServiceEnv = {
    UNIFIED_GATEWAY_MODULE4_SIDECAR_MODE: process.env.UNIFIED_GATEWAY_MODULE4_SIDECAR_MODE || 'auto',
  };
  if (process.env.MODULE2_UPSTREAM_URL) {
    gatewayServiceEnv.MODULE2_UPSTREAM_URL = process.env.MODULE2_UPSTREAM_URL;
  }
  if (process.env.MODULE4_UPSTREAM_URL) {
    gatewayServiceEnv.MODULE4_UPSTREAM_URL = process.env.MODULE4_UPSTREAM_URL;
  }

  services.push({
    name: 'gateway-backend',
    command: nodeExec,
    args: [path.join(rootDir, 'scripts', `${scriptPrefix}-gateway.cjs`)],
    cwd: rootDir,
    env: gatewayServiceEnv,
    scopes: ['module2', 'backend'],
    required: true,
  });

  if (enableModule2) {
    services.push({
      name: 'module2-backend',
      command: nodeExec,
      args: [path.join(rootDir, 'scripts', `${scriptPrefix}-module2.cjs`)],
      cwd: rootDir,
      scopes: ['backend', 'module2'],
      required: true,
    });
  } else {
    console.log(
      `[${label}] standalone module2 disabled; unified FastAPI sidecar will attach or start module2 when required`,
    );
  }

  if (enableModule4) {
    services.push({
      name: 'module4-backend',
      command: nodeExec,
      args: [path.join(rootDir, 'scripts', `${scriptPrefix}-module4.cjs`)],
      cwd: rootDir,
      scopes: ['backend', 'module4'],
      required: true,
    });
  } else {
    console.log(
      `[${label}] standalone module4 disabled; unified FastAPI gateway will attach or start module4 when required`,
    );
  }

  return services;
};

const runManagedServices = ({
  label,
  services,
  watchParentPid = false,
}) => {
  const children = [];
  let shuttingDown = false;
  let parentWatchdog = null;

  const stopAll = (exitCode = 0) => {
    if (shuttingDown) return;
    shuttingDown = true;
    if (parentWatchdog) {
      clearInterval(parentWatchdog);
      parentWatchdog = null;
    }
    for (const child of children) {
      if (!child.killed) {
        child.kill('SIGTERM');
      }
    }
    setTimeout(() => process.exit(exitCode), 400);
  };

  if (watchParentPid) {
    const managedParentPid = Number(process.env.SMART_DOC_FLOW_PARENT_PID || 0);
    if (Number.isInteger(managedParentPid) && managedParentPid > 0 && managedParentPid !== process.pid) {
      parentWatchdog = setInterval(() => {
        try {
          process.kill(managedParentPid, 0);
        } catch (error) {
          const code = error && typeof error === 'object' ? error.code : '';
          if (code && code !== 'ESRCH') {
            return;
          }
          console.warn(`[${label}] parent process ${managedParentPid} is gone; stopping managed backend tree`);
          stopAll(0);
        }
      }, 3000);
      if (typeof parentWatchdog.unref === 'function') {
        parentWatchdog.unref();
      }
    }
  }

  for (const service of services) {
    const serviceEnv = buildManagedRuntimeEnv({
      baseEnv: { ...process.env, ...(service.env || {}) },
      scopes: service.scopes,
    });
    const child = spawn(service.command, service.args, {
      cwd: service.cwd,
      stdio: 'inherit',
      shell: false,
      env: buildNodeRuntimeEnv({ baseEnv: serviceEnv }),
    });

    children.push(child);

    child.on('exit', (code, signal) => {
      if (shuttingDown) return;
      const exitInfo = typeof code === 'number' ? `code ${code}` : `signal ${signal}`;
      if (service.required === false) {
        console.warn(`[${label}] optional service ${service.name} exited with ${exitInfo}`);
        return;
      }
      console.error(`[${label}] ${service.name} exited with ${exitInfo}`);
      stopAll(typeof code === 'number' ? code : 1);
    });
  }

  process.on('SIGINT', () => stopAll(0));
  process.on('SIGTERM', () => stopAll(0));
};

module.exports = {
  buildBackendServices,
  envEnabled,
  runManagedServices,
};
