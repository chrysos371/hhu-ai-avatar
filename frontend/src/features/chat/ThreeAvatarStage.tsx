import { useEffect, useRef } from 'react';
import type { AvatarPoseInput } from './avatarPose';
import type { AvatarRig, RendererStatus } from './threeAvatar';

export function ThreeAvatarStage({ mouth, valence, arousal, busy, speaking, onStatus }: AvatarPoseInput & {
  onStatus: (status: RendererStatus) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const rig = useRef<AvatarRig | null>(null);
  const latest = useRef<AvatarPoseInput>({ mouth, valence, arousal, busy, speaking });
  useEffect(() => {
    const input = { mouth, valence, arousal, busy, speaking };
    latest.current = input; rig.current?.present(input);
  }, [mouth, valence, arousal, busy, speaking]);
  useEffect(() => {
    if (typeof WebGL2RenderingContext === 'undefined') { onStatus('fallback'); return; }
    let closed = false;
    let active: AvatarRig | null = null;
    void import('./threeAvatar').then(({ createAvatarRig }) => {
      if (closed || !host.current) return;
      try {
        active = createAvatarRig(host.current, latest.current, status => { if (!closed) onStatus(status); });
        rig.current = active;
      } catch { if (!closed) onStatus('fallback'); }
    }).catch(() => { if (!closed) onStatus('fallback'); });
    return () => { closed = true; active?.dispose(); rig.current = null; };
  }, [onStatus]);
  return <div className="avatar-three-host" ref={host} aria-hidden="true" />;
}
