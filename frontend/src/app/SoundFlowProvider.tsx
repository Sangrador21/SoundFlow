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

interface ContextValue {
  servers: string[];
  api: ClusterApi;
  player: PlaybackController;
  playback: PlaybackState;
  configure: (servers: string[]) => void;
}
const SoundFlowContext = createContext<ContextValue | null>(null);

export function SoundFlowProvider({ children }: { children: ReactNode }) {
  const [servers, setServers] = useState(loadServers);
  const [api, setApi] = useState(() => new ClusterApi(servers));
  const [player] = useState(
    () => new PlaybackController(api, new AudioEngine()),
  );
  const playback = useSyncExternalStore(player.subscribe, player.getSnapshot);
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
    setApi(next);
    setServers(values);
  };
  return (
    <SoundFlowContext value={{ servers, api, player, playback, configure }}>
      {children}
    </SoundFlowContext>
  );
}
export function useSoundFlow(): ContextValue {
  const value = useContext(SoundFlowContext);
  if (!value) throw new Error("Falta el proveedor de SoundFlow.");
  return value;
}
