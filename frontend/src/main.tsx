import { createRoot } from 'react-dom/client';
import 'leaflet/dist/leaflet.css';
import './styles.css';
import { PublicReport } from './PublicReport';
import { retireLegacyWorker } from './service-worker';

void retireLegacyWorker();
createRoot(document.getElementById('root')!).render(<PublicReport />);
