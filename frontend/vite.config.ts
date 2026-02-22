import path from 'path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

const CHAT_PROXY_FALLBACK_TEXT =
  '聊天后端服务暂未启动，我已切换到本地兜底模式。请保持前端端口为3000，并启动 backend/auth/server.cjs 以使用完整模型能力。';

export default defineConfig(({ mode }) => {
  loadEnv(mode, '.', '');
  return {
    server: {
      port: 3000,
      host: '0.0.0.0',
      proxy: {
        '/api/chat': {
          target: 'http://localhost:3001',
          changeOrigin: true,
          secure: false,
          configure: (proxy) => {
            proxy.on('error', (_err, _req, res) => {
              if (!res || typeof (res as { end?: unknown }).end !== 'function') {
                return;
              }
              const streamRes = res as {
                writableEnded?: boolean;
                statusCode: number;
                setHeader: (name: string, value: string) => void;
                write: (chunk: string) => void;
                end: () => void;
              };
              if (streamRes.writableEnded) return;
              streamRes.statusCode = 200;
              streamRes.setHeader('Content-Type', 'text/event-stream; charset=utf-8');
              streamRes.setHeader('Cache-Control', 'no-cache, no-transform');
              streamRes.setHeader('Connection', 'keep-alive');
              streamRes.setHeader('X-Vercel-AI-Data-Stream', 'v1');
              for (const ch of Array.from(CHAT_PROXY_FALLBACK_TEXT)) {
                streamRes.write(`0:${JSON.stringify(ch)}\n`);
              }
              streamRes.write('0:"[DONE]"\n');
              streamRes.end();
            });
          },
        },
        '/api': {
          target: 'http://localhost:3001',
          changeOrigin: true,
          secure: false,
        },
        '/extract': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          secure: false,
        },
      },
    },
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
  };
});
