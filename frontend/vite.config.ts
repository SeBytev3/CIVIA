import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import metadata from './package.json';

function buildMetadata(buildSha: string | undefined): Plugin {
  const commit = buildSha && /^[0-9a-f]{7,64}(?:-dirty)?$/i.test(buildSha) ? buildSha : 'unknown';
  const source = JSON.stringify({ version: metadata.version, commit });
  return {
    name: 'civia-build-metadata',
    generateBundle() {
      this.emitFile({ type: 'asset', fileName: 'build.json', source });
    },
    configureServer(server) {
      server.middlewares.use('/build.json', (_request, response) => {
        response.setHeader('Content-Type', 'application/json');
        response.setHeader('Cache-Control', 'no-store');
        response.end(source);
      });
    },
  };
}

export default defineConfig(({ mode }) => {
  const native = mode === 'android';
  const options = { target: process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000', changeOrigin: false };
  const proxy = { '/api': options, '/health': options };

  return {
    plugins: [react(), buildMetadata(process.env.CIVIA_BUILD_SHA), native && {
      name: 'civia-android-csp',
      transformIndexHtml: {
        order: 'pre',
        handler(html) {
          return {
            html: html.replace('/src/main.tsx', '/src/native-main.tsx'),
            tags: [{
              tag: 'meta',
              attrs: {
                'http-equiv': 'Content-Security-Policy',
                content: "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://tile.openstreetmap.org; media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'",
              },
              injectTo: 'head-prepend',
            }],
          };
        },
      },
    }],
    publicDir: native ? false : undefined,
    build: {
      outDir: native ? 'dist-native' : 'dist',
      rollupOptions: {
        input: native ? 'index.html' : { report: 'index.html', app: 'app/index.html', admin: 'admin/index.html' },
        output: { manualChunks: { map: ['leaflet'] } },
      },
    },
    server: { host: '127.0.0.1', port: 5173, proxy },
    preview: { host: '127.0.0.1', port: 4173, proxy },
  };
});
