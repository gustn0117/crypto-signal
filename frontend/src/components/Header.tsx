"use client";

import AlertBell from "./AlertBell";
import { Wifi, WifiOff } from "lucide-react";

interface HeaderProps {
  connected: boolean;
  unreadAlerts: number;
  latestAlert: any;
  onClearLatest: () => void;
  onResetUnread: (count: number) => void;
}

export default function Header({
  connected,
  unreadAlerts,
  latestAlert,
  onClearLatest,
  onResetUnread,
}: HeaderProps) {
  return (
    <header
      className="fixed top-0 right-0 z-30 bg-card flex items-center justify-end px-6"
      style={{
        height: "var(--header-height)",
        left: "var(--sidebar-width)",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <div className="flex items-center gap-5">
        {/* WebSocket 연결 상태 */}
        <div className="flex items-center gap-2">
          {connected ? (
            <>
              <Wifi size={14} className="text-success" />
              <span className="text-success text-xs font-medium">실시간</span>
            </>
          ) : (
            <>
              <WifiOff size={14} className="text-danger" />
              <span className="text-danger text-xs font-medium">연결 끊김</span>
            </>
          )}
        </div>

        {/* 알림 벨 */}
        <AlertBell
          unreadCount={unreadAlerts}
          latestAlert={latestAlert}
          onClearLatest={onClearLatest}
          onResetUnread={onResetUnread}
        />
      </div>
    </header>
  );
}
