/* global AudioWorkletProcessor, registerProcessor */
class PCMRecorder extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Float32Array(4096);
    this.used = 0;
    this.stopped = false;
    this.port.onmessage = () => {
      this.stopped = true;
      if (this.used) this.port.postMessage(this.buffer.slice(0, this.used));
      this.port.postMessage("done");
    };
  }
  process(inputs) {
    if (this.stopped) return false;
    const channel = inputs[0]?.[0];
    if (!channel) return true;
    for (const sample of channel) {
      this.buffer[this.used++] = sample;
      if (this.used === this.buffer.length) {
        this.port.postMessage(this.buffer);
        this.used = 0;
      }
    }
    return true;
  }
}
registerProcessor("avatar-pcm-recorder", PCMRecorder);
