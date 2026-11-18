import { useEffect, useState } from 'react';
import { experience, standaloneDisplay } from '../experience';

interface InstallPrompt extends Event {
  prompt(): Promise<unknown>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

export function InstallPanel() {
  const [prompt, setPrompt] = useState<InstallPrompt>();
  const [hidden, setHidden] = useState(() => experience() !== 'browser');
  const [showHelp, setShowHelp] = useState(() => location.hash === '#instalar');

  useEffect(() => {
    const display = window.matchMedia(standaloneDisplay);
    const readDisplay = () => setHidden(experience() !== 'browser');
    const capture = (event: Event) => {
      event.preventDefault();
      setPrompt(event as InstallPrompt);
    };
    const installed = () => {
      setHidden(true);
      setPrompt(undefined);
    };
    window.addEventListener('beforeinstallprompt', capture);
    window.addEventListener('appinstalled', installed);
    display.addEventListener('change', readDisplay);
    return () => {
      window.removeEventListener('beforeinstallprompt', capture);
      window.removeEventListener('appinstalled', installed);
      display.removeEventListener('change', readDisplay);
    };
  }, []);

  if (hidden) return null;
  return <aside className="surface install-panel stack" aria-labelledby="install-title">
    <h2 id="install-title">Instalar CIVIA</h2>
    {!window.isSecureContext ? <p>La instalación necesita la dirección HTTPS de CIVIA. Abre el enlace seguro de tu instalación para continuar.</p>
      : prompt ? <button onClick={async () => {
        setPrompt(undefined);
        try {
          await prompt.prompt();
          const choice = await prompt.userChoice;
          if (choice.outcome === 'accepted') setHidden(true);
        } catch {
          setShowHelp(true);
        }
      }}>Instalar aplicación</button>
        : <details open={showHelp} onToggle={(event) => setShowHelp(event.currentTarget.open)}>
          <summary>Cómo instalar CIVIA</summary>
          {'standalone' in navigator
            ? <p>En Safari, toca Compartir y selecciona Añadir a pantalla de inicio.</p>
            : <p>En el menú de tu navegador, elige Instalar aplicación o Añadir a pantalla de inicio, según las opciones de tu dispositivo.</p>}
        </details>}
    <a href="/">Ir al formulario web</a>
  </aside>;
}
