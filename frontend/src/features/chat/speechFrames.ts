import type { LipFrame } from '../../lib/types';

export interface SpeechFrameSource {
  subscribe: (listener: () => void) => () => void;
  getSnapshot: () => Readonly<LipFrame> | null;
  getServerSnapshot: () => null;
}

// One immutable current frame per player; no audio or frame history is retained.
export function createSpeechFrameChannel() {
  let current: Readonly<LipFrame> | null = null;
  const listeners = new Set<() => void>();
  return {
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
    getSnapshot: () => current,
    getServerSnapshot: () => null,
    publish(frame: LipFrame | null) {
      if (current === null && frame === null) return;
      if (current && frame && current.time === frame.time && current.mouth_open === frame.mouth_open
        && current.vowel === frame.vowel && current.energy === frame.energy) return;
      current = frame ? Object.freeze({ ...frame }) : null;
      for (const listener of [...listeners]) listener();
    },
  };
}
