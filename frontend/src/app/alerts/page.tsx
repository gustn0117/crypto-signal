"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import {
  Alert,
  fetchAlerts,
  markAlertsRead,
} from "@/lib/api";
import { signalColor, timeAgo } from "@/lib/utils";
import { TableSkeleton } from "@/components/Skeleton";
import { Bell } from "lucide-react";

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [total, setTotal] = useState(0);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const alertsData = await fetchAlerts(100);
      setAlerts(alertsData.alerts);
      setTotal(alertsData.total);
      setUnread(alertsData.unread);
    } catch (e) {
      console.error("알림 데이터 로드 실패:", e);
    } finally {
      setLoading(false);
    }
  };

  const handleMarkAllRead = useCallback(async () => {
    const ids = alerts.filter((a) => !a.read).map((a) => a.id);
    if (ids.length === 0) return;
    try {
      await markAlertsRead(ids);
      setAlerts((prev) => prev.map((a) => ({ ...a, read: true })));
      setUnread(0);
    } catch (e) {
      console.error("읽음 처리 실패:", e);
    }
  }, [alerts]);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Bell size={22} className="text-primary" />
          <h1 className="text-xl font-bold text-heading">알림</h1>
        </div>
        <div className="cd-card p-0 overflow-hidden">
          <TableSkeleton rows={6} />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Bell size={22} className="text-primary" />
        <h1 className="text-xl font-bold text-heading">알림</h1>
      </div>

      <div className="flex items-center justify-between">
        <span className="text-sm text-muted">
          총 {total}개 / 읽지 않은 알림 {unread}개
        </span>
        {unread > 0 && (
          <button onClick={handleMarkAllRead} className="text-sm text-primary hover:underline">
            모두 읽음 처리
          </button>
        )}
      </div>

      {alerts.length === 0 ? (
        <div className="text-center py-16 text-muted">
          <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-card-active flex items-center justify-center">
            <Bell size={28} className="text-icon-muted" />
          </div>
          <p className="text-base font-medium text-heading mb-1">알림이 없습니다</p>
          <p className="text-sm text-muted">시그널이 감지되면 여기에 표시됩니다</p>
        </div>
      ) : (
        <div className="space-y-2">
          {alerts.map((alert) => (
            <Link
              key={alert.id}
              href={`/coin/${alert.symbol.replace("/", "")}`}
              className={`block p-4 rounded-card border transition-colors hover:border-primary/40 ${
                alert.read
                  ? "border-border bg-body"
                  : "border-border bg-card"
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-3 flex-wrap">
                  {!alert.read && (
                    <span className="w-2.5 h-2.5 rounded-full bg-primary shrink-0" />
                  )}
                  <span className="font-bold text-heading">{alert.symbol}</span>
                  <span
                    className="text-xs font-bold px-2 py-0.5 rounded-full"
                    style={{
                      color: signalColor(alert.signal),
                      backgroundColor: `color-mix(in srgb, ${signalColor(alert.signal)} 12%, transparent)`,
                    }}
                  >
                    {alert.signal}
                  </span>
                  <span className="text-sm text-muted">
                    신뢰도 {(alert.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <span className="text-xs text-muted">{timeAgo(alert.timestamp)}</span>
              </div>
              <div className="flex items-center gap-4 text-sm text-body-text flex-wrap">
                <span>가격: ${alert.current_price.toLocaleString()}</span>
                {alert.trade_params && (
                  <>
                    <span className="text-danger">
                      SL: ${alert.trade_params.stop_loss.toLocaleString()}
                    </span>
                    <span className="text-success">
                      TP1: ${alert.trade_params.take_profit_1.toLocaleString()}
                    </span>
                  </>
                )}
              </div>
              {alert.summary && (
                <p className="text-sm text-muted mt-2 leading-relaxed">{alert.summary}</p>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
