import { useEffect, useState } from 'react';
import brandIcon from '../assets/civia.svg';
import type { Page } from '../types';

export function Brand({ href, subtitle }: { href: string; subtitle?: string }) {
  return <a className="brand" href={href}><img src={brandIcon} alt="" width="38" height="38" />
    <span><strong>CIVIA</strong>{subtitle && <small>{subtitle}</small>}</span>
  </a>;
}

export function useLoad<T>(load: () => Promise<T>, dependencies: readonly unknown[] = []) {
  const [state, setState] = useState<{ value?: T; loading: boolean; error: string }>({ loading: true, error: '' });
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setState({ loading: true, error: '' });
    load().then((value) => { if (!cancelled) setState({ value, loading: false, error: '' }); })
      .catch((reason: Error) => { if (!cancelled) setState({ error: reason.message, loading: false }); });
    return () => { cancelled = true; };
  }, [version, ...dependencies]);
  return { ...state, reload: () => setVersion((previous) => previous + 1) };
}

export function PageControls({ page, onOffset }: { page?: Page<unknown>; onOffset: (offset: number) => void }) {
  if (!page || page.total <= page.limit) return null;
  return <nav className="actions pagination" aria-label="Paginación">
    <button className="secondary" disabled={page.offset === 0} onClick={() => onOffset(Math.max(0, page.offset - page.limit))}>Anterior</button>
    <span>{page.offset + 1}–{Math.min(page.offset + page.limit, page.total)} de {page.total}</span>
    <button className="secondary" disabled={page.offset + page.limit >= page.total} onClick={() => onOffset(page.offset + page.limit)}>Siguiente</button>
  </nav>;
}

export function LoadNotice({ loading, error }: { loading: boolean; error: string }) {
  return error ? <p role="alert">{error}</p> : loading ? <p role="status">Cargando información…</p> : null;
}
