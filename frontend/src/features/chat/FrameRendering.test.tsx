import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import type { ChatResult, LipFrame } from '../../lib/types';
import { SpeechAvatarStage } from './SpeechAvatarStage';
import { useSpeechPlayer } from './useSpeechPlayer';
import { StrictMode } from 'react';

const frames: LipFrame[] = Array.from({ length: 61 }, (_, i) => ({
  time: i * .01, mouth_open: (i + 1) / 100, vowel: 'a', energy: 1,
}));
let parentRenders: number, rowVisits: number, clock: number, paused: boolean;
let raf: Map<number, FrameRequestCallback>, serial: number;
let latest: ReturnType<typeof useSpeechPlayer>;
function History({ count }: { count: number }) {
  return <div>{Array.from({ length: count }, (_, index) => {
    rowVisits++;
    return <article key={index}><p>历史回复{index}</p><details><pre>{JSON.stringify({
      recalled_memories: [{ content: '有来源的历史片段', source_id: index }], guard: { passed: true }, tool_calls: [],
    }, null, 2)}</pre></details></article>;
  })}</div>;
}
function Harness({ count }: { count: number }) {
  parentRenders++;
  const speech = useSpeechPlayer();
  latest = speech;
  return <><button onClick={() => void speech.play(0, { reply: '受控帧测试' } as ChatResult)}>开始</button>
    <button onClick={speech.stop}>停止</button><output>{speech.status}</output>
    <SpeechAvatarStage frameSource={speech.mouthFrames} /><History count={count} />
    <audio data-testid="audio" ref={speech.audioRef} onPlay={speech.onPlay} onPause={speech.onPause} />
  </>;
}
beforeEach(() => {
  parentRenders = 0; rowVisits = 0; clock = 0; paused = true; serial = 0; raf = new Map();
  sessionStorage.setItem('avatar-token', 'frame-rendering-disposable-test-token');
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { raf.set(++serial, callback); return serial; });
  vi.stubGlobal('cancelAnimationFrame', (id: number) => raf.delete(id));
  vi.spyOn(HTMLMediaElement.prototype, 'paused', 'get').mockImplementation(() => paused);
  vi.spyOn(HTMLMediaElement.prototype, 'ended', 'get').mockReturnValue(false);
  vi.spyOn(HTMLMediaElement.prototype, 'currentTime', 'get').mockImplementation(() => clock);
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => { paused = true; });
  vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => { paused = true; });
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockImplementation(function(this: HTMLMediaElement) {
    paused = false; this.dispatchEvent(new Event('play')); return Promise.resolve();
  });
  URL.createObjectURL = vi.fn(() => 'blob:render-audit'); URL.revokeObjectURL = vi.fn();
  vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(url.endsWith('/speech')
    ? { ok: true, json: async () => ({ data: { audio_id: 'render_audit_audio_identifier', frames, warning: null } }) }
    : { ok: true, blob: async () => new Blob(['controlled-media']) })));
});

it('clears the local frame and pending RAF on pause and StrictMode unmount', async () => {
  const view = render(<StrictMode><Harness count={25} /></StrictMode>);
  fireEvent.click(screen.getByText('开始')); await screen.findByText('playing');
  const source = latest.mouthFrames, audio = screen.getByTestId('audio') as HTMLAudioElement;
  expect(source.getSnapshot()?.mouth_open).toBe(.01);
  paused = true; fireEvent.pause(audio);
  expect(source.getSnapshot()).toBeNull(); expect(raf.size).toBe(0);
  await act(async () => { await audio.play(); });
  expect(source.getSnapshot()?.mouth_open).toBe(.01);
  view.unmount(); expect(source.getSnapshot()).toBeNull(); expect(raf.size).toBe(0);
  expect(audio).not.toHaveAttribute('src'); expect(URL.revokeObjectURL).toHaveBeenCalledTimes(1);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it.each([1, 25, 100])('isolates 60 mouth frames from the parent and %i history rows', async count => {
  render(<Harness count={count} />); fireEvent.click(screen.getByText('开始'));
  await screen.findByText('playing');
  parentRenders = 0; rowVisits = 0;
  const rows: { step: number; rendered: string | null; expected: string; parentRenders: number; rowVisits: number }[] = [];
  for (let step = 1; step <= 60; step++) {
    clock = step * .01;
    const scheduled = [...raf.values()]; raf.clear(); expect(scheduled).toHaveLength(1);
    await act(async () => scheduled.forEach(callback => callback(step * 1000 / 60)));
    rows.push({ step, rendered: screen.getByRole('img').getAttribute('data-mouth-open'),
      expected: frames[step].mouth_open.toFixed(3), parentRenders, rowVisits });
  }
  const measured = { parentRenders, rowVisits };
  fireEvent.click(screen.getByText('停止'));
  const stopped = { mouth: screen.getByRole('img').getAttribute('data-mouth-open'),
    src: screen.getByTestId('audio').getAttribute('src'), pendingRaf: raf.size };
  const folder = process.env.AVATAR_RENDER_EVIDENCE_DIR;
  if (folder) {
    mkdirSync(folder, { recursive: true });
    const paths = ['src/features/chat/useSpeechPlayer.ts', 'src/features/chat/AvatarStage.tsx',
      'src/features/chat/SpeechAvatarStage.tsx', 'src/features/chat/speechFrames.ts',
      'src/features/chat/FrameRendering.test.tsx', '../evals/interaction/cycle-09/render-protocol.json'];
    writeFileSync(join(folder, `history-${count}.json`), JSON.stringify({
      scope: 'JSDOM/React structural counts with deterministic media/RAF, not CPU or physical timing',
      head: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
      sourceSha256: Object.fromEntries(paths.map(path => [path, createHash('sha256').update(readFileSync(path)).digest('hex')])),
      count, updates: 60, ...measured, rows, stopped,
    }, null, 2) + '\n', { flag: 'wx' });
  }
  expect(rows.every(row => row.rendered === row.expected)).toBe(true);
  expect(stopped).toEqual({ mouth: '0.000', src: null, pendingRaf: 0 });
  expect(measured.parentRenders).toBe(0); expect(measured.rowVisits).toBe(0);
});
