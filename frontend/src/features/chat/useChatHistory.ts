import { useCallback, useEffect, useLayoutEffect, useRef, useState, type SetStateAction } from 'react';
import { ApiError, apiRequest } from '../../lib/api';
import { subscribeConversationPrivacy, type ChatRow, type ConversationSnapshot } from '../../lib/conversation';
import type { ChatResult } from '../../lib/types';
import { watchConversationChanges } from '../../lib/conversationWatch';
import type { ConversationVersion } from '../../lib/conversationWatch';
import { readSpeakerContext, type SpeakerSnapshot } from '../../lib/speakerContext';

type Version = ConversationVersion;
type View = { rows: ChatRow[]; ready: boolean; loading: boolean; error: Error | null;
  hasMore: boolean; before: number | null; version: Version | null;
  context: SpeakerSnapshot | null; contextLoading: boolean; contextError: Error | null };

export function useChatHistory({ isBusy, onInvalidate, includeContext = false }: {
  isBusy: () => boolean; onInvalidate: () => void; includeContext?: boolean;
}) {
  const [view, setView] = useState<View>({ rows: [], ready: false, loading: true, error: null, hasMore: false,
    before: null, version: null, context: null, contextLoading: false, contextError: null });
  const current = useRef(view);
  useLayoutEffect(() => { current.current = view; }, [view]);
  const version = useRef<Version | null>(null);
  const syncAvailable = useRef(true);
  const request = useRef<AbortController | null>(null), generation = useRef(0), epoch = useRef(0), mounted = useRef(false);
  const contextRequest = useRef<AbortController | null>(null), contextGeneration = useRef(0);
  const refreshRef = useRef<(() => Promise<void>) | null>(null);
  const setRows = useCallback((update: SetStateAction<ChatRow[]>) => {
    setView(old => ({ ...old, rows: typeof update === 'function' ? update(old.rows) : update }));
  }, []);
  const clearForPrivacy = useCallback(() => {
    epoch.current++; generation.current++; request.current?.abort();
    contextGeneration.current++; contextRequest.current?.abort();
    onInvalidate();
    setView(old => ({ ...old, rows: [], ready: false, hasMore: false, before: null, error: null,
      context: null, contextLoading: false, contextError: null }));
  }, [onInvalidate]);
  const loadContext = useCallback(async () => {
    const expected = version.current;
    if (!includeContext || !mounted.current || !syncAvailable.current || !expected) return;
    const ticket = ++contextGeneration.current, submittedEpoch = epoch.current;
    contextRequest.current?.abort(); const controller = new AbortController(); contextRequest.current = controller;
    setView(old => ({ ...old, context: null, contextLoading: true, contextError: null }));
    try {
      const data = await readSpeakerContext(controller.signal);
      if (!mounted.current || ticket !== contextGeneration.current || !syncAvailable.current
        || submittedEpoch !== epoch.current || version.current?.instance_id !== expected.instance_id) return;
      const known = version.current;
      if (data.instance_id !== known.instance_id || data.revision > known.revision) {
        clearForPrivacy();
        version.current = { instance_id: data.instance_id, revision: data.revision, context_cursor: data.context_cursor };
        void refreshRef.current?.(); return;
      }
      if (data.revision < known.revision || data.context_cursor < (known.context_cursor ?? 0)) return;
      const next = { instance_id: data.instance_id, revision: data.revision, context_cursor: data.context_cursor };
      version.current = next;
      setView(old => ({ ...old, version: next, context: data, contextLoading: false, contextError: null }));
    } catch (error) {
      if (!mounted.current || ticket !== contextGeneration.current || controller.signal.aborted) return;
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
        syncAvailable.current = false; clearForPrivacy();
        setView(old => ({ ...old, loading: false, error: new Error('语境核验鉴权失败，请使用启动链接重新打开。' + error.message) }));
        return;
      }
      setView(old => ({ ...old, context: null, contextLoading: false,
        contextError: error instanceof Error ? error : new Error('暂时无法核验说话者语境。') }));
    } finally {
      if (mounted.current && ticket === contextGeneration.current) setView(old => ({ ...old, contextLoading: false }));
    }
  }, [clearForPrivacy, includeContext]);
  const markContextPending = useCallback(() => {
    if (!includeContext) return;
    contextGeneration.current++; contextRequest.current?.abort();
    setView(old => ({ ...old, context: null, contextLoading: true, contextError: null }));
  }, [includeContext]);
  const load = useCallback(async function load(older = false): Promise<void> {
    if (!mounted.current || !syncAvailable.current) return;
    const cursor = current.current;
    if (older && (!cursor.hasMore || cursor.before === null || !version.current)) return;
    const ticket = ++generation.current;
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    setView(old => ({ ...old, loading: true, error: null }));
    const query = new URLSearchParams({ limit: '100' });
    if (older) { query.set('before_id', String(cursor.before)); query.set('revision', String(version.current!.revision)); }
    try {
      const data = await apiRequest<ConversationSnapshot>('/conversation?' + query, { signal: controller.signal });
      if (!mounted.current || ticket !== generation.current || !syncAvailable.current) return;
      const prior = version.current;
      if (prior && prior.instance_id === data.instance_id && data.revision < prior.revision) return;
      const changed = prior !== null && (prior.instance_id !== data.instance_id || prior.revision !== data.revision);
      if (changed) clearForPrivacy();
      // An unchanged read during streaming cannot duplicate its persisted user
      // message or replace the local partial assistant. Re-read on settlement.
      if (!changed && isBusy()) return;
      const next: Version = { instance_id: data.instance_id, revision: data.revision,
        ...(includeContext ? { context_cursor: changed ? 0 : (prior?.context_cursor ?? 0) } : {}) };
      version.current = next;
      setView(old => {
        const same = old.version?.instance_id === data.instance_id && old.version.revision === data.revision;
        const stored = same ? old.rows.filter(row => row.id !== undefined) : [];
        const rows = new Map(stored.map(row => [row.id!, row]));
        for (const row of data.items) rows.set(row.id, row);
        const keepOlderRange = same && !older && stored.length > 0 && data.items.length > 0
          && Math.min(...stored.map(row => row.id!)) < data.items[0].id;
        return { ...old, rows: [...rows.values()].sort((a, b) => a.id! - b.id!), ready: true, loading: false, error: null,
          hasMore: keepOlderRange ? old.hasMore : data.has_more,
          before: keepOlderRange ? old.before : data.next_before_id,
          version: next };
      });
      if (!older) void loadContext();
    } catch (error) {
      if (!mounted.current || ticket !== generation.current || controller.signal.aborted) return;
      if (older && error instanceof ApiError && error.code === 'conversation_changed') {
        clearForPrivacy(); await load(false); return;
      }
      setView(old => ({ ...old, error: error instanceof Error ? error : new Error('对话记录读取失败。') }));
    } finally {
      if (mounted.current && ticket === generation.current) setView(old => ({ ...old, loading: false }));
    }
  }, [clearForPrivacy, includeContext, isBusy, loadContext]);
  refreshRef.current = load;
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
      contextGeneration.current++; contextRequest.current?.abort();
      unsubscribe(); window.removeEventListener('focus', focus); document.removeEventListener('visibilitychange', visible);
    };
  }, [clearForPrivacy, load]);
  const watchInstance = view.version?.instance_id;
  useEffect(() => {
    if (!watchInstance || !version.current) return;
    const controller = new AbortController();
    let recovering = false;
    void watchConversationChanges(version.current, controller.signal, {
      onVersion: value => {
        if (!mounted.current || controller.signal.aborted) return;
        const prior = version.current;
        if (prior?.instance_id === value.instance_id && value.revision < prior.revision) return;
        if (includeContext && prior?.instance_id === value.instance_id && value.revision === prior.revision
          && (value.context_cursor ?? 0) < (prior.context_cursor ?? 0)) return;
        const changed = prior?.instance_id !== value.instance_id || prior.revision !== value.revision;
        const contextChanged = includeContext && (prior?.context_cursor ?? 0) !== (value.context_cursor ?? 0);
        syncAvailable.current = true;
        if (changed || recovering) {
          if (!recovering) clearForPrivacy();
          version.current = value; recovering = false;
          void load();
        } else if (contextChanged) {
          // Ordinary source changes update only control metadata. They neither
          // erase local drafts/history nor cancel a running generation.
          version.current = value;
          setView(old => ({ ...old, version: value }));
          void loadContext();
        }
      },
      onUnavailable: error => {
        if (!mounted.current || controller.signal.aborted) return;
        syncAvailable.current = false;
        if (!recovering) { recovering = true; clearForPrivacy(); }
        const terminal = error instanceof ApiError && (error.status === 401 || error.status === 403);
        setView(old => ({ ...old, loading: false, error: new Error(terminal
          ? '版本同步鉴权失败，已暂停旧内容；请使用启动链接重新打开。' + error.message
          : '版本同步暂不可用，已暂停旧内容；正在重新连接。' + error.message) }));
      },
    });
    return () => controller.abort();
  }, [watchInstance, clearForPrivacy, includeContext, load, loadContext]);
  const isCurrent = useCallback((submittedEpoch: number, result?: ChatResult) => {
    if (!mounted.current || !syncAvailable.current || submittedEpoch !== epoch.current) return false;
    const revision = result?.conversation?.revision, known = version.current;
    if (known && revision !== undefined && revision !== known.revision) {
      if (revision > known.revision) { clearForPrivacy(); void load(); }
      return false;
    }
    return true;
  }, [clearForPrivacy, load]);
  return { ...view, setRows, refresh: load, refreshContext: loadContext, markContextPending, epoch, isCurrent };
}
