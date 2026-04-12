const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn, spawnSync } = require('child_process');

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const outputDir = process.env.DESKTOP_SMOKE_OUTPUT_DIR || process.argv[2] || 'dist-electron';
const smokeMode = String(process.env.DESKTOP_SMOKE_MODE || process.argv[3] || 'backend').trim().toLowerCase();
const gatewayPort = String(process.env.DESKTOP_SMOKE_GATEWAY_PORT || '3001').trim() || '3001';
const gatewayBaseUrl = `http://127.0.0.1:${gatewayPort}`;
const requestTimeoutMs = Math.max(2_000, Number(process.env.DESKTOP_SMOKE_HTTP_TIMEOUT_MS || 10_000));
const readyTimeoutMs = Math.max(15_000, Number(process.env.DESKTOP_SMOKE_READY_TIMEOUT_MS || 180_000));
const module2WarmupTimeoutMs = Math.max(10_000, Number(process.env.DESKTOP_SMOKE_MODULE2_WARMUP_TIMEOUT_MS || 90_000));
const module4ProbeTimeoutMs = Math.max(10_000, Number(process.env.DESKTOP_SMOKE_MODULE4_PROBE_TIMEOUT_MS || 90_000));
const readyScope = String(
  process.env.DESKTOP_SMOKE_READY_SCOPE || (smokeMode === 'backend' ? 'backend' : 'all'),
).trim() || (smokeMode === 'backend' ? 'backend' : 'all');
const warmModule2Enabled = !['0', 'false', 'no', 'off'].includes(
  String(process.env.DESKTOP_SMOKE_WARM_MODULE2 || '1').trim().toLowerCase(),
);
const packagedDir = path.resolve(outputDir, 'win-unpacked');
const exePath = path.join(packagedDir, 'Smart Doc Flow.exe');
const backendScriptPath = path.join(packagedDir, 'resources', 'app-runtime', 'scripts', 'start-backend-fastapi.cjs');
const smokeDataRoot = path.join(
  os.tmpdir(),
  'smart-doc-flow-desktop-smoke',
  path.basename(outputDir),
  `${Date.now()}`,
);

if (!fs.existsSync(exePath)) {
  console.error(JSON.stringify({
    ok: false,
    error: `Desktop executable not found: ${exePath}`,
  }, null, 2));
  process.exit(1);
}

const terminateProcessTree = (pid) => {
  if (!pid || !Number.isInteger(pid)) {
    return;
  }
  if (process.platform === 'win32') {
    spawnSync('taskkill', ['/F', '/T', '/PID', String(pid)], {
      stdio: 'ignore',
      windowsHide: true,
      shell: false,
    });
    return;
  }
  try {
    process.kill(pid, 'SIGTERM');
  } catch {
    // Ignore missing process errors during cleanup.
  }
};

const fetchWithTimeout = async (url, options = {}) => {
  const signal = typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function'
    ? AbortSignal.timeout(requestTimeoutMs)
    : undefined;
  return fetch(url, { ...options, signal });
};

const fetchJsonWithTimeout = async (url, options = {}) => {
  const response = await fetchWithTimeout(url, options);
  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }
  return { response, payload, text };
};

const summarizePayload = (payload, text) => {
  if (payload && typeof payload === 'object') {
    const serialized = JSON.stringify(payload);
    return serialized.length > 800 ? `${serialized.slice(0, 800)}...` : serialized;
  }
  const normalizedText = String(text || '').trim();
  if (!normalizedText) {
    return '';
  }
  return normalizedText.length > 800 ? `${normalizedText.slice(0, 800)}...` : normalizedText;
};

const warmModule2Sidecar = async ({ ensureDesktopAlive = () => {} } = {}) => {
  if (!warmModule2Enabled) {
    return { skipped: true };
  }

  const warmupUrl = `${gatewayBaseUrl}/extract/jobs/status/desktop_smoke_probe`;
  const startedAt = Date.now();
  let lastError = '';
  let lastDetail = '';

  while ((Date.now() - startedAt) < module2WarmupTimeoutMs) {
    ensureDesktopAlive();
    try {
      const { response, payload, text } = await fetchJsonWithTimeout(warmupUrl, {
        method: 'GET',
        cache: 'no-store',
      });
      if (response.status === 404 || response.ok) {
        return {
          skipped: false,
          status: response.status,
          payload,
          detail: summarizePayload(payload, text),
        };
      }
      lastError = `HTTP ${response.status}`;
      lastDetail = summarizePayload(payload, text);
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
      lastDetail = '';
    }
    await sleep(1000);
  }

  throw new Error(
    `Module2 sidecar warmup did not complete via ${warmupUrl}: ${lastError}${lastDetail ? ` payload=${lastDetail}` : ''}`,
  );
};

