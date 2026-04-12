const path = require('path');
const { Readable } = require('stream');

const cors = require('cors');
const express = require('express');
require('dotenv').config({ path: path.join(__dirname, '.env') });

const app = express();

const PORT = Number(process.env.AUTH_PORT || process.env.PORT || 3003);
const COMPAT_PROXY_TIMEOUT_MS = Math.max(5000, Number(process.env.AUTH_COMPAT_PROXY_TIMEOUT_MS || 180000));
const CORS_ORIGINS = (process.env.AUTH_CORS_ORIGINS || 'http://localhost:3000,http://localhost:3002,http://localhost:5173')
  .split(',')
  .map((item) => String(item || '').trim())
  .filter(Boolean);
const ALLOW_ALL_CORS = CORS_ORIGINS.includes('*');

const PROXY_HOP_BY_HOP_HEADERS = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  // Undici rejects forwarding the Expect header, so compat POST requests
  // must strip it before proxying to the unified backend.
  'expect',
  'te',
  'trailers',
  'transfer-encoding',
  'upgrade',
  'host',
  'content-length',
]);

const normalizeStr = (value) => String(value || '').trim();

const sanitizeAssistantChunk = (text) => (
  String(text || '')
    .replace(/\r/g, '')
    .replace(/\u0000/g, '')
    .replace(/\u200b/g, '')
    .replace(/\uFFFD/g, '')
    .replace(/[*`#>]/g, '')
);

const CHAT_FALLBACK_TEXT =
  '统一助手服务当前不可用，请改用统一网关或稍后重试。';

const resolveCompatTargetBaseUrl = () => {
  const explicit = normalizeStr(
    process.env.AUTH_COMPAT_TARGET_URL
      || process.env.GATEWAY_UPSTREAM_URL
      || process.env.GATEWAY_ASSISTANT_UPSTREAM_URL
  );
  if (explicit) {
    return explicit.replace(/\/+$/, '');
  }
  const gatewayPort = normalizeStr(process.env.GATEWAY_PORT || '3001') || '3001';
  return `http://127.0.0.1:${gatewayPort}`;
};

const buildTargetUrl = (req, targetPath = '') => {
  const baseUrl = resolveCompatTargetBaseUrl();
  const requestPath = normalizeStr(targetPath || req.path) || '/';
  const normalizedPath = requestPath.startsWith('/') ? requestPath : `/${requestPath}`;
  const queryIndex = String(req.originalUrl || '').indexOf('?');
  const queryString = queryIndex >= 0 ? String(req.originalUrl).slice(queryIndex) : '';
  return `${baseUrl}${normalizedPath}${queryString}`;
};

const buildProxyHeaders = (req, { jsonBody = false } = {}) => {
  const headers = {};
  for (const [key, rawValue] of Object.entries(req.headers || {})) {
    const normalizedKey = normalizeStr(key).toLowerCase();
    if (!normalizedKey || PROXY_HOP_BY_HOP_HEADERS.has(normalizedKey) || normalizedKey === 'content-type') {
      continue;
    }
    if (Array.isArray(rawValue)) {
      headers[key] = rawValue.join(', ');
      continue;
    }
    if (rawValue !== undefined) {
      headers[key] = String(rawValue);
    }
  }
  if (jsonBody) {
    headers['Content-Type'] = 'application/json';
  }
  headers['X-Smart-Doc-Flow-Compat'] = 'auth-service-proxy';
  return headers;
};

const applyProxyResponseHeaders = (response, res) => {
  response.headers.forEach((value, key) => {
    const normalizedKey = normalizeStr(key).toLowerCase();
    if (!normalizedKey || PROXY_HOP_BY_HOP_HEADERS.has(normalizedKey) || normalizedKey === 'set-cookie') {
      return;
    }
    res.setHeader(key, value);
  });

  if (typeof response.headers.getSetCookie === 'function') {
    const cookies = response.headers.getSetCookie();
    if (Array.isArray(cookies) && cookies.length > 0) {
      res.setHeader('set-cookie', cookies);
    }
  } else {
    const cookieValue = response.headers.get('set-cookie');
    if (cookieValue) {
      res.setHeader('set-cookie', cookieValue);
    }
  }

  res.setHeader('X-Smart-Doc-Flow-Compat', 'auth-service-proxy');
};

const createAbortController = () => {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), COMPAT_PROXY_TIMEOUT_MS);
  return {
    controller,
    cleanup: () => clearTimeout(timeout),
  };
};

const proxyJsonRequest = async (req, res, { targetPath = '' } = {}) => {
  const { controller, cleanup } = createAbortController();
  try {
    const hasBody = !['GET', 'HEAD'].includes(String(req.method || 'GET').toUpperCase());
    const response = await fetch(buildTargetUrl(req, targetPath), {
      method: req.method,
      headers: buildProxyHeaders(req, { jsonBody: hasBody }),
      body: hasBody ? JSON.stringify(req.body || {}) : undefined,
      signal: controller.signal,
    });
    const text = await response.text();
    res.status(response.status);
    applyProxyResponseHeaders(response, res);
    res.send(text);
  } catch (error) {
    console.error('Auth compat JSON proxy error:', error);
    res.status(502).json({
      error: 'Unified auth gateway unavailable',
      detail: String(error && error.message ? error.message : error || '').trim() || 'auth_compat_proxy_error',
    });
  } finally {
    cleanup();
  }
};

