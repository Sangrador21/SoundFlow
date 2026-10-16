import { expect, it, vi } from "vitest";
import { AudioEngine } from "./audio-engine";

it("solicita resume en el gesto inicial, antes de esperar el módulo de audio", async () => {
  let resolveModule: () => void = () => undefined;
  const addModule = vi.fn(
    () =>
      new Promise<void>((resolve) => {
        resolveModule = resolve;
      }),
  );
  const resume = vi.fn(async () => undefined);
  const context = {
    sampleRate: 44100,
    state: "running",
    currentTime: 0,
    onstatechange: null,
    audioWorklet: { addModule },
    resume,
    close: vi.fn(async () => undefined),
    destination: {},
    createGain: () => ({
      gain: { value: 1, setTargetAtTime: vi.fn() },
      connect: vi.fn(),
      disconnect: vi.fn(),
    }),
  };
  const Context = vi.fn(function () {
    return context;
  });
  const post = vi.fn();
  class WorkletNode {
    port = { postMessage: post, onmessage: null };
    connect(gain: unknown) {
      return gain;
    }
    disconnect() {}
  }
  vi.stubGlobal("AudioContext", Context);
  vi.stubGlobal("AudioWorkletNode", WorkletNode);
  const engine = new AudioEngine();
  try {
    const pending = engine.unlock();
    expect(resume).toHaveBeenCalledOnce();
    expect(addModule).toHaveBeenCalledWith("/worklets/pcm-player.js");
    resolveModule();
    await pending;
    engine.reset(2, false);
    engine.pause(2, true);
    expect(post).toHaveBeenLastCalledWith({
      type: "pause",
      id: 2,
      value: true,
    });
  } finally {
    engine.dispose();
    vi.unstubAllGlobals();
  }
});
it("convierte un rechazo síncrono del dispositivo en un error manejable", async () => {
  vi.stubGlobal(
    "AudioContext",
    class {
      constructor() {
        throw new Error("Frecuencia no soportada");
      }
    },
  );
  try {
    await expect(new AudioEngine().unlock()).rejects.toThrow(
      "Frecuencia no soportada",
    );
  } finally {
    vi.unstubAllGlobals();
  }
});
