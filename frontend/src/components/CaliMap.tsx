import { useEffect, useRef } from 'react';
import L from 'leaflet';
import type { ReportCategory, ReportItem } from '../types';

interface CaliMapProps {
  reports: ReportItem[];
  onSelectReport?: (report: ReportItem) => void;
  selectable?: boolean;
  selectedLat?: number;
  selectedLon?: number;
  onPickCoords?: (lat: number, lon: number) => void;
  height?: string;
}

const CATEGORY_COLORS: Record<ReportCategory | 'PENDIENTE', string> = {
  HUECO: '#e36414',
  BASURAS: '#7b2cbf',
  TALA: '#2d6a4f',
  QUEMA: '#d90429',
  OTRO: '#3a86ff',
  PENDIENTE: '#6c757d',
};

function createPinIcon(color: string, isSynthetic: boolean): L.DivIcon {
  const ring = isSynthetic ? '#ffffff' : '#ffe66d';
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="32" height="40" viewBox="0 0 32 40">
      <path d="M16 2C8.8 2 3 7.8 3 15c0 9.6 13 23 13 23s13-13.4 13-23C29 7.8 23.2 2 16 2z"
            fill="${color}" stroke="#12263a" stroke-width="2"/>
      <circle cx="16" cy="15" r="5.5" fill="${ring}"/>
    </svg>
  `;
  return L.divIcon({
    html: svg,
    className: 'civia-map-pin',
    iconSize: [32, 40],
    iconAnchor: [16, 38],
    popupAnchor: [0, -34],
  });
}

const PICKER_ICON = L.divIcon({
  html: `
    <svg xmlns="http://www.w3.org/2000/svg" width="36" height="44" viewBox="0 0 36 44">
      <path d="M18 2C9.7 2 3 8.7 3 17c0 11 15 25 15 25s15-14 15-25C33 8.7 26.3 2 18 2z"
            fill="#0f4c5c" stroke="#ffffff" stroke-width="2.5"/>
      <circle cx="18" cy="17" r="6" fill="#2ec4b6"/>
    </svg>
  `,
  className: 'civia-map-picker-pin',
  iconSize: [36, 44],
  iconAnchor: [18, 42],
});

export function CaliMap({
  reports,
  onSelectReport,
  selectable = false,
  selectedLat,
  selectedLon,
  onPickCoords,
  height = '420px',
}: CaliMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markersLayerRef = useRef<L.LayerGroup | null>(null);
  const pickerMarkerRef = useRef<L.Marker | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = L.map(containerRef.current, {
      center: [3.4372, -76.5225],
      zoom: 12,
      scrollWheelZoom: true,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors · CIVIA Cali',
      maxZoom: 19,
    }).addTo(map);

    const layerGroup = L.layerGroup().addTo(map);
    mapRef.current = map;
    markersLayerRef.current = layerGroup;

    return () => {
      map.remove();
      mapRef.current = null;
      markersLayerRef.current = null;
      pickerMarkerRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const handleClick = (e: L.LeafletMouseEvent) => {
      if (selectable && onPickCoords) {
        const lat = Number(e.latlng.lat.toFixed(6));
        const lon = Number(e.latlng.lng.toFixed(6));
        onPickCoords(lat, lon);
      }
    };

    map.on('click', handleClick);
    return () => {
      map.off('click', handleClick);
    };
  }, [selectable, onPickCoords]);

  useEffect(() => {
    const layer = markersLayerRef.current;
    if (!layer) return;
    layer.clearLayers();

    reports.forEach((rep) => {
      const cat = rep.effective_category || 'PENDIENTE';
      const color = CATEGORY_COLORS[cat] || CATEGORY_COLORS.PENDIENTE;
      const marker = L.marker([rep.latitude, rep.longitude], {
        icon: createPinIcon(color, rep.is_synthetic),
      });

      const wrapper = document.createElement('div');
      wrapper.className = 'civia-popup-card';

      const codeEl = document.createElement('div');
      codeEl.className = 'civia-popup-code';
      codeEl.textContent = `${rep.tracking_code}${rep.is_synthetic ? ' · DEMO SINTÉTICO' : ''}`;
      wrapper.appendChild(codeEl);

      const titleEl = document.createElement('strong');
      titleEl.className = 'civia-popup-title';
      titleEl.textContent = rep.title;
      wrapper.appendChild(titleEl);

      const metaEl = document.createElement('div');
      metaEl.className = 'civia-popup-meta';
      metaEl.textContent = `Categoría: ${cat} · Severidad: ${rep.effective_severity || 'N/A'} · ${rep.comuna || 'Cali'}`;
      wrapper.appendChild(metaEl);

      if (onSelectReport) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'civia-popup-btn';
        btn.textContent = 'Ver evidencia y estado';
        btn.addEventListener('click', () => onSelectReport(rep));
        wrapper.appendChild(btn);
      }

      marker.bindPopup(wrapper);
      marker.addTo(layer);
    });
  }, [reports, onSelectReport]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (
      selectable &&
      typeof selectedLat === 'number' &&
      typeof selectedLon === 'number' &&
      !Number.isNaN(selectedLat) &&
      !Number.isNaN(selectedLon)
    ) {
      if (!pickerMarkerRef.current) {
        pickerMarkerRef.current = L.marker([selectedLat, selectedLon], {
          icon: PICKER_ICON,
        }).addTo(map);
      } else {
        pickerMarkerRef.current.setLatLng([selectedLat, selectedLon]);
      }
      pickerMarkerRef.current.bindTooltip('Ubicación seleccionada para el reporte', {
        direction: 'top',
        offset: [0, -36],
      });
    } else if (pickerMarkerRef.current) {
      pickerMarkerRef.current.remove();
      pickerMarkerRef.current = null;
    }
  }, [selectable, selectedLat, selectedLon]);

  return (
    <div className="civia-map-shell">
      <div
        ref={containerRef}
        style={{ height, width: '100%' }}
        aria-label="Mapa interactivo de reportes ciudadanos en Santiago de Cali"
      />
      <div className="civia-map-legend" aria-label="Convenciones del mapa">
        <span>
          <i style={{ background: CATEGORY_COLORS.HUECO }} /> Huecos viales
        </span>
        <span>
          <i style={{ background: CATEGORY_COLORS.BASURAS }} /> Basuras y escombros
        </span>
        <span>
          <i style={{ background: CATEGORY_COLORS.TALA }} /> Tala arbórea
        </span>
        <span>
          <i style={{ background: CATEGORY_COLORS.QUEMA }} /> Quemas e incendios
        </span>
        <span>
          <i style={{ background: CATEGORY_COLORS.PENDIENTE }} /> En análisis / Otro
        </span>
      </div>
    </div>
  );
}
