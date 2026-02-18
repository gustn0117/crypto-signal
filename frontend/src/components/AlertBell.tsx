"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Alert, fetchAlerts, markAlertsRead } from "@/lib/api";
import { Bell, X } from "lucide-react";
import Link from "next/link";

interface AlertBellProps {
  unreadCount: number;
  latestAlert: Alert | null;
  onClearLatest: () => void;
  onResetUnread: (count: number) => void;
}

function timeAgo(timestamp: string): string {
  const diff = Date.now() - new Date(timestamp).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "방금";
  if (minutes < 60) return `${minutes}분 전`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}시간 전`;
  return `${Math.floor(hours / 24)}일 전`;
}

function signalColor(signal: string): string {
  if (signal.includes("LONG")) return "#26dad2";
  if (signal.includes("SHORT")) return "#ef5350";
  return "#abafb3";
}

export default function AlertBell({ unreadCount, latestAlert, onClearLatest, onResetUnread }: AlertBellProps) {
  const [open, setOpen] = useState(false);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<Alert | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // 새 알림 토스트 표시
  useEffect(() => {
    if (latestAlert) {
      setToast(latestAlert);
      const timer = setTimeout(() => {
        setToast(null);
        onClearLatest();
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [latestAlert, onClearLatest]);

  // 패널 열 때 알림 목록 로드
  const togglePanel = useCallback(async () => {
    if (!open) {
      setLoading(true);
      try {
        const data = await fetchAlerts(20);
        setAlerts(data.alerts);
      } catch (e) {
        console.error("알림 로드 실패:", e);
      } finally {
        setLoading(false);
      }
    }
    setOpen(!open);
  }, [open]);

  // 전체 읽음 처리
  const handleMarkAllRead = useCallback(async () => {
    const unreadIds = alerts.filter((a) => !a.read).map((a) => a.id);
    if (unreadIds.length === 0) return;
    try {
      await markAlertsRead(unreadIds);
      setAlerts((prev) => prev.map((a) => ({ ...a, read: true })));
      onResetUnread(0);
    } catch (e) {
      console.error("읽음 처리 실패:", e);
    }
  }, [alerts, onResetUnread]);

  // 패널 바깥 클릭 시 닫기
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  return (
    <div className="relative" ref={panelRef}>
      {/* 벨 아이콘 */}
      <button
        onClick={togglePanel}
        className="relative p-2 rounded hover:bg-card-active text-muted hover:text-white transition-colors"
      >
        <Bell size={18} />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] flex items-center justify-center text-[10px] font-bold text-white rounded-full px-1" style={{ backgroundColor: "#ef5350" }}>
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {/* 드롭다운 패널 */}
      {open && (
        <div className="absolute right-0 top-full mt-2 w-[380px] max-h-[480px] rounded-lg border border-border bg-card shadow-xl z-50 overflow-hidden">
          <div className="px-4 py-3 border-b border-border flex items-center justify-between">
            <h3 className="font-semibold text-sm">알림</h3>
            <div className="flex items-center gap-3">
              {unreadCount > 0 && (
                <button
                  onClick={handleMarkAllRead}
                  className="text-xs text-primary hover:underline"
                >
                  모두 읽음
                </button>
              )}
              <Link
                href="/alerts"
                className="text-xs text-muted hover:text-white"
                onClick={() => setOpen(false)}
              >
                설정
              </Link>
            </div>
          </div>
          <div className="overflow-auto max-h-[400px]">
            {loading ? (
              <div className="p-6 text-center text-muted text-sm">로딩 중...</div>
            ) : alerts.length === 0 ? (
              <div className="p-6 text-center text-muted text-sm">알림이 없습니다</div>
            ) : (
              alerts.map((alert) => (
                <Link
                  key={alert.id}
                  href={`/coin/${alert.symbol.replace("/", "")}`}
                  onClick={() => setOpen(false)}
                  className={`block px-4 py-3 border-b border-card-active hover:bg-body transition-colors ${
                    !alert.read ? "bg-body/50" : ""
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      {!alert.read && (
                        <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: "#4680ff" }} />
                      )}
                      <span className="font-semibold text-sm text-heading">
                        {alert.symbol}
                      </span>
                      <span
                        className="text-xs font-bold px-1.5 py-0.5 rounded"
                        style={{
                          color: signalColor(alert.signal),
                          backgroundColor: `${signalColor(alert.signal)}20`,
                        }}
                      >
                        {alert.signal}
                      </span>
                    </div>
                    <span className="text-xs text-muted">{timeAgo(alert.timestamp)}</span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-muted">
                    <span>신뢰도 {(alert.confidence * 100).toFixed(0)}%</span>
                    <span>${alert.current_price.toLocaleString()}</span>
                  </div>
                  {alert.summary && (
                    <p className="text-xs text-muted mt-1 truncate">{alert.summary}</p>
                  )}
                </Link>
              ))
            )}
          </div>
        </div>
      )}

      {/* 토스트 알림 */}
      {toast && (
        <div className="fixed top-4 right-4 w-[360px] p-4 rounded-lg border bg-card border-border shadow-2xl z-[100] animate-slide-in">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-sm font-bold text-heading">{toast.symbol}</span>
              <span
                className="text-xs font-bold px-1.5 py-0.5 rounded"
                style={{
                  color: signalColor(toast.signal),
                  backgroundColor: `${signalColor(toast.signal)}20`,
                }}
              >
                {toast.signal}
              </span>
              <span className="text-xs text-muted">
                신뢰도 {(toast.confidence * 100).toFixed(0)}%
              </span>
            </div>
            <button
              onClick={() => { setToast(null); onClearLatest(); }}
              className="text-muted hover:text-white p-0.5"
            >
              <X size={14} />
            </button>
          </div>
          {toast.summary && (
            <p className="text-xs text-muted truncate">{toast.summary}</p>
          )}
        </div>
      )}
    </div>
  );
}
