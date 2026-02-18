"use client";

import { createContext, useContext } from "react";
import Sidebar from "./Sidebar";
import Header from "./Header";
import { useWebSocket } from "@/hooks/useWebSocket";

type WebSocketState = ReturnType<typeof useWebSocket>;

const WebSocketContext = createContext<WebSocketState | null>(null);

export function useWS(): WebSocketState {
  const ctx = useContext(WebSocketContext);
  if (!ctx) throw new Error("useWS must be used within ClientLayout");
  return ctx;
}

export default function ClientLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const ws = useWebSocket();

  return (
    <WebSocketContext.Provider value={ws}>
      <div className="flex min-h-screen bg-body">
        <Sidebar />
        <div
          className="flex-1 flex flex-col min-w-0"
          style={{ marginLeft: "var(--sidebar-width)" }}
        >
          <Header
            connected={ws.connected}
            unreadAlerts={ws.unreadAlerts}
            latestAlert={ws.latestAlert}
            onClearLatest={ws.clearLatestAlert}
            onResetUnread={ws.resetUnreadAlerts}
          />
          <main
            className="flex-1 p-6 overflow-auto"
            style={{ marginTop: "var(--header-height)" }}
          >
            {children}
          </main>
        </div>
      </div>
    </WebSocketContext.Provider>
  );
}
