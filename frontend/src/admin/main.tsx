import { createRoot } from 'react-dom/client';
import 'leaflet/dist/leaflet.css';
import '../styles.css';
import { AdminApp } from './AdminApp';
import { registerScopedWorker } from '../service-worker';

void registerScopedWorker('/admin/');

createRoot(document.getElementById('root')!).render(<AdminApp />);
