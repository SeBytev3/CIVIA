import { createRoot } from 'react-dom/client';
import 'leaflet/dist/leaflet.css';
import './styles.css';
import { CitizenApp } from './CitizenApp';
import { retireLegacyWorker } from './service-worker';
import { isNative } from './device';

if (!isNative) void retireLegacyWorker();

createRoot(document.getElementById('root')!).render(<CitizenApp />);
