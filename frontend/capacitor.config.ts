import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'co.edu.ucc.civia',
  appName: 'CIVIA',
  webDir: 'dist-native',
  loggingBehavior: 'none',
  // Capacitor intercepts this loopback-only asset origin without opening a cleartext socket.
  // Keeping the 1.1.0 origin allows explicit recovery of the legacy IndexedDB draft.
  server: { androidScheme: 'http' },
  android: { allowMixedContent: false, webContentsDebuggingEnabled: false, adjustMarginsForEdgeToEdge: 'auto' },
  plugins: { CapacitorHttp: { enabled: false }, CapacitorCookies: { enabled: false } },
};
export default config;
