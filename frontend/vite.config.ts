import path from 'path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

const normalizeModuleId = (id: string) => id.replace(/\\/g, '/');

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

const KNOWLEDGE_NEXUS_SCREEN_MODULE = '/frontend/components/knowledge-nexus/KnowledgeNexusNeo4j.tsx';

export default defineConfig(({ mode }) => {
  loadEnv(mode, '.', '');
  return {
    server: {
      port: 3000,
      strictPort: true,
      host: '0.0.0.0',
      proxy: {
        '/api': {
          target: 'http://localhost:3001',
          changeOrigin: true,
          secure: false,
          timeout: 180000,
          proxyTimeout: 180000,
        },
        '/extract': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          secure: false,
        },
        '/module4': {
          target: 'http://localhost:8100',
          changeOrigin: true,
          secure: false,
        },
      },
    },
    preview: {
      port: 3000,
      strictPort: true,
      host: '0.0.0.0',
    },
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    build: {
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
