import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import { SoundFlowProvider } from "./app/SoundFlowProvider";
import "./styles/index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <SoundFlowProvider>
      <App />
    </SoundFlowProvider>
  </StrictMode>,
);
