import { createSpeechFrameChannel } from './speechFrames';
import type { LipFrame } from '../../lib/types';

const frame: LipFrame = { time: .1, mouth_open: .7, vowel: 'a', energy: .2 };
it('keeps snapshots stable, immutable and separate from the mutable input', () => {
  const channel = createSpeechFrameChannel(), listener = vi.fn();
  channel.subscribe(listener);
  expect(channel.getSnapshot()).toBeNull(); expect(channel.getServerSnapshot()).toBeNull();
  const input = { ...frame }; channel.publish(input);
  const first = channel.getSnapshot(); expect(Object.isFrozen(first)).toBe(true);
  input.mouth_open = 0; expect(first?.mouth_open).toBe(.7);
  channel.publish({ ...frame }); expect(channel.getSnapshot()).toBe(first); expect(listener).toHaveBeenCalledTimes(1);
  channel.publish({ ...frame, time: .2 });
  expect(channel.getSnapshot()).not.toBe(first); expect(first).toEqual(frame);
});
it('notifies on each changed frame field but suppresses unchanged and repeated clears', () => {
  const channel = createSpeechFrameChannel(), listener = vi.fn(); channel.subscribe(listener);
  channel.publish(null); expect(listener).not.toHaveBeenCalled();
  for (const field of ['time', 'mouth_open', 'vowel', 'energy'] as const) {
    channel.publish(frame); listener.mockClear();
    channel.publish({ ...frame, [field]: field === 'vowel' ? 'u' : frame[field] as number + .1 });
    expect(listener).toHaveBeenCalledTimes(1);
  }
  channel.publish(null); listener.mockClear(); channel.publish(null);
  expect(channel.getSnapshot()).toBeNull(); expect(listener).not.toHaveBeenCalled();
});
it('unsubscribes consumers and isolates two players through reset and further frames', () => {
  const one = createSpeechFrameChannel(), two = createSpeechFrameChannel();
  const gone = vi.fn(), remaining = vi.fn(), other = vi.fn();
  const unsubscribe = one.subscribe(gone); one.subscribe(remaining); two.subscribe(other);
  one.publish(frame); two.publish({ ...frame, vowel: 'i' });
  unsubscribe(); unsubscribe(); gone.mockClear(); remaining.mockClear(); other.mockClear();
  one.publish(null);
  for (let time = 0; time < 1000; time++) one.publish({ ...frame, time });
  expect(gone).not.toHaveBeenCalled(); expect(other).not.toHaveBeenCalled();
  expect(remaining).toHaveBeenCalledTimes(1001);
  expect(two.getSnapshot()?.vowel).toBe('i'); expect(one.getSnapshot()?.time).toBe(999);
});
