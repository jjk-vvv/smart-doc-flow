const gatewayPort = process.env.GATEWAY_PORT || '3001';
const gatewayUrl = process.env.GATEWAY_URL || `http://127.0.0.1:${gatewayPort}`;
const readyScope = process.env.GATEWAY_READY_SCOPE || 'all';
const timeoutMs = Math.max(5_000, Number(process.env.GATEWAY_WAIT_TIMEOUT_MS || 120_000));
const pollIntervalMs = Math.max(250, Number(process.env.GATEWAY_WAIT_POLL_INTERVAL_MS || 1_000));

const targetUrl = `${gatewayUrl.replace(/\/+$/, '')}/gateway/ready?scope=${encodeURIComponent(readyScope)}`;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const run = async () => {
  const startedAt = Date.now();

  while ((Date.now() - startedAt) < timeoutMs) {
    try {
      const response = await fetch(targetUrl, { method: 'GET' });
      if (response.ok) {
        const payload = await response.json().catch(() => ({}));
        console.log(`[wait:gateway] ready at ${targetUrl}`);
        if (payload && typeof payload === 'object') {
          console.log(JSON.stringify(payload, null, 2));
        }
        process.exit(0);
      }
    } catch {
      // Retry until timeout.
    }
    await sleep(pollIntervalMs);
  }

  console.error(`[wait:gateway] timed out after ${timeoutMs}ms waiting for ${targetUrl}`);
  process.exit(1);
};

run().catch((error) => {
  console.error(`[wait:gateway] unexpected error: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});

