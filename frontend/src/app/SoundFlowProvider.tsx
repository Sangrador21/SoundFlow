import {
  createContext,
  useContext,
  useEffect,
  useState,
  useSyncExternalStore,
} from "react";
import type { ReactNode } from "react";
import { loadServers, saveServers } from "../config/servers";
import { ClusterApi } from "../services/cluster-api";
import { AudioEngine } from "../features/player/audio/audio-engine";
import { PlaybackController } from "../features/player/playback-controller";
import type { PlaybackState } from "../features/player/playback-controller";
import { OfflineStore } from "../features/offline/offline-store";
import type { OfflineState } from "../features/offline/offline-store";
import { RecentDownloads } from "../features/offline/recent-downloads";

interface ContextValue {
  servers: string[];
  api: ClusterApi;
  player: PlaybackController;
  playback: PlaybackState;
  offline: OfflineStore;
  offlineState: OfflineState;
  recent: RecentDownloads;
  configure: (servers: string[]) => void;
}
const SoundFlowContext = createContext<ContextValue | null>(null);

export function SoundFlowProvider({ children }: { children: ReactNode }) {
  const [servers, setServers] = useState(loadServers);
  const [api, setApi] = useState(() => new ClusterApi(servers));
  const [offline] = useState(() => new OfflineStore());
  const [player] = useState(
    () => new PlaybackController(api, new AudioEngine(), offline),
  );
  const [recent] = useState(() => new RecentDownloads(api, player, offline));
  const offlineState = useSyncExternalStore(
    offline.subscribe,
    offline.getSnapshot,
  );
  const playback = useSyncExternalStore(player.subscribe, player.getSnapshot);
  useEffect(() => {
    void offline.start();
    const disconnect = recent.connect();
    return () => {
      disconnect();
      offline.dispose();
    };
  }, [offline, recent]);
  useEffect(() => {
    const leave = () => player.stop();
    window.addEventListener("pagehide", leave);
    return () => {
      window.removeEventListener("pagehide", leave);
      player.dispose();
    };
  }, [player]);
  const configure = (values: string[]) => {
    saveServers(values);
    const next = new ClusterApi(values);
    player.setApi(next);
    recent.setApi(next);
    setApi(next);
    setServers(values);
  };
  return (
    <SoundFlowContext
      value={{
        servers,
        api,
        player,
        playback,
        configure,
        offline,
        offlineState,
        recent,
      }}
    >
      {children}
    </SoundFlowContext>
  );
}
export function useSoundFlow(): ContextValue {
  const value = useContext(SoundFlowContext);
  if (!value) throw new Error("Falta el proveedor de SoundFlow.");
  return value;
}
