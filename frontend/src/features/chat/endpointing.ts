// Deterministic energy endpointing. Loud noise and quiet speech remain ambiguous.
export const endpointDefaults = Object.freeze({
  rmsThreshold: 0.006, voiceMs: 240, silenceMs: 1200,
  noSpeechMs: 8000, maxMs: 60000, windowMs: 20,
});
export type EndpointReason = "pause" | "no_speech" | "limit";
export class EnergyEndpoint {
  readonly sampleRate: number;
  readonly config: typeof endpointDefaults;
  private readonly windowSamples: number;
  private windowCount = 0;
  private squareSum = 0;
  private total = 0;
  private voiceRunMs = 0;
  private quietMs = 0;
  private heardVoice = false;
  private ended: EndpointReason | null = null;
  constructor(sampleRate: number, config = endpointDefaults) {
    if (!Number.isInteger(sampleRate) || sampleRate < 8000 || sampleRate > 192000)
      throw new RangeError("Unsupported recording sample rate");
    if (Object.values(config).some(value => !Number.isFinite(value) || value <= 0)
      || config.windowMs > config.voiceMs || config.silenceMs >= config.maxMs)
      throw new RangeError("Invalid endpoint parameters");
    this.sampleRate = sampleRate;
    this.config = Object.freeze({ ...config });
    this.windowSamples = Math.round(sampleRate * config.windowMs / 1000);
  }
  get elapsedMs() { return this.total * 1000 / this.sampleRate; }
  push(samples: Float32Array): { reason: EndpointReason | null; consumed: number } {
    if (this.ended) return { reason: this.ended, consumed: 0 };
    let consumed = 0;
    for (const sample of samples) {
      consumed++; this.total++; this.windowCount++;
      this.squareSum += Number.isFinite(sample) ? sample * sample : 0;
      if (this.windowCount < this.windowSamples) continue;
      const ms = this.windowCount * 1000 / this.sampleRate;
      const loud = Math.sqrt(this.squareSum / this.windowCount) >= this.config.rmsThreshold;
      this.windowCount = 0; this.squareSum = 0;
      if (loud) {
        this.voiceRunMs += ms;
        this.quietMs = 0;
        if (this.voiceRunMs >= this.config.voiceMs) this.heardVoice = true;
      } else {
        this.voiceRunMs = 0;
        this.quietMs += ms;
      }
      if (this.elapsedMs >= this.config.maxMs) this.ended = "limit";
      else if (this.heardVoice && this.quietMs >= this.config.silenceMs) this.ended = "pause";
      else if (!this.heardVoice && this.elapsedMs >= this.config.noSpeechMs) this.ended = "no_speech";
      if (this.ended) break;
    }
    return { reason: this.ended, consumed };
  }
}
