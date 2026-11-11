import { speakerSnapshot } from './speakerContext';

const valid = { instance_id: 'server-one', revision: 0, context_cursor: 3, scope: 'current_user',
  profile_writes_for_new_turn: true, real_actions_for_new_turn: true,
  general_coreference_verified: false, version: 1 };

it.each(['current_user', 'fictional_character', 'unverified'])('accepts source scope %s with coherent new-turn permissions', scope => {
  const real = scope === 'current_user';
  const value = { ...valid, scope, profile_writes_for_new_turn: real, real_actions_for_new_turn: real };
  expect(speakerSnapshot(value)).toEqual(value);
});

it.each([null, [], { ...valid, text: 'private-source-text' }, { ...valid, scope: 'guess' },
  { ...valid, scope: 'fictional_character' }, { ...valid, profile_writes_for_new_turn: 'true' },
  { ...valid, real_actions_for_new_turn: false }, { ...valid, general_coreference_verified: true },
  { ...valid, version: 2 }, { ...valid, instance_id: '' }, { ...valid, instance_id: 'bad?instance' },
  { ...valid, revision: -1 }, { ...valid, context_cursor: -1 }, { ...valid, context_cursor: NaN },
  { ...valid, context_cursor: Number.MAX_SAFE_INTEGER + 1 }, { ...valid, revision: '0' },
])('rejects invalid metadata without publishing its contents %#', value => {
  expect(() => speakerSnapshot(value)).toThrow('说话者语境格式无效');
});
