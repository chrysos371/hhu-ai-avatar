import { useSyncExternalStore, type ComponentProps } from 'react';
import { AvatarStage } from './AvatarStage';
import type { SpeechFrameSource } from './speechFrames';

export function SpeechAvatarStage({ frameSource, ...props }: Omit<ComponentProps<typeof AvatarStage>, 'mouth'> & {
  frameSource: SpeechFrameSource;
}) {
  const mouth = useSyncExternalStore(frameSource.subscribe, frameSource.getSnapshot, frameSource.getServerSnapshot);
  return <AvatarStage {...props} mouth={mouth} />;
}
