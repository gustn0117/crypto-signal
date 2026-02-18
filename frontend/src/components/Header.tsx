"use client";

import AlertBell from "./AlertBell";
import { Wifi, WifiOff, Menu } from "lucide-react";

interface HeaderProps {
  connected: boolean;
  unreadAlerts: number;
  latestAlert: any;
  onClearLatest: () => void;
  onResetUnread: (count: number) => void;
  isDesktop: boolean;
  onMenuClick: () => void;
}

export default function Header({
  connected,
  unreadAlerts,
  latestAlert,
  onClearLatest,
  onResetUnread,
  isDesktop,
  onMenuClick,
}: HeaderProps) {
  return (
    <header
      className="fixed top-0 right-0 z-30 flex items-center justify-between px-4 lg:px-6 bg-card/80 backdrop-blur-md"
      style={{
        height: "var(--header-height)",
        left: isDesktop ? "var(--sidebar-width)" : 0,
        borderBottom: "1px solid var(--border)",
      }}
    >
      {/* 좌측: 햄버거 (모바일) */}
      <div className="flex items-center gap-3">
        {!isDesktop && (
          <button
            onClick={onMenuClick}
            className="p-2 -ml-1 rounded-card text-icon-muted hover:text-heading hover:bg-card-active transition-colors"
            aria-label="사이드바 메뉴 열기"
          >
            <Menu size={20} />
          </button>
        )}
      </div>

      {/* 우측: 상태 + 알림 */}
      <div className="flex items-center gap-3">
        {/* WebSocket 연결 상태 pill */}
        <div
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
            connected
              ? "bg-success/10 text-success border border-success/20"
              : "bg-danger/10 text-danger border border-danger/20"
          }`}
        >
          {connected ? (
            <>
              <Wifi size={12} />
              <span>Live</span>
            </>
          ) : (
            <>
              <WifiOff size={12} />
              <span>연결 끊김</span>
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
