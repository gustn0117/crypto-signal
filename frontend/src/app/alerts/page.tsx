"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import {
  Alert,
  AlertConfig,
  fetchAlerts,
  fetchAlertConfig,
  updateAlertConfig,
  markAlertsRead,
} from "@/lib/api";
import { Bell, Settings, Check } from "lucide-react";

const SIGNAL_OPTIONS = ["STRONG_LONG", "LONG", "SHORT", "STRONG_SHORT"];

function signalColor(signal: string): string {
  if (signal.includes("LONG")) return "#4caf50";
  if (signal.includes("SHORT")) return "#ef5350";
  return "#abafb3";
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

export default function AlertsPage() {
  const [tab, setTab] = useState<"history" | "settings">("history");
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [total, setTotal] = useState(0);
  const [unread, setUnread] = useState(0);
  const [config, setConfig] = useState<AlertConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [alertsData, configData] = await Promise.all([
        fetchAlerts(100),
        fetchAlertConfig(),
      ]);
      setAlerts(alertsData.alerts);
      setTotal(alertsData.total);
      setUnread(alertsData.unread);
      setConfig(configData);
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

  const handleSaveConfig = useCallback(async () => {
    if (!config) return;
    setSaving(true);
    try {
      const updated = await updateAlertConfig(config);
      setConfig(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      console.error("설정 저장 실패:", e);
    } finally {
      setSaving(false);
    }
  }, [config]);

  const toggleSignalType = (type: string) => {
    if (!config) return;
    const types = config.signal_types.includes(type)
      ? config.signal_types.filter((t) => t !== type)
      : [...config.signal_types, type];
    setConfig({ ...config, signal_types: types });
  };

  return (
    <div className="space-y-5">
      {/* 탭 */}
      <div className="flex items-center gap-1" style={{ borderBottom: "1px solid var(--border)" }}>
        <button
          onClick={() => setTab("history")}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            tab === "history"
              ? "border-primary text-heading"
              : "border-transparent text-body-text hover:text-heading"
          }`}
        >
          <Bell size={16} />
          알림 내역
          {unread > 0 && (
            <span className="ml-1 px-1.5 py-0.5 text-xs bg-danger text-white rounded-full">
              {unread}
            </span>
          )}
        </button>
        <button
          onClick={() => setTab("settings")}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            tab === "settings"
              ? "border-primary text-heading"
              : "border-transparent text-body-text hover:text-heading"
          }`}
        >
          <Settings size={16} />
          알림 설정
        </button>
      </div>

      {loading ? (
        <div className="text-center py-12 text-muted">로딩 중...</div>
      ) : tab === "history" ? (
        <div>
          <div className="flex items-center justify-between mb-4">
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
              <Bell size={48} className="mx-auto mb-4 opacity-50" />
              <p className="text-lg mb-2 text-heading">알림이 없습니다</p>
              <p className="text-sm">시그널이 감지되면 여기에 표시됩니다</p>
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
                    <div className="flex items-center gap-3">
                      {!alert.read && (
                        <span className="w-2.5 h-2.5 rounded-full bg-primary shrink-0" />
                      )}
                      <span className="font-bold text-heading">{alert.symbol}</span>
                      <span
                        className="text-xs font-bold px-2 py-0.5 rounded-full"
                        style={{
                          color: signalColor(alert.signal),
                          backgroundColor: `${signalColor(alert.signal)}20`,
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
                  <div className="flex items-center gap-4 text-sm text-body-text">
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
                    <p className="text-sm text-muted mt-2">{alert.summary}</p>
                  )}
                </Link>
              ))}
            </div>
          )}
        </div>
      ) : (
        config && (
          <div className="max-w-[600px] space-y-5">
            {/* 알림 ON/OFF */}
            <div className="cd-card">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-semibold text-heading">알림 활성화</h3>
                  <p className="text-sm text-muted mt-1">시그널 감지 시 실시간 알림을 받습니다</p>
                </div>
                <button
                  onClick={() => setConfig({ ...config, enabled: !config.enabled })}
                  className={`w-12 h-6 rounded-full transition-colors relative ${
                    config.enabled ? "bg-success-text" : "bg-icon-muted"
                  }`}
                >
                  <span
                    className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-transform ${
                      config.enabled ? "left-[26px]" : "left-0.5"
                    }`}
                  />
                </button>
              </div>
            </div>

            {/* 최소 신뢰도 */}
            <div className="cd-card">
              <h3 className="font-semibold text-heading mb-3">최소 신뢰도</h3>
              <p className="text-sm text-muted mb-3">이 값 이상의 신뢰도를 가진 시그널만 알림을 받습니다</p>
              <div className="flex items-center gap-4">
                <input
                  type="range"
                  min={0.3}
                  max={0.9}
                  step={0.05}
                  value={config.min_confidence}
                  onChange={(e) => setConfig({ ...config, min_confidence: parseFloat(e.target.value) })}
                  className="flex-1 accent-primary"
                />
                <span className="text-sm font-mono font-bold text-heading w-12 text-right">
                  {(config.min_confidence * 100).toFixed(0)}%
                </span>
              </div>
            </div>

            {/* 시그널 타입 */}
            <div className="cd-card">
              <h3 className="font-semibold text-heading mb-3">시그널 타입</h3>
              <p className="text-sm text-muted mb-3">알림을 받을 시그널 타입을 선택합니다</p>
              <div className="grid grid-cols-2 gap-2">
                {SIGNAL_OPTIONS.map((type) => {
                  const active = config.signal_types.includes(type);
                  const color = signalColor(type);
                  return (
                    <button
                      key={type}
                      onClick={() => toggleSignalType(type)}
                      className={`p-3 rounded-card border text-sm font-medium transition-colors ${
                        active
                          ? "border-current"
                          : "border-border text-muted hover:text-heading"
                      }`}
                      style={active ? { color, borderColor: color, backgroundColor: `${color}10` } : undefined}
                    >
                      {type.replace("_", " ")}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* 쿨다운 */}
            <div className="cd-card">
              <h3 className="font-semibold text-heading mb-3">쿨다운 (분)</h3>
              <p className="text-sm text-muted mb-3">같은 심볼+시그널에 대해 중복 알림을 방지하는 시간 간격</p>
              <div className="flex items-center gap-4">
                <input
                  type="range"
                  min={5}
                  max={120}
                  step={5}
                  value={config.cooldown_minutes}
                  onChange={(e) => setConfig({ ...config, cooldown_minutes: parseInt(e.target.value) })}
                  className="flex-1 accent-primary"
                />
                <span className="text-sm font-mono font-bold text-heading w-16 text-right">
                  {config.cooldown_minutes}분
                </span>
              </div>
            </div>

            {/* 저장 버튼 */}
            <button
              onClick={handleSaveConfig}
              disabled={saving}
              className="w-full py-3 bg-success-text hover:bg-success-text/80 text-white font-medium rounded-card transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {saved ? (
                <><Check size={16} /> 저장됨</>
              ) : saving ? (
                "저장 중..."
              ) : (
                "설정 저장"
              )}
            </button>
          </div>
        )
      )}
    </div>
  );
}
