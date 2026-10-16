import type { StereoBlock } from "./pcm-decoder";
import { SAMPLE_RATE } from "./pcm-decoder";

export interface EngineEvent {
  type: "progress" | "ended" | "suspended";
  id: number;
  played: number;
  frames: number;
  buffering: boolean;
}
export interface PlayerEngine {
  onEvent: (event: EngineEvent) => void;
  unlock(): Promise<void>;
  reset(id: number, paused: boolean): void;
  feed(id: number, block: StereoBlock): void;
  finish(id: number): void;
  pause(id: number, value: boolean): void;
  volume(value: number): void;
  dispose(): void;
}
export class AudioEngine implements PlayerEngine {
  onEvent: (event: EngineEvent) => void = () => undefined;
  private context: AudioContext | null = null;
  private node: AudioWorkletNode | null = null;
  private gain: GainNode | null = null;
  private initialization: Promise<void> | null = null;
  private id = 0;
  private level = 0.7;

  async unlock(): Promise<void> {
    // resume se invoca desde el clic, antes de esperar la red o cargar el módulo.
    if (!this.context) {
      if (!globalThis.AudioContext)
        return Promise.reject(new Error("Tu navegador no admite Web Audio."));
      this.context = new AudioContext({
        sampleRate: SAMPLE_RATE,
        latencyHint: "playback",
      });
      if (!this.context.audioWorklet)
        return Promise.reject(
          new Error(
            "El audio requiere HTTPS o localhost y un navegador actualizado.",
          ),
        );
      if (this.context.sampleRate !== SAMPLE_RATE) {
        return Promise.reject(
          new Error(
            "El navegador no admite la frecuencia de audio de 44.1 kHz.",
          ),
        );
      }
      this.context.onstatechange = () => {
        if (this.context?.state === "suspended" && this.id) {
          this.onEvent({
            type: "suspended",
            id: this.id,
            played: 0,
            frames: 0,
            buffering: false,
          });
        }
      };
      this.initialization = this.context.audioWorklet
        .addModule(`${import.meta.env.BASE_URL}worklets/pcm-player.js`)
        .then(() => {
          if (!this.context || this.context.state === "closed") return;
          this.node = new AudioWorkletNode(this.context, "soundflow-pcm", {
            numberOfInputs: 0,
            numberOfOutputs: 1,
            outputChannelCount: [2],
          });
          this.gain = this.context.createGain();
          this.gain.gain.value = this.level;
          this.node.connect(this.gain).connect(this.context.destination);
          this.node.port.onmessage = ({ data }: MessageEvent<EngineEvent>) =>
            this.onEvent(data);
        });
    }
    const resumed = this.context.resume();
    return Promise.all([resumed, this.initialization]).then(() => undefined);
  }
  reset(id: number, paused: boolean): void {
    this.id = id;
    this.node?.port.postMessage({ type: "reset", id, paused });
  }
  feed(id: number, block: StereoBlock): void {
    this.node?.port.postMessage(
      { type: "chunk", id, left: block.left, right: block.right },
      [block.left.buffer as ArrayBuffer, block.right.buffer as ArrayBuffer],
    );
  }
  finish(id: number): void {
    this.node?.port.postMessage({ type: "end", id });
  }
  pause(id: number, value: boolean): void {
    this.node?.port.postMessage({ type: "pause", id, value });
  }
  volume(value: number): void {
    this.level = value;
    if (this.gain && this.context)
      this.gain.gain.setTargetAtTime(value, this.context.currentTime, 0.015);
  }
  dispose(): void {
    this.node?.disconnect();
    this.gain?.disconnect();
    if (this.context) {
      this.context.onstatechange = null;
      void this.context.close();
    }
    this.context = null;
    this.node = null;
    this.initialization = null;
  }
}
