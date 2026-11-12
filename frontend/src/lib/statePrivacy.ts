import { apiRequest } from './api';

export interface StateContext { instance_id: string; revision: number }

export function stateContext(value: unknown): StateContext {
  if (!value || typeof value !== 'object'
    || Object.keys(value).sort().join(',') !== 'instance_id,revision') {
    throw new Error('状态版本格式无效，请重新读取。');
  }
  const context = value as StateContext;
  if (typeof context.instance_id !== 'string' || !/^[A-Za-z0-9_-]{1,100}$/.test(context.instance_id)
    || !Number.isSafeInteger(context.revision) || context.revision < 0) {
    throw new Error('状态版本格式无效，请重新读取。');
  }
  return { instance_id: context.instance_id, revision: context.revision };
}

export function sameStateContext(a: StateContext | null, b: StateContext | null): boolean {
  return !!a && !!b && a.instance_id === b.instance_id && a.revision === b.revision;
}

export async function readStateContext(signal: AbortSignal): Promise<StateContext> {
  // Live instances are 32 hex characters. This distinct bootstrap identifier
  // requests immediate metadata, never a held wait or a transcript snapshot.
  return stateContext(await apiRequest<unknown>(
    '/conversation/changes?instance_id=state-bootstrap&revision=0', { signal }));
}
