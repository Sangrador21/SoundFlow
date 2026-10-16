export interface Song {
  id: string;
  filename: string;
  title: string;
  artist: string;
  duration: number;
  servers: string[];
  available: boolean;
}
export interface Resources {
  accepting: boolean;
  active_streams: number;
  cpu_percent: number;
  memory_percent: number;
  maintenance: boolean;
}
export interface ClusterNode {
  server_id: string;
  base_url: string;
  resources: Resources;
  song_count: number;
}
export interface Catalog {
  songs: Song[];
  nodes: ClusterNode[];
  offline: string[];
}
export interface StreamAssignment {
  stream_id: string;
  server_id: string;
  server_url: string;
  audio_url: string;
  song_id: string;
  start: number;
  duration: number;
  sample_rate: number;
  channels: number;
  sample_bytes: number;
}
export interface Ticket {
  request_id: string;
  state: "waiting" | "ready" | "failed" | "cancelled";
  position: number;
  message: string;
  stream: StreamAssignment | null;
  error_code: number;
  wait_timeout: number;
}
export interface Lease {
  coordinator: string;
  ticket: Ticket;
}
