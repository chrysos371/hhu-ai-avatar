import { useCallback, useEffect, useLayoutEffect, useRef, useState, type SetStateAction } from 'react';
import { ApiError, apiRequest } from '../../lib/api';
import { subscribeConversationPrivacy, type ChatRow, type ConversationSnapshot } from '../../lib/conversation';
import type { ChatResult } from '../../lib/types';

type Version = Pick<ConversationSnapshot, 'instance_id' | 'revision'>;
type View = { rows: ChatRow[]; ready: boolean; loading: boolean; error: Error | null;
  hasMore: boolean; before: number | null; version: Version | null };

export function useChatHistory({ isBusy, onInvalidate }: { isBusy: () => boolean; onInvalidate: () => void }) {
  const [view, setView] = useState<View>({ rows: [], ready: false, loading: true, error: null, hasMore: false, before: null, version: null });
  const current = useRef(view);
  useLayoutEffect(() => { current.current = view; }, [view]);
  const version = useRef<Version | null>(null);
  const request = useRef<AbortController | null>(null), generation = useRef(0), epoch = useRef(0), mounted = useRef(false);
  const setRows = useCallback((update: SetStateAction<ChatRow[]>) => {
    setView(old => ({ ...old, rows: typeof update === 'function' ? update(old.rows) : update }));
  }, []);
  const clearForPrivacy = useCallback(() => {
    epoch.current++; generation.current++; request.current?.abort();
    onInvalidate();
    setView(old => ({ ...old, rows: [], ready: false, hasMore: false, before: null, error: null }));
  }, [onInvalidate]);
  const load = useCallback(async function load(older = false): Promise<void> {
    if (!mounted.current) return;
    const cursor = current.current;
    if (older && (!cursor.hasMore || cursor.before === null || !version.current)) return;
    const ticket = ++generation.current;
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    setView(old => ({ ...old, loading: true, error: null }));
    const query = new URLSearchParams({ limit: '100' });
    if (older) { query.set('before_id', String(cursor.before)); query.set('revision', String(version.current!.revision)); }
    try {
      const data = await apiRequest<ConversationSnapshot>('/conversation?' + query, { signal: controller.signal });
      if (!mounted.current || ticket !== generation.current) return;
      const prior = version.current;
      if (prior && prior.instance_id === data.instance_id && data.revision < prior.revision) return;
      const changed = prior !== null && (prior.instance_id !== data.instance_id || prior.revision !== data.revision);
      if (changed) clearForPrivacy();
      // An unchanged read during streaming cannot duplicate its persisted user
      // message or replace the local partial assistant. Re-read on settlement.
      if (!changed && isBusy()) return;
      version.current = { instance_id: data.instance_id, revision: data.revision };
      setView(old => {
        const same = old.version?.instance_id === data.instance_id && old.version.revision === data.revision;
        const stored = same ? old.rows.filter(row => row.id !== undefined) : [];
        const rows = new Map(stored.map(row => [row.id!, row]));
        for (const row of data.items) rows.set(row.id, row);
        const keepOlderRange = same && !older && stored.length > 0 && data.items.length > 0
          && Math.min(...stored.map(row => row.id!)) < data.items[0].id;
        return { rows: [...rows.values()].sort((a, b) => a.id! - b.id!), ready: true, loading: false, error: null,
          hasMore: keepOlderRange ? old.hasMore : data.has_more,
          before: keepOlderRange ? old.before : data.next_before_id,
          version: { instance_id: data.instance_id, revision: data.revision } };
      });
    } catch (error) {
      if (!mounted.current || ticket !== generation.current || controller.signal.aborted) return;
      if (older && error instanceof ApiError && error.code === 'conversation_changed') {
        clearForPrivacy(); await load(false); return;
      }
      setView(old => ({ ...old, error: error instanceof Error ? error : new Error('对话记录读取失败。') }));
    } finally {
      if (mounted.current && ticket === generation.current) setView(old => ({ ...old, loading: false }));
    }
  }, [clearForPrivacy, isBusy]);
  useEffect(() => {
    mounted.current = true;
    const privacy = () => { clearForPrivacy(); void load(); };
    const focus = () => { void load(); };
    const visible = () => { if (document.visibilityState === 'visible') void load(); };
    const unsubscribe = subscribeConversationPrivacy(privacy);
    window.addEventListener('focus', focus); document.addEventListener('visibilitychange', visible);
    void load();
    return () => {
      mounted.current = false; generation.current++; epoch.current++; request.current?.abort();
      unsubscribe(); window.removeEventListener('focus', focus); document.removeEventListener('visibilitychange', visible);
    };
  }, [clearForPrivacy, load]);
  const isCurrent = useCallback((submittedEpoch: number, result?: ChatResult) => {
    if (!mounted.current || submittedEpoch !== epoch.current) return false;
    const revision = result?.conversation?.revision, known = version.current;
    if (known && revision !== undefined && revision !== known.revision) {
      if (revision > known.revision) { clearForPrivacy(); void load(); }
      return false;
    }
    return true;
  }, [clearForPrivacy, load]);
  return { ...view, setRows, refresh: load, epoch, isCurrent };
}
