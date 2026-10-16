import { describe, expect, it } from "vitest";
import { PcmDecoder } from "./pcm-decoder";

describe("PCM recibido por HTTP", () => {
  it("mantiene canales y muestras exactas aunque los bloques terminen entre bytes", () => {
    const raw = new Uint8Array(12);
    const data = new DataView(raw.buffer);
    const samples = [-32768, 32767, 1024, -2048, 8192, -8192];
    samples.forEach((sample, i) => data.setInt16(i * 2, sample, true));
    const decoder = new PcmDecoder();
    const left: number[] = [],
      right: number[] = [];
    for (const chunk of [
      raw.slice(0, 1),
      raw.slice(1, 6),
      raw.slice(6, 11),
      raw.slice(11),
    ]) {
      const block = decoder.decode(chunk);
      left.push(...block.left);
      right.push(...block.right);
    }
    expect(left).toEqual([-1, 1024 / 32768, 0.25]);
    expect(right).toEqual([32767 / 32768, -2048 / 32768, -0.25]);
    expect(decoder.aligned).toBe(true);
  });
});
