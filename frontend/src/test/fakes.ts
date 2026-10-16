import type {
  PlayerEngine,
  EngineEvent,
} from "../features/player/audio/audio-engine";
import type { StereoBlock } from "../features/player/audio/pcm-decoder";
import type { Song } from "../types/api";

export class FakeEngine implements PlayerEngine {
  onEvent: (event: EngineEvent) => void = () => undefined;
  blocks: StereoBlock[] = [];
  resets: number[] = [];
  ends: number[] = [];
  async unlock() {}
  reset(id: number) {
    this.resets.push(id);
  }
  feed(_id: number, block: StereoBlock) {
    this.blocks.push(block);
  }
  finish(id: number) {
    this.ends.push(id);
  }
  pause() {}
  volume() {}
  dispose() {}
}
export const song: Song = {
  id: "a".repeat(64),
  title: "Canción uno",
  artist: "Artista",
  duration: 20,
  servers: ["S1"],
  available: true,
  filename: "one.wav",
};
export const second: Song = {
  ...song,
  id: "b".repeat(64),
  title: "Canción dos",
  servers: ["S2"],
};
export const pcmHeaders = {
  "X-Audio-Format": "s16le",
  "X-Sample-Rate": "44100",
  "X-Channels": "2",
};
export function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
export function assigned(index: number, start = 0) {
  return {
    request_id: `ticket-${index}`,
    state: "ready",
    position: 0,
    message: "Listo",
    error_code: 0,
    wait_timeout: 2,
    stream: {
      stream_id: `stream-${index}`,
      server_id: "S2",
      server_url: "https://s2.test",
      audio_url: `https://s2.test/api/streams/stream-${index}/audio`,
      song_id: song.id,
      start,
      duration: 20,
      sample_rate: 44100,
      channels: 2,
      sample_bytes: 2,
    },
  };
}
