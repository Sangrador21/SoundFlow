// @vitest-environment node
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { describe, expect, it } from "vitest";

interface Processor {
  port: { onmessage: (event: { data: Record<string, unknown> }) => void };
  process: (input: unknown[], output: Float32Array[][]) => boolean;
}
function worklet() {
  const messages: Record<string, unknown>[] = [];
  let Factory: (new () => Processor) | undefined;
  class Base {
    port = {
      onmessage: null,
      postMessage: (data: Record<string, unknown>) => messages.push(data),
    };
  }
  runInNewContext(
    readFileSync(
      new URL("../../../../public/worklets/pcm-player.js", import.meta.url),
      "utf8",
    ),
    {
      AudioWorkletProcessor: Base,
      registerProcessor: (_name: string, value: new () => Processor) => {
        Factory = value;
      },
      sampleRate: 44_100,
      Float32Array,
    },
  );
  const processor = new Factory!();
  const send = (data: Record<string, unknown>) =>
    processor.port.onmessage({ data });
  const process = () => {
    const left = new Float32Array(128),
      right = new Float32Array(128);
    processor.process([], [[left, right]]);
    return [left, right] as const;
  };
  return { send, process, messages };
}
describe("Hilo de reproducción", () => {
  it("no confunde falta temporal de datos con el fin de canción", () => {
    const w = worklet();
    w.send({ type: "reset", id: 1 });
    w.send({
      type: "chunk",
      id: 1,
      left: new Float32Array([0.5, 0.6]),
      right: new Float32Array([-0.5, -0.6]),
    });
    expect(w.process()[0].every((value) => value === 0)).toBe(true);
    expect(
      w.messages.filter((message) => message.type === "ended"),
    ).toHaveLength(0);
    w.send({ type: "end", id: 1 });
    const [left, right] = w.process();
    expect(left[0]).toBe(0.5);
    expect(right[0]).toBe(-0.5);
    expect(w.messages.filter((message) => message.type === "ended")).toEqual([
      { type: "ended", id: 1, played: 2, frames: 0 },
    ]);
    w.process();
    expect(
      w.messages.filter((message) => message.type === "ended"),
    ).toHaveLength(1);
  });
  it("conserva el audio al pausar y descarta bloques de una generación anterior", () => {
    const w = worklet();
    w.send({ type: "reset", id: 2, paused: true });
    w.send({
      type: "chunk",
      id: 1,
      left: new Float32Array([1]),
      right: new Float32Array([1]),
    });
    w.send({
      type: "chunk",
      id: 2,
      left: new Float32Array([0.25]),
      right: new Float32Array([0.75]),
    });
    w.send({ type: "end", id: 2 });
    expect(w.process()[0][0]).toBe(0);
    expect(
      w.messages.filter((message) => message.type === "ended"),
    ).toHaveLength(0);
    w.send({ type: "pause", id: 2, value: false });
    const [left, right] = w.process();
    expect(left[0]).toBe(0.25);
    expect(right[0]).toBe(0.75);
  });
});
