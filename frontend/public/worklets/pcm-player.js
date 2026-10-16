/* PCM se procesa en el hilo de audio, separado del renderizado de React. */
class SoundFlowProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.id = 0;
    this.blocks = [];
    this.head = 0;
    this.offset = 0;
    this.frames = 0;
    this.played = 0;
    this.paused = false;
    this.complete = false;
    this.started = false;
    this.ended = false;
    this.ticks = 0;
    this.port.onmessage = ({ data }) => {
      if (data.type === "reset") {
        this.id = data.id;
        this.blocks = [];
        this.head = this.offset = this.frames = this.played = this.ticks = 0;
        this.complete = this.started = this.ended = false;
        this.paused = Boolean(data.paused);
      } else if (data.id === this.id) {
        if (data.type === "chunk") {
          this.blocks.push({ left: data.left, right: data.right });
          this.frames += data.left.length;
        } else if (data.type === "end") this.complete = true;
        else if (data.type === "pause") this.paused = data.value;
      }
    };
  }
  process(_inputs, outputs) {
    const output = outputs[0];
    if (!output?.[0]) return true;
    const left = output[0];
    const right = output[1] || output[0];
    left.fill(0);
    right.fill(0);
    if (this.id && !this.paused && !this.ended) {
      const minimum = this.played ? Math.floor(sampleRate * 0.25) : sampleRate;
      if (!this.started && (this.frames >= minimum || this.complete))
        this.started = true;
      if (this.started) {
        let write = 0;
        while (write < left.length && this.head < this.blocks.length) {
          const block = this.blocks[this.head];
          const count = Math.min(
            left.length - write,
            block.left.length - this.offset,
          );
          left.set(
            block.left.subarray(this.offset, this.offset + count),
            write,
          );
          right.set(
            block.right.subarray(this.offset, this.offset + count),
            write,
          );
          this.frames -= count;
          this.played += count;
          this.offset += count;
          write += count;
          if (this.offset === block.left.length) {
            this.blocks[this.head] = null;
            this.head++;
            this.offset = 0;
          }
        }
        if (this.head > 64) {
          this.blocks = this.blocks.slice(this.head);
          this.head = 0;
        }
        if (!this.frames && this.complete) {
          this.ended = true;
          this.port.postMessage({
            type: "ended",
            id: this.id,
            played: this.played,
            frames: 0,
          });
        } else if (!this.frames) {
          this.started = false;
        }
      }
    }
    this.ticks += left.length;
    if (this.id && !this.ended && this.ticks >= sampleRate / 10) {
      this.ticks = 0;
      this.port.postMessage({
        type: "progress",
        id: this.id,
        played: this.played,
        frames: this.frames,
        buffering: !this.started && !this.complete,
      });
    }
    return true;
  }
}
registerProcessor("soundflow-pcm", SoundFlowProcessor);
