import { createRoot } from 'react-dom/client';
import 'leaflet/dist/leaflet.css';
import '../styles.css';
import { CitizenApp } from '../CitizenApp';
import { InstallPanel } from '../components/InstallPanel';
import { registerScopedWorker } from '../service-worker';

void registerScopedWorker('/app/');
createRoot(document.getElementById('root')!).render(<CitizenApp installation={<InstallPanel />} />);
