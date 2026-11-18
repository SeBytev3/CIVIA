import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const native = mode === 'android';
  const env = loadEnv(mode, process.cwd());
  const endpoint = new URL(env.VITE_API_BASE_URL || 'http://127.0.0.1:5173');
  if (native) {
    if (!['http:', 'https:'].includes(endpoint.protocol) || endpoint.username || endpoint.password ||
        endpoint.pathname !== '/' || endpoint.search || endpoint.hash) {
      throw new Error('VITE_API_BASE_URL debe ser un origen HTTP(S) sin credenciales, ruta ni parámetros.');
    }
  }
  const options = { target: process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000', changeOrigin: false };
  const proxy = { '/api': options, '/health': options };

  return {
    plugins: [react(), native && {
      name: 'civia-android-csp',
      transformIndexHtml: () => [{
        tag: 'meta',
        attrs: {
          'http-equiv': 'Content-Security-Policy',
          content: `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://*.tile.openstreetmap.org; media-src 'self' blob:; connect-src 'self' ${endpoint.origin}; object-src 'none'; base-uri 'none'; form-action 'self'`,
        },
        injectTo: 'head-prepend',
      }],
    }],
    publicDir: native ? false : undefined,
    build: {
      outDir: native ? 'dist-native' : 'dist',
      rollupOptions: {
        input: native ? 'index.html' : { citizen: 'index.html', admin: 'admin/index.html' },
        output: { manualChunks: { map: ['leaflet'] } },
      },
    },
    server: { host: '127.0.0.1', port: 5173, proxy },
    preview: { host: '127.0.0.1', port: 4173, proxy },
  };
});
