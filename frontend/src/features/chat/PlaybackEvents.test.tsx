import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ChatResult } from '../../lib/types';
import { useSpeechPlayer } from './useSpeechPlayer';

const result = { reply: '这段最终回复需要依次朗读，每一段都保持原来的顺序，不让过时事件改变当前的播放。'.repeat(5) } as ChatResult;
function Harness() {
  const speech = useSpeechPlayer();
  return <><button onClick={() => void speech.play(0, result, true)}>开始</button>
    <button onClick={speech.stop}>停止</button><output data-testid="status">{speech.status}</output>
    <output data-testid="segment">{speech.segment.index}</output>
    <audio data-testid="audio" ref={speech.audioRef} onPlay={speech.onPlay} onPause={speech.onPause}
      onEnded={speech.onEnded} onError={speech.onError} /></>;
}
let media: { paused: boolean; ended: boolean; error: MediaError | null };
let prepared: number;
beforeEach(() => {
  media = { paused: true, ended: false, error: null }; prepared = 0;
  sessionStorage.setItem('avatar-token', 'queued-media-event-unit-token');
  vi.spyOn(HTMLMediaElement.prototype, 'paused', 'get').mockImplementation(() => media.paused);
  vi.spyOn(HTMLMediaElement.prototype, 'ended', 'get').mockImplementation(() => media.ended);
  vi.spyOn(HTMLMediaElement.prototype, 'error', 'get').mockImplementation(() => media.error);
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockImplementation(function (this: HTMLMediaElement) {
    media.paused = false; media.ended = false; this.dispatchEvent(new Event('play')); return Promise.resolve();
  });
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(function (this: HTMLMediaElement) {
    media.paused = true; this.dispatchEvent(new Event('pause'));
  });
  vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => { media.paused = true; media.ended = false; media.error = null; });
  URL.createObjectURL = vi.fn(() => 'blob:queued-event-test'); URL.revokeObjectURL = vi.fn();
  vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(url.endsWith('/speech')
    ? { ok: true, json: async () => ({ data: { audio_id: 'queued_audio_identifier_' + (++prepared).toString().padStart(8, '0'), frames: [], warning: null } }) }
    : url.endsWith('/cancel') ? { ok: true, json: async () => ({ data: { cancelled: true } }) }
      : { ok: true, blob: async () => new Blob(['controlled-unit-audio']) })));
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
async function begin() {
  render(<Harness />); fireEvent.click(screen.getByText('开始'));
  await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('playing'));
  await waitFor(() => expect(prepared).toBe(2));
  return screen.getByTestId('audio') as HTMLAudioElement;
}

it('does not let a queued old play event revive stopped playback', async () => {
  const audio = await begin(); fireEvent.click(screen.getByText('停止'));
  expect(audio).not.toHaveAttribute('src'); expect(media.paused).toBe(true);
  fireEvent.play(audio);
  expect(screen.getByTestId('status')).toHaveTextContent('idle');
});
it('does not pause a healthy current source when an old pause event arrives', async () => {
  const audio = await begin(); expect(media.paused).toBe(false);
  fireEvent.pause(audio);
  expect(screen.getByTestId('status')).toHaveTextContent('playing');
});
it('does not advance the current queue when an old ended event arrives mid-play', async () => {
  const audio = await begin(); expect(media.ended).toBe(false);
  await act(async () => fireEvent.ended(audio));
  expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
  expect(screen.getByTestId('segment')).toHaveTextContent('1');
});
it('does not release a healthy new source on an old error event', async () => {
  const audio = await begin(); expect(media.error).toBeNull();
  fireEvent.error(audio);
  expect(audio).toHaveAttribute('src');
  expect(screen.getByTestId('status')).toHaveTextContent('playing');
});
it('still handles genuine pause and resume state', async () => {
  const audio = await begin(); media.paused = true; fireEvent.pause(audio);
  expect(screen.getByTestId('status')).toHaveTextContent('paused');
  media.paused = false; fireEvent.play(audio);
  expect(screen.getByTestId('status')).toHaveTextContent('playing');
});
it('still advances on a genuine ended state', async () => {
  const audio = await begin(); media.ended = true; media.paused = true;
  await act(async () => fireEvent.ended(audio));
  await waitFor(() => expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(2));
  expect(screen.getByTestId('segment')).toHaveTextContent('2');
});
it('still reports a current decoder error', async () => {
  const audio = await begin(); media.error = { code: 3, message: 'controlled decoder failure' } as MediaError;
  fireEvent.error(audio);
  expect(screen.getByTestId('status')).toHaveTextContent('error'); expect(audio).not.toHaveAttribute('src');
});
