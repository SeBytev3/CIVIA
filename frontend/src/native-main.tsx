import { createRoot } from 'react-dom/client';
import 'leaflet/dist/leaflet.css';
import './styles.css';
import { CitizenApp } from './CitizenApp';
import { ConnectionGate } from './ConnectionGate';

createRoot(document.getElementById('root')!).render(<ConnectionGate><CitizenApp /></ConnectionGate>);
