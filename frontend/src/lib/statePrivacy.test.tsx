import { apiRequest } from './api';
import { readStateContext, sameStateContext, stateContext } from './statePrivacy';

vi.mock('./api', () => ({ apiRequest: vi.fn() }));
afterEach(() => vi.clearAllMocks());

it('copies an exact nonnegative safe metadata version', () => {
  const source = { instance_id: 'instance-a', revision: 0 };
  const copy = stateContext(source);
  source.revision = 1;
  expect(copy).toEqual({ instance_id: 'instance-a', revision: 0 });
});

it.each([null, [], {}, { instance_id: 'x', revision: true }, { instance_id: 'x', revision: -1 },
  { instance_id: 'x', revision: '1' }, { instance_id: 'x', revision: 1.5 },
  { instance_id: 'x', revision: Number.MAX_SAFE_INTEGER + 1 }, { instance_id: '', revision: 0 },
  { instance_id: 'x/y', revision: 0 }, { instance_id: 'x', revision: 0, context_cursor: 1 }])(
  'rejects malformed or ambiguous state context %j', value => {
    expect(() => stateContext(value)).toThrow('状态版本格式无效');
  });

it('compares both instance identity and revision without authorizing missing metadata', () => {
  expect(sameStateContext({ instance_id: 'a', revision: 1 }, { instance_id: 'a', revision: 1 })).toBe(true);
  expect(sameStateContext({ instance_id: 'a', revision: 1 }, { instance_id: 'b', revision: 1 })).toBe(false);
  expect(sameStateContext({ instance_id: 'a', revision: 1 }, { instance_id: 'a', revision: 2 })).toBe(false);
  expect(sameStateContext(null, null)).toBe(false);
});

it('reads immediate metadata with the original abort signal, without history or model requests', async () => {
  const controller = new AbortController();
  vi.mocked(apiRequest).mockResolvedValueOnce({ instance_id: 'actual', revision: 7 });
  expect(await readStateContext(controller.signal)).toEqual({ instance_id: 'actual', revision: 7 });
  expect(apiRequest).toHaveBeenCalledExactlyOnceWith(
    '/conversation/changes?instance_id=state-bootstrap&revision=0', { signal: controller.signal });
});

it('rejects a malformed metadata response before returning state authorization', async () => {
  vi.mocked(apiRequest).mockResolvedValueOnce({ instance_id: 'actual', revision: -1 });
  await expect(readStateContext(new AbortController().signal)).rejects.toThrow('状态版本格式无效');
});
