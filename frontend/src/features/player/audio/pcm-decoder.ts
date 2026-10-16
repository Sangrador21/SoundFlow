export const SAMPLE_RATE = 44_100;
export const FRAME_BYTES = 4;
export interface StereoBlock {
  left: Float32Array;
  right: Float32Array;
  frames: number;
}

/** Conserva hasta tres bytes entre bloques HTTP: un bloque no equivale a una muestra. */
export class PcmDecoder {
  private carry = new Uint8Array(0);
  decode(chunk: Uint8Array): StereoBlock {
    const bytes = new Uint8Array(this.carry.length + chunk.length);
    bytes.set(this.carry);
    bytes.set(chunk, this.carry.length);
    const frames = Math.floor(bytes.length / FRAME_BYTES);
    const view = new DataView(bytes.buffer);
    const left = new Float32Array(frames);
    const right = new Float32Array(frames);
    for (let i = 0; i < frames; i++) {
      left[i] = view.getInt16(i * FRAME_BYTES, true) / 32768;
      right[i] = view.getInt16(i * FRAME_BYTES + 2, true) / 32768;
    }
    this.carry = bytes.slice(frames * FRAME_BYTES);
    return { left, right, frames };
  }
  get aligned(): boolean {
    return this.carry.length === 0;
  }
}