const initDataStreamResponse = (res, source = 'compat_proxy_error') => {
  if (res.headersSent) return;
  res.status(200);
  res.setHeader('Content-Type', 'text/event-stream; charset=utf-8');
  res.setHeader('Cache-Control', 'no-cache, no-transform');
  res.setHeader('Connection', 'keep-alive');
  res.setHeader('X-Accel-Buffering', 'no');
  res.setHeader('X-Vercel-AI-Data-Stream', 'v1');
  res.setHeader('X-AI-Reply-Source', source);
  res.setHeader('X-Smart-Doc-Flow-Compat', 'auth-service-proxy');
  res.flushHeaders();
};

const writeDataStreamChunk = (res, text) => {
  if (res.writableEnded) return;
  const safeText = sanitizeAssistantChunk(text);
  if (!safeText) return;
  res.write(`0:${JSON.stringify(safeText)}\n`);
};

const endDataStream = (res) => {
  if (res.writableEnded) return;
  res.write('0:"[DONE]"\n');
  res.end();
};

const streamFallbackData = (res, text = CHAT_FALLBACK_TEXT, source = 'compat_proxy_error') => {
  initDataStreamResponse(res, source);
  res.write(':ka\n\n');
  for (const ch of Array.from(String(text || ''))) {
    writeDataStreamChunk(res, ch);
  }
  endDataStream(res);
};

const proxyChatStream = async (req, res) => {
  const { controller, cleanup } = createAbortController();
  const abortUpstream = () => controller.abort();
  req.on('aborted', abortUpstream);
  res.on('close', abortUpstream);

  try {
    const response = await fetch(buildTargetUrl(req, '/api/chat'), {
      method: 'POST',
      headers: buildProxyHeaders(req, { jsonBody: true }),
      body: JSON.stringify(req.body || {}),
      signal: controller.signal,
    });

    const contentType = String(response.headers.get('content-type') || '').toLowerCase();
    res.status(response.status);
    applyProxyResponseHeaders(response, res);

    if (!response.body || !contentType.includes('text/event-stream')) {
      const text = await response.text();
      res.send(text);
      return;
    }

    const stream = Readable.fromWeb(response.body);
    stream.on('error', (error) => {
      console.error('Auth compat chat stream error:', error);
      if (!res.writableEnded) {
        res.end();
      }
    });
    stream.pipe(res);
  } catch (error) {
    console.error('Auth compat chat proxy error:', error);
    streamFallbackData(res);
  } finally {
    cleanup();
    req.removeListener('aborted', abortUpstream);
    res.removeListener('close', abortUpstream);
  }
};

app.use(
  cors({
    origin: (origin, callback) => {
      if (ALLOW_ALL_CORS || !origin || CORS_ORIGINS.includes(origin)) {
        callback(null, true);
        return;
      }
      callback(new Error(`Origin not allowed by CORS: ${origin}`));
    },
    credentials: true,
  }),
);
app.use(express.json({ limit: '2mb' }));

app.get('/health', (req, res) => {
  res.json({
    ok: true,
    service: 'auth-compat-proxy',
    port: PORT,
    targetBaseUrl: resolveCompatTargetBaseUrl(),
  });
});

app.get('/api/auth/health', async (req, res) => {
  await proxyJsonRequest(req, res, { targetPath: '/api/auth/health' });
});

app.post('/api/register', async (req, res) => {
  await proxyJsonRequest(req, res);
});

app.post('/api/login', async (req, res) => {
  await proxyJsonRequest(req, res);
});

app.post('/api/logout', async (req, res) => {
  await proxyJsonRequest(req, res);
});

app.get('/api/me', async (req, res) => {
  await proxyJsonRequest(req, res);
});

app.post('/api/forgot/send-code', async (req, res) => {
  await proxyJsonRequest(req, res);
});

app.post('/api/forgot/reset', async (req, res) => {
  await proxyJsonRequest(req, res);
});

app.post('/api/register/send-code', async (req, res) => {
  await proxyJsonRequest(req, res);
});

app.get('/api/chat/health', async (req, res) => {
  await proxyJsonRequest(req, res);
});

app.post('/api/chat', async (req, res) => {
  await proxyChatStream(req, res);
});

app.use((req, res) => {
  res.status(404).json({
    error: 'Not found',
    detail: `No compat route for ${req.method} ${req.originalUrl}`,
  });
});

app.listen(PORT, () => {
  console.log(`Auth compatibility server running on http://localhost:${PORT}`);
});
