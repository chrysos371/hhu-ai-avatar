import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from './api';
import { subscribeConversationPrivacy } from './conversation';
import { watchConversationChanges } from './conversationWatch';
import { readStateContext, sameStateContext, stateContext, type StateContext } from './statePrivacy';

type StateName = 'emotion' | 'dashboard';
interface Basis { context: StateContext | null; epoch: number; available: boolean; error: Error | null }
interface Controls { restart: () => void; invalidate: (error: Error) => void }
const stateNames: StateName[] = ['emotion', 'dashboard'];

export function usePrivateStateQuery<T extends { context: StateContext }>(name: StateName, interval: number) {
  const client = useQueryClient();
  const live = useRef<Basis>({ context: null, epoch: 0, available: false, error: null });
  const [basis, setBasis] = useState<Basis>(live.current);
  const controls = useRef<Controls>({ restart: () => {}, invalidate: () => {} });

  useEffect(() => {
    let mounted = true, generation = 0;
    let controller: AbortController | null = null;
    let bootstrapTimer: ReturnType<typeof setTimeout> | null = null;
    const clearBootstrapTimer = () => {
      if (bootstrapTimer !== null) clearTimeout(bootstrapTimer);
      bootstrapTimer = null;
    };
    const clear = (error: Error | null) => {
      if (!mounted) return;
      live.current = { ...live.current, epoch: live.current.epoch + 1, available: false, error };
      // Cancel both active and inactive derived caches. A query which ignores
      // AbortSignal is also rejected by the epoch check before it can return.
      for (const key of stateNames) {
        void client.cancelQueries({ queryKey: [key] });
        client.removeQueries({ queryKey: [key] });
      }
      setBasis(live.current);
    };
    const unavailable = (error: Error) => {
      if (!mounted) return;
      clear(new Error('版本同步暂不可用，已暂停旧状态。' + error.message));
    };
    const adopt = (value: unknown) => {
      const next = stateContext(value), prior = live.current.context;
      if (prior?.instance_id === next.instance_id && next.revision < prior.revision) {
        throw new Error('状态版本倒退，请重新核验。');
      }
      const changed = !sameStateContext(prior, next);
      if (changed) clear(null);
      if (changed || !live.current.available) {
        live.current = { ...live.current, context: next, available: true, error: null };
        setBasis(live.current);
      }
    };
    const restart = () => {
      const ticket = ++generation;
      controller?.abort();
      clearBootstrapTimer();
      const owner = new AbortController();
      controller = owner;
      const signal = owner.signal;
      clear(null);
      const timer = setTimeout(() => {
        if (!mounted || ticket !== generation || signal.aborted) return;
        owner.abort();
        unavailable(new Error('版本同步超时，请重新读取。'));
      }, 15000);
      bootstrapTimer = timer;
      void (async () => {
        try {
          const initial = await readStateContext(signal);
          clearTimeout(timer);
          if (bootstrapTimer === timer) bootstrapTimer = null;
          if (!mounted || ticket !== generation || signal.aborted) return;
          adopt(initial);
          await watchConversationChanges(initial, signal, {
            onVersion: value => {
              if (!mounted || ticket !== generation || signal.aborted) return;
              try { adopt(value); } catch (error) { unavailable(error as Error); }
            },
            onUnavailable: error => {
              if (mounted && ticket === generation && !signal.aborted) unavailable(error);
            },
          });
        } catch (error) {
          if (mounted && ticket === generation && !signal.aborted) unavailable(error as Error);
        } finally {
          clearTimeout(timer);
          if (bootstrapTimer === timer) bootstrapTimer = null;
        }
      })();
    };
    controls.current = { restart, invalidate: unavailable };
    const unsubscribe = subscribeConversationPrivacy(restart);
    const visible = () => { if (document.visibilityState === 'visible') restart(); };
    window.addEventListener('focus', restart);
    document.addEventListener('visibilitychange', visible);
    restart();
    return () => {
      mounted = false;
      generation++;
      controller?.abort();
      clearBootstrapTimer();
      unsubscribe();
      window.removeEventListener('focus', restart);
      document.removeEventListener('visibilitychange', visible);
      for (const key of stateNames) void client.cancelQueries({ queryKey: [key] });
      live.current = { ...live.current, available: false };
    };
  }, [client, name]);

  const query = useQuery<T, Error>({
    queryKey: [name, basis.context?.instance_id, basis.context?.revision, basis.epoch],
    enabled: basis.available,
    retry: false,
    refetchInterval: interval,
    queryFn: async ({ signal }) => {
      const expected = basis.context, epoch = basis.epoch;
      const value = await apiRequest<T>('/' + name, { signal });
      if (signal.aborted || !live.current.available || live.current.epoch !== epoch
        || !sameStateContext(live.current.context, expected)) {
        throw new DOMException('旧状态读取已失效。', 'AbortError');
      }
      try {
        if (!sameStateContext(stateContext(value.context), expected)) throw new Error('状态来源版本已改变。');
      } catch (error) {
        controls.current.invalidate(error as Error);
        throw error;
      }
      return value;
    },
  });
  return { ...query,
    data: basis.available && query.data && sameStateContext(query.data.context, basis.context) ? query.data : undefined,
    isPending: basis.available ? query.isPending : !basis.error,
    isError: !!basis.error || query.isError,
    error: basis.error ?? query.error,
    refetch: () => live.current.available ? query.refetch() : controls.current.restart(),
    privacyEpoch: basis.epoch,
  };
}
