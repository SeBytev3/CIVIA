import { draftInstallation } from './api';
import { randomId } from './device';

export interface Draft {
  key: string;
  title: string;
  description: string;
  latitude?: number;
  longitude?: number;
  photo?: File;
  audio?: File;
  pending: boolean;
}

export function blankDraft(): Draft {
  return { key: randomId(), title: '', description: '', pending: false };
}

function transaction<T>(mode: IDBTransactionMode, action: (store: IDBObjectStore) => () => T): Promise<T> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('civia-drafts', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('reports');
    request.onerror = () => reject(request.error);
    request.onsuccess = () => {
      const db = request.result;
      const tx = db.transaction('reports', mode);
      const result = action(tx.objectStore('reports'));
      tx.oncomplete = () => {
        db.close();
        resolve(result());
      };
      tx.onabort = () => {
        db.close();
        reject(tx.error);
      };
    };
  });
}

function store<T>(mode: IDBTransactionMode, action: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return transaction(mode, (db) => {
    const result = action(db);
    return () => result.result;
  });
}

export async function draftStorage(ownerId: string) {
  const installationId = await draftInstallation(ownerId);
  const key = `${installationId}:${ownerId}`;
  return {
    installationId,
    read: () => store<Draft | undefined>('readonly', (db) => db.get(key)),
    save: (draft: Draft) => store('readwrite', (db) => db.put(draft, key)),
    remove: () => store('readwrite', (db) => db.delete(key)),
    readLegacy: () => store<Draft | undefined>('readonly', (db) => db.get(ownerId)),
    recoverLegacy: () => transaction<Draft | undefined>('readwrite', (db) => {
      let restored: Draft | undefined;
      const current = db.get(key);
      current.onsuccess = () => {
        if (current.result) return;
        const legacy = db.get(ownerId);
        legacy.onsuccess = () => {
          if (!legacy.result) return;
          restored = { ...(legacy.result as Draft), pending: false };
          db.put(restored, key);
          db.delete(ownerId);
        };
      };
      return () => restored;
    }),
  };
}

export type DraftStorage = Awaited<ReturnType<typeof draftStorage>>;
