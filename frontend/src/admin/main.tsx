import { createRoot } from 'react-dom/client';
import 'leaflet/dist/leaflet.css';
import '../styles.css';
import { AdminApp } from './AdminApp';
import { retireLegacyWorker } from '../service-worker';

void retireLegacyWorker().then(async () => {
  if ('serviceWorker' in navigator) {
    try { await navigator.serviceWorker.register('/admin/sw.js', { scope: '/admin/' }); }
    catch { /* The portal also works without service workers. */ }
  }
});

createRoot(document.getElementById('root')!).render(<AdminApp />);
