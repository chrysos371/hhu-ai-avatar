import { apiRequest } from './api';

export interface SpeakerSnapshot {
  instance_id: string; revision: number; context_cursor: number;
  scope: 'current_user' | 'fictional_character' | 'unverified';
  profile_writes_for_new_turn: boolean; real_actions_for_new_turn: boolean;
  general_coreference_verified: false; version: 1;
}
export const speakerControls = {
  current_user: '回到现实。',
  fictional_character: '我来扮演一个虚构角色。',
} as const;
export type SpeakerChoice = keyof typeof speakerControls;

export function speakerSnapshot(value: unknown): SpeakerSnapshot {
  const fields = 'context_cursor,general_coreference_verified,instance_id,profile_writes_for_new_turn,real_actions_for_new_turn,revision,scope,version';
  const invalid = () => new Error('说话者语境格式无效，请重新核验。');
  if (!value || typeof value !== 'object' || Object.keys(value).sort().join(',') !== fields) throw invalid();
  const data = value as SpeakerSnapshot;
  if (typeof data.instance_id !== 'string' || !/^[A-Za-z0-9_-]{1,100}$/.test(data.instance_id)
      || !Number.isSafeInteger(data.revision) || data.revision < 0
      || !Number.isSafeInteger(data.context_cursor) || data.context_cursor < 0
      || !['current_user', 'fictional_character', 'unverified'].includes(data.scope)
      || data.general_coreference_verified !== false || data.version !== 1) throw invalid();
  const real = data.scope === 'current_user';
  if (data.profile_writes_for_new_turn !== real || data.real_actions_for_new_turn !== real) throw invalid();
  return data;
}

export async function readSpeakerContext(signal: AbortSignal) {
  return speakerSnapshot(await apiRequest<unknown>('/conversation/speaker', { signal }));
}
