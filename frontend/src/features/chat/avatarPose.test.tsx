import { describe, expect, it } from 'vitest';
import { avatarPose } from './avatarPose';

describe('formal avatar pose from the shared media frame', () => {
  it('uses the exact media frame and closes on pause/stop without an idle mouth oscillator', () => {
    const active = avatarPose({ mouth: { time: 1.25, mouth_open: .8, vowel: 'a', energy: .4 }, speaking: true });
    expect(active.open).toBe(.8); expect(active.mediaTime).toBe(1.25);
    expect(active.mouthHeight).toBeGreaterThan(.1);
    expect(avatarPose({ mouth: null }).mouthHeight).toBe(.018);
    expect(avatarPose({ mouth: null, speaking: true }).headRoll).toBe(0);
  });
  it('keeps distinct supplied round and wide visemes without inventing new phonemes', () => {
    const frame = { time: .2, mouth_open: .7, energy: .4 };
    const round = avatarPose({ mouth: { ...frame, vowel: 'u' } });
    const wide = avatarPose({ mouth: { ...frame, vowel: 'i' } });
    expect(round.mouthWidth).toBeLessThan(wide.mouthWidth);
    expect(round.mouthHeight).toBeGreaterThan(wide.mouthHeight);
  });
  it('rejects nonfinite source values into a neutral closed pose', () => {
    const pose = avatarPose({ mouth: { time: NaN, mouth_open: NaN, vowel: 'a', energy: 0 }, valence: Infinity });
    expect(pose.open).toBe(0); expect(pose.mediaTime).toBe(0); expect(pose.browTilt).toBe(0);
  });
  it('replaying an identical frame after a seek gives an identical pose', () => {
    const input = { mouth: { time: .9, mouth_open: .6, vowel: 'o', energy: .3 }, valence: .4, speaking: true };
    const first = avatarPose(input);
    avatarPose({ ...input, mouth: { ...input.mouth, time: 99 } });
    expect(avatarPose(input)).toEqual(first);
  });
});
