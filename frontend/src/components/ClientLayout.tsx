"use client";

import { createContext, useContext, useState } from "react";
import Sidebar from "./Sidebar";
import Header from "./Header";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useMediaQuery } from "@/hooks/useMediaQuery";

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
  const isDesktop = useMediaQuery("(min-width: 1024px)");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <WebSocketContext.Provider value={ws}>
      <div className="flex min-h-screen bg-body">
        <Sidebar
          isDesktop={isDesktop}
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
        />
        <div
          className="flex-1 flex flex-col min-w-0 transition-[margin] duration-200"
          style={{ marginLeft: isDesktop ? "var(--sidebar-width)" : 0 }}
        >
          <Header
            connected={ws.connected}
            unreadAlerts={ws.unreadAlerts}
            latestAlert={ws.latestAlert}
            onClearLatest={ws.clearLatestAlert}
            onResetUnread={ws.resetUnreadAlerts}
            isDesktop={isDesktop}
            onMenuClick={() => setSidebarOpen(true)}
          />
          <main
            className="flex-1 p-4 lg:p-6 overflow-auto"
            style={{ marginTop: "var(--header-height)" }}
          >
            {children}
          </main>
        </div>
      </div>
    </WebSocketContext.Provider>
  );
}
