import type { LipFrame } from '../../lib/types';

export type AvatarPoseInput = {
  mouth: LipFrame | null; valence?: number; arousal?: number; busy?: boolean; speaking?: boolean;
};

function finite(value: number | undefined, low: number, high: number, fallback = 0) {
  return typeof value === 'number' && Number.isFinite(value) ? Math.min(high, Math.max(low, value)) : fallback;
}

/** Media frames own mouth movement. There is no elapsed-wall-clock oscillator. */
export function avatarPose(input: AvatarPoseInput) {
  const open = finite(input.mouth?.mouth_open, 0, 1);
  const valence = finite(input.valence, -1, 1);
  const arousal = finite(input.arousal, -1, 1);
  const time = finite(input.mouth?.time, 0, 86400);
  const vowel = input.mouth?.vowel;
  const round = vowel === 'o' || vowel === 'u';
  return {
    open, mediaTime: time,
    mouthWidth: open <= .01 ? .19 : round ? .12 + .04 * open : vowel === 'i' ? .25 : .20 + .06 * open,
    mouthHeight: open <= .01 ? .018 : .025 + open * (vowel === 'i' ? .09 : .19),
    eyeHeight: (valence > .2 ? .78 : 1) + Math.max(0, arousal) * .12,
    browTilt: valence * .14,
    browLift: input.busy ? .025 : Math.max(0, arousal) * .015,
    headRoll: input.speaking && open > 0 ? Math.sin(time * 1.8) * .012 : 0,
  };
}
