#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

const DEFAULT_URLS = [
  'http://127.0.0.1:3000/',
  'http://127.0.0.1:3002/',
];

const urls = String(process.env.MONITOR_URLS || '')
  .split(',')
  .map((item) => item.trim())
  .filter(Boolean);
const monitorUrls = urls.length > 0 ? urls : DEFAULT_URLS;

const intervalMs = Math.max(1000, Number(process.env.MONITOR_INTERVAL_MS || 5000));
const requestTimeoutMs = Math.max(800, Number(process.env.MONITOR_TIMEOUT_MS || 3500));
const outPath = path.resolve(
  process.cwd(),
  process.env.FRONTEND_MONITOR_LOG || 'runtime-logs/frontend-monitor.log',
);

fs.mkdirSync(path.dirname(outPath), { recursive: true });

const nowIso = () => new Date().toISOString();

function writeLine(line) {
  fs.appendFileSync(outPath, `${line}\n`, 'utf8');
  process.stdout.write(`${line}\n`);
}

async function probeUrl(url) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), requestTimeoutMs);
  const started = Date.now();
  try {
    const response = await fetch(url, {
      method: 'GET',
      redirect: 'follow',
      signal: controller.signal,
      headers: { Accept: 'text/html,*/*;q=0.8' },
    });
    clearTimeout(timeout);
    return {
      ok: response.ok,
      status: Number(response.status || 0),
      latency_ms: Date.now() - started,
      error: '',
    };
  } catch (error) {
    clearTimeout(timeout);
    const message = error && error.name === 'AbortError'
      ? `timeout>${requestTimeoutMs}ms`
      : String((error && error.message) || error || 'unknown_error');
    return {
      ok: false,
      status: 0,
      latency_ms: Date.now() - started,
      error: message,
    };
  }
}

async function runRound() {
  const stamp = nowIso();
  for (const url of monitorUrls) {
    const result = await probeUrl(url);
    const record = {
      ts: stamp,
      url,
      ok: result.ok,
      status: result.status,
      latency_ms: result.latency_ms,
      error: result.error,
    };
    writeLine(JSON.stringify(record));
  }
}

writeLine(
  JSON.stringify({
    ts: nowIso(),
    type: 'monitor.start',
    pid: process.pid,
    interval_ms: intervalMs,
    timeout_ms: requestTimeoutMs,
    urls: monitorUrls,
    log_path: outPath,
  }),
);

let timer = null;

const scheduleNext = () => {
  timer = setTimeout(async () => {
    await runRound();
    scheduleNext();
  }, intervalMs);
};

runRound().then(scheduleNext);

const shutdown = (signalName) => {
  if (timer) {
    clearTimeout(timer);
    timer = null;
  }
  writeLine(JSON.stringify({ ts: nowIso(), type: 'monitor.stop', signal: signalName }));
  process.exit(0);
};

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
