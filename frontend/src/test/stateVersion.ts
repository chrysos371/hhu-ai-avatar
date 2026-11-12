import { response } from './render';
import type { StateContext } from '../lib/statePrivacy';

export function stateVersion(initial: StateContext = { instance_id: 'unit-state', revision: 0 }) {
  let current = { ...initial };
  const waits = new Set<(error?: Error) => void>();
  return {
    get current() { return { ...current }; },
    get pending() { return waits.size; },
    handle(path: string, options?: RequestInit): Promise<ReturnType<typeof response>> | null {
      if (!path.startsWith('/api/v1/conversation/changes?')) return null;
      const query = new URL(path, 'http://127.0.0.1').searchParams;
      if (query.get('instance_id') !== current.instance_id || Number(query.get('revision')) !== current.revision) {
        return Promise.resolve(response({ ...current }));
      }
      return new Promise((resolve, reject) => {
        let completed = false;
        const finish = (error?: Error) => {
          if (completed) return;
          completed = true;
          waits.delete(finish);
          options?.signal?.removeEventListener('abort', abort);
          if (error) reject(error); else resolve(response({ ...current }));
        };
        const abort = () => finish(new DOMException('Aborted', 'AbortError'));
        waits.add(finish);
        options?.signal?.addEventListener('abort', abort, { once: true });
        if (options?.signal?.aborted) abort();
      });
    },
    advance(next: StateContext) {
      current = { ...next };
      for (const finish of [...waits]) finish();
    },
    fail(error: Error) { for (const finish of [...waits]) finish(error); },
  };
}
