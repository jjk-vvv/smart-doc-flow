import path from 'path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

const normalizeModuleId = (id: string) => id.replace(/\\/g, '/');
const parsePort = (value: string | undefined, fallback: number): number => {
  const parsed = Number.parseInt(String(value || '').trim(), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
};

const normalizeBasePath = (value: string | undefined, fallback: string): string => {
  const normalized = String(value || fallback).trim() || fallback;
  const withLeadingSlash = normalized.startsWith('/') ? normalized : `/${normalized}`;
  return withLeadingSlash.endsWith('/') ? withLeadingSlash : `${withLeadingSlash}/`;
};

const GRAPH_RUNTIME_PACKAGES = [
  '/node_modules/@neo4j-nvl/',
  '/node_modules/d3-force/',
  '/node_modules/d3-dispatch/',
  '/node_modules/d3-quadtree/',
  '/node_modules/d3-timer/',
];

const MOTION_RUNTIME_PACKAGES = [
  '/node_modules/framer-motion/',
  '/node_modules/motion-dom/',
  '/node_modules/motion-utils/',
];

const KNOWLEDGE_NEXUS_SCREEN_MODULE = '/frontend-app/pages/knowledge-nexus/KnowledgeNexusGraphRAGG6.tsx';
const PREBUNDLED_DYNAMIC_PREVIEW_DEPS = [
  'pdfjs-dist',
  'xlsx',
  'jquery',
  'luckyexcel',
  'luckysheet/dist/plugins/js/plugin.js',
  'luckysheet/dist/luckysheet.umd.js',
];

export default defineConfig(({ mode }) => {
  loadEnv(mode, '.', '');
  const gatewayPort = parsePort(process.env.GATEWAY_PORT, 3001);
  const frontendAppPort = parsePort(process.env.FRONTEND_APP_PORT, 3002);
  const backendEntryUrl = process.env.VITE_BACKEND_ENTRY_URL || `http://localhost:${gatewayPort}`;
  const frontendAppPublicBase = normalizeBasePath(
    process.env.FRONTEND_APP_PUBLIC_BASE,
    mode === 'native' ? '/' : '/m/',
  );
  const frontendAppBuildOutDir = String(
    process.env.VITE_BUILD_OUT_DIR || (mode === 'native' ? 'dist-native' : 'dist'),
  ).trim() || (mode === 'native' ? 'dist-native' : 'dist');
  const devProxyTimeoutMs = Math.max(
    180_000,
    Number.parseInt(process.env.VITE_DEV_PROXY_TIMEOUT_MS || '600000', 10) || 600_000,
  );
  return {
    base: mode === 'production' ? frontendAppPublicBase : '/',
    server: {
      port: frontendAppPort,
      strictPort: true,
      host: '0.0.0.0',
      proxy: {
        '/api': {
          target: backendEntryUrl,
          changeOrigin: true,
          secure: false,
          timeout: devProxyTimeoutMs,
          proxyTimeout: devProxyTimeoutMs,
        },
        '/extract': {
          target: backendEntryUrl,
          changeOrigin: true,
          secure: false,
          timeout: devProxyTimeoutMs,
          proxyTimeout: devProxyTimeoutMs,
        },
        '/module4': {
          target: backendEntryUrl,
          changeOrigin: true,
          secure: false,
          timeout: devProxyTimeoutMs,
          proxyTimeout: devProxyTimeoutMs,
        },
        '/gateway': {
          target: backendEntryUrl,
          changeOrigin: true,
          secure: false,
          timeout: devProxyTimeoutMs,
          proxyTimeout: devProxyTimeoutMs,
        },
        '/module3': {
          target: backendEntryUrl,
          changeOrigin: true,
          secure: false,
          timeout: devProxyTimeoutMs,
          proxyTimeout: devProxyTimeoutMs,
        },
        '/module1': {
          target: backendEntryUrl,
          changeOrigin: true,
          secure: false,
          timeout: devProxyTimeoutMs,
          proxyTimeout: devProxyTimeoutMs,
        },
      },
    },
    preview: {
      port: frontendAppPort,
      strictPort: true,
      host: '0.0.0.0',
    },
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    optimizeDeps: {
      include: PREBUNDLED_DYNAMIC_PREVIEW_DEPS,
    },
    build: {
      outDir: frontendAppBuildOutDir,
      rollupOptions: {
        output: {
          manualChunks(id) {
            const moduleId = normalizeModuleId(id);

            if (moduleId.endsWith(KNOWLEDGE_NEXUS_SCREEN_MODULE)) {
              return 'knowledge-nexus-screen';
            }

            if (GRAPH_RUNTIME_PACKAGES.some((fragment) => moduleId.includes(fragment))) {
              return 'graph-runtime';
            }

            if (MOTION_RUNTIME_PACKAGES.some((fragment) => moduleId.includes(fragment))) {
              return 'motion-runtime';
            }

            return undefined;
          },
        },
      },
    },
  };
});
