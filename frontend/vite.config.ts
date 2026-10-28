import { configDefaults, defineConfig } from "vitest/config";
import { loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { soundFlowPwa } from "./pwa/build.ts";

export default defineConfig(({ mode }) => ({
  base:
    process.env.VITE_BASE_PATH ||
    loadEnv(mode, process.cwd(), "VITE_").VITE_BASE_PATH ||
    "/",
  plugins: [react(), tailwindcss(), soundFlowPwa()],
  server: { port: 5173, strictPort: true },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    restoreMocks: true,
    exclude: [...configDefaults.exclude, "e2e/**"],
  },
}));
