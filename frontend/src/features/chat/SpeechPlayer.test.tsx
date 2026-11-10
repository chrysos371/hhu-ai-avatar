import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { frameAt, useSpeechPlayer } from "./useSpeechPlayer";
import { AvatarStage } from "./AvatarStage";
import type { ChatResult, LipFrame } from "../../lib/types";

const frames: LipFrame[] = [{ time: 0, mouth_open: 0.7, vowel: "a", energy: 1 },
  { time: 0.01, mouth_open: 0.3, vowel: "i", energy: 0.5 }];
const result = { reply: "你好", speech_rate: "-10%", speech_pitch: "-5Hz", mouth_intensity: 0.6 } as ChatResult;
function Harness() {
  const player = useSpeechPlayer();
  return <><button onClick={() => void player.play(0, result)}>朗读</button>
    <button onClick={player.stop}>停止</button><p>{player.status}</p><p>{player.error}</p>
    <AvatarStage mouth={player.mouth} />
    <audio ref={player.audioRef} data-testid="audio" onPlay={player.onPlay} onPause={player.onPause} onEnded={player.onEnded} />
  </>;
}
beforeEach(() => {
  sessionStorage.setItem("avatar-token", "unit-session-token-123456");
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function(this: HTMLMediaElement) {
    this.dispatchEvent(new Event("play")); return Promise.resolve();
  });
  URL.createObjectURL = vi.fn(() => "blob:unit-audio");
  URL.revokeObjectURL = vi.fn();
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
it("uses audio timestamps without extrapolating beyond the last frame", () => {
  expect(frameAt(frames, -1)).toBeNull();
  expect(frameAt(frames, 0.005)?.vowel).toBe("a");
  expect(frameAt(frames, 0.01)?.vowel).toBe("i");
  expect(frameAt(frames, 0.2)).toBeNull();
});
it("fetches audio with a token header, forwards expression parameters, closes on pause and releases on stop", async () => {
  const fetch = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ data: {
    audio_id: "unit_audio_identifier_123456", frames, warning: null,
  }, error: null }) }).mockResolvedValueOnce({ ok: true, blob: async () => new Blob(["wav"]) });
  vi.stubGlobal("fetch", fetch);
  render(<Harness />);
  fireEvent.click(screen.getByText("朗读"));
  await screen.findByText("playing");
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toMatchObject({ rate: "-10%", pitch: "-5Hz", mouth_intensity: 0.6 });
  expect(fetch.mock.calls[1][0]).not.toContain("token");
  expect(fetch.mock.calls[1][1].headers["X-Avatar-Token"]).toBe("unit-session-token-123456");
  const audio = screen.getByTestId("audio") as HTMLAudioElement;
  Object.defineProperty(audio, "paused", { configurable: true, value: false });
  await waitFor(() => expect(screen.getByRole("img")).toHaveAttribute("data-mouth-open", "0.700"));
  fireEvent.pause(audio);
  expect(screen.getByRole("img")).toHaveAttribute("data-mouth-open", "0.000");
  fireEvent.click(screen.getByText("停止"));
  expect(audio).not.toHaveAttribute("src");
  expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:unit-audio");
});
it("cancellation prevents late generation from starting playback", async () => {
  let finish!: (value: unknown) => void;
  const fetch = vi.fn(() => new Promise(resolve => { finish = resolve; }));
  vi.stubGlobal("fetch", fetch);
  render(<Harness />);
  fireEvent.click(screen.getByText("朗读"));
  fireEvent.click(screen.getByText("停止"));
  await act(async () => finish({ ok: true, json: async () => ({ data: { audio_id: "late_audio_identifier_123456", frames }, error: null }) }));
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
  expect(screen.getByText("idle")).toBeInTheDocument();
});
