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
  return { key: crypto.randomUUID(), title: '', description: '', pending: false };
}

function store<T>(mode: IDBTransactionMode, action: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
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
        resolve(result.result);
      };
      tx.onabort = () => {
        db.close();
        reject(tx.error);
      };
    };
  });
}

export function readDraft(ownerId: string) {
  return store<Draft | undefined>('readonly', (db) => db.get(ownerId));
}

export function saveDraft(ownerId: string, draft: Draft) {
  return store('readwrite', (db) => db.put(draft, ownerId));
}

export function deleteDraft(ownerId: string) {
  return store('readwrite', (db) => db.delete(ownerId));
}
