import type { CapacitorConfig } from '@capacitor/cli';

const endpoint = new URL(process.env.VITE_API_BASE_URL || 'http://127.0.0.1:5173');
const config: CapacitorConfig = {
  appId: 'co.edu.ucc.civia',
  appName: 'CIVIA',
  webDir: 'dist-native',
  server: { androidScheme: endpoint.protocol === 'https:' ? 'https' : 'http' },
  android: { allowMixedContent: false, webContentsDebuggingEnabled: false, adjustMarginsForEdgeToEdge: 'auto' },
};
export default config;
