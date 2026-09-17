import React from "react";
import ReactDOM from "react-dom/client";
import "@livekit/components-styles";
import "./styles.css";
import "./ui/tailwind.css";
import "./ui/ui.css";
import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