const probeModule4Health = async ({ ensureDesktopAlive = () => {} } = {}) => {
  const healthUrl = `${gatewayBaseUrl}/module4/healthz`;
  const startedAt = Date.now();
  let lastError = '';
  let lastDetail = '';

  while ((Date.now() - startedAt) < module4ProbeTimeoutMs) {
    ensureDesktopAlive();
    try {
      const { response, payload, text } = await fetchJsonWithTimeout(healthUrl, {
        method: 'GET',
        cache: 'no-store',
      });
      if (response.ok) {
        return {
          status: response.status,
          payload,
          detail: summarizePayload(payload, text),
        };
      }
      lastError = `HTTP ${response.status}`;
      lastDetail = summarizePayload(payload, text);
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
      lastDetail = '';
    }
    await sleep(1000);
  }

  throw new Error(
    `Module4 health probe did not complete via ${healthUrl}: ${lastError}${lastDetail ? ` payload=${lastDetail}` : ''}`,
  );
};

const waitForReady = async ({ ensureDesktopAlive = () => {} } = {}) => {
  const readyUrl = `${gatewayBaseUrl}/gateway/ready?scope=${encodeURIComponent(readyScope)}`;
  const startedAt = Date.now();
  let lastError = '';
  let lastDetail = '';
  while ((Date.now() - startedAt) < readyTimeoutMs) {
    ensureDesktopAlive();
    try {
      const { response, payload, text } = await fetchJsonWithTimeout(readyUrl, {
        method: 'GET',
        cache: 'no-store',
      });
      if (response.ok) {
        if (payload && payload.ok) {
          return payload;
        }
        lastError = 'ready payload returned ok=false';
        lastDetail = summarizePayload(payload, text);
      } else {
        lastError = `HTTP ${response.status}`;
        lastDetail = summarizePayload(payload, text);
      }
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
      lastDetail = '';
    }
    await sleep(2000);
  }
  throw new Error(
    `Packaged gateway did not become ready at ${readyUrl}: ${lastError}${lastDetail ? ` payload=${lastDetail}` : ''}`,
  );
};

const main = async () => {
  const spawnArgs = smokeMode === 'backend' ? [backendScriptPath] : [];
  const child = spawn(exePath, spawnArgs, {
    cwd: packagedDir,
    detached: false,
    shell: false,
    stdio: 'ignore',
    windowsHide: false,
    env: {
      ...process.env,
      ELECTRON_RUN_AS_NODE: smokeMode === 'backend' ? '1' : process.env.ELECTRON_RUN_AS_NODE,
      ELECTRON_NO_ATTACH_CONSOLE: process.env.ELECTRON_NO_ATTACH_CONSOLE || '1',
      SMART_DOC_FLOW_ELECTRON_OPEN_DEVTOOLS: '0',
      SMART_DOC_FLOW_DATA_ROOT: process.env.SMART_DOC_FLOW_DATA_ROOT || smokeDataRoot,
    },
  });

  let settled = false;
  let earlyExitMessage = '';
  child.on('exit', (code, signal) => {
    if (!settled) {
      earlyExitMessage = `Desktop process exited before smoke test completed: code=${code} signal=${signal}`;
    }
  });

  const ensureDesktopAlive = () => {
    if (earlyExitMessage) {
      throw new Error(earlyExitMessage);
    }
  };

  try {
    const module2Warmup = await warmModule2Sidecar({ ensureDesktopAlive });
    const ready = await waitForReady({ ensureDesktopAlive });
    const module4Health = await probeModule4Health({ ensureDesktopAlive });
    const { response: infoResponse, payload: infoPayload, text: infoText } = await fetchJsonWithTimeout(`${gatewayBaseUrl}/gateway/info`, {
      method: 'GET',
      cache: 'no-store',
    });
    if (!infoResponse.ok) {
      throw new Error(
        `Packaged gateway info request failed: HTTP ${infoResponse.status}${infoText ? ` payload=${summarizePayload(infoPayload, infoText)}` : ''}`,
      );
    }
    settled = true;
    console.log(JSON.stringify({
      ok: true,
      output_dir: outputDir,
      smoke_mode: smokeMode,
      ready_scope: readyScope,
      exe_path: exePath,
      module2_warmup: module2Warmup,
      module4_health: module4Health,
      ready,
      info: infoPayload,
      desktop_pid: child.pid,
    }, null, 2));
  } finally {
    terminateProcessTree(child.pid);
    await sleep(3000);
    child.removeAllListeners();
    if (typeof child.unref === 'function') {
      child.unref();
    }
  }
};

main()
  .then(() => {
    process.exit(0);
  })
  .catch((error) => {
    console.error(JSON.stringify({
      ok: false,
      error: error instanceof Error ? (error.stack || error.message) : String(error),
    }, null, 2));
    process.exit(1);
  });
