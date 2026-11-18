import { Capacitor } from '@capacitor/core';

export const standaloneDisplay = '(display-mode: standalone)';

export function experience(): 'native' | 'standalone' | 'browser' {
  if (Capacitor.isNativePlatform()) return 'native';
  if (window.matchMedia(standaloneDisplay).matches ||
      (navigator as Navigator & { standalone?: boolean }).standalone === true) return 'standalone';
  return 'browser';
}
