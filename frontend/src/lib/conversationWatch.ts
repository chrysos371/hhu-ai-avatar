import { ApiError, apiRequest } from './api';

export interface ConversationVersion { instance_id: string; revision: number; context_cursor?: number }
interface Callbacks {
  onVersion: (value: ConversationVersion) => void;
  onUnavailable: (error: Error) => void;
}
const delays = [250, 500, 1000, 2000, 5000];
function pause(ms: number, signal: AbortSignal) {
  return new Promise<void>(resolve => {
    const finish = () => { clearTimeout(timer); signal.removeEventListener('abort', finish); resolve(); };
    const timer = setTimeout(finish, ms);
    signal.addEventListener('abort', finish, { once: true });
    if (signal.aborted) finish();
  });
}
function metadata(value: unknown, context: boolean): ConversationVersion {
  const fields = context ? 'context_cursor,instance_id,revision' : 'instance_id,revision';
  if (!value || typeof value !== 'object' || Object.keys(value).sort().join(',') !== fields)
    throw new Error('版本通知格式无效。');
  const data = value as ConversationVersion;
  if (typeof data.instance_id !== 'string' || !data.instance_id || data.instance_id.length > 100
    || !Number.isSafeInteger(data.revision) || data.revision < 0) throw new Error('版本通知格式无效。');
  if (context && (typeof data.context_cursor !== 'number' || !Number.isSafeInteger(data.context_cursor)
    || data.context_cursor < 0)) throw new Error('语境通知格式无效。');
  return data;
}

// Exactly one held metadata request, or one backoff timer. A heartbeat never
// fetches transcripts here; the caller decides whether a newer version matters.
export async function watchConversationChanges(initial: ConversationVersion, signal: AbortSignal, callbacks: Callbacks) {
  let known = initial, failures = 0, unavailable = false;
  const context = initial.context_cursor !== undefined;
  while (!signal.aborted) {
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal.addEventListener('abort', abort, { once: true });
    const timeout = setTimeout(abort, 15000);
    let failure: Error | null = null;
    try {
      if (signal.aborted) return;
      const query = new URLSearchParams({ instance_id: known.instance_id, revision: String(known.revision) });
      if (context) query.set('context_cursor', String(known.context_cursor));
      const value = metadata(await apiRequest<unknown>('/conversation/changes?' + query, { signal: controller.signal }), context);
      if (signal.aborted) return;
      if (value.instance_id === known.instance_id && value.revision < known.revision) throw new Error('版本通知倒退，请重新核验。');
      if (context && value.instance_id === known.instance_id && value.context_cursor! < known.context_cursor!)
        throw new Error('语境通知倒退，请重新核验。');
      known = value; failures = 0; unavailable = false;
      callbacks.onVersion(value);
    } catch (error) {
      if (signal.aborted) return;
      failure = error instanceof Error ? error : new Error('版本同步暂不可用。');
    } finally {
      clearTimeout(timeout); signal.removeEventListener('abort', abort);
    }
    if (failure) {
      const terminal = failure instanceof ApiError && (failure.status === 401 || failure.status === 403);
      if (!unavailable || terminal) callbacks.onUnavailable(failure);
      unavailable = true;
      if (terminal) return;
      await pause(delays[Math.min(failures++, delays.length - 1)], signal);
    }
  }
}
